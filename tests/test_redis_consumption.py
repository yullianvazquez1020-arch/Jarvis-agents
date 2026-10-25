"""Idle work must not burn Redis writes or hide a storage outage.

These regressions exercise the real code with fictitious stored data. They do
not connect to production, send messages, or relax the leadership check.
"""
import asyncio
import datetime
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_hardening as h
import jarvis_brain as brain

j = h.j
extensions = j._extensions


class IdleStorage(h.Base):
    def test_brain_health_reads_once_and_respects_owner_stop(self):
        for stopped in (False, True):
            with self.subTest(stopped=stopped), \
                 patch.dict(os.environ, {"BRAIN_ENABLED": "true"}), \
                 patch.object(j, "kv_get", return_value={"owner_on": not stopped}) as read, \
                 patch.object(j, "kv_set") as write:
                result = brain.health(j)
            self.assertEqual(result["enabled"], not stopped)
            read.assert_called_once_with(brain.STATE_KEY, {})
            write.assert_not_called()

    def test_health_still_returns_unavailable_when_redis_fails(self):
        with patch.object(j, "kv_get", side_effect=j.RedisRequestFailed("http_400:monthly_request_limit")):
            result = asyncio.run(j.health())
        self.assertEqual(result.status_code, 503)
        self.assertNotIn(b"monthly_request_limit", result.body)

    def test_reading_cycle_count_does_not_write_or_advance_old_day(self):
        previous = {"day": "2026-10-24", "cycles": 9, "owner_on": False}
        j.kv_set(brain.STATE_KEY, previous)
        today = datetime.datetime(2026, 10, 25, 12, tzinfo=j.TZ)
        with patch.object(j, "_now", return_value=today), patch.object(j, "kv_set") as write:
            self.assertEqual(brain._count_today(j), 0)
        write.assert_not_called()
        self.assertEqual(j.kv_get(brain.STATE_KEY, {}), previous)
        with patch.object(j, "_now", return_value=today):
            self.assertEqual(brain._count_today(j, bump=True), 1)
        self.assertEqual(j.kv_get(brain.STATE_KEY, {}),
                         {"day": "2026-10-25", "cycles": 1, "owner_on": False})

    def test_empty_schedules_do_not_write_or_read_jobs(self):
        with patch.object(extensions, "save") as save, patch.object(j, "_cload") as jobs:
            self.assertEqual(extensions.recurring_due(), [])
        save.assert_not_called()
        jobs.assert_not_called()

    def test_recurring_invoice_is_saved_once_and_pending_notice_survives(self):
        client = j.add_client("Fictitious client")
        job = j.add_job(client["id"], "Fictitious work", price=100)
        extensions.add_recurring_invoice(job["id"], j._today().isoformat())
        with patch.object(extensions, "save", wraps=extensions.save) as save:
            first = extensions.recurring_due()
            second = extensions.recurring_due()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 1)
        save.assert_called_once()

    def test_cancelled_job_disables_schedule_durably_once(self):
        client = j.add_client("Fictitious client")
        job = j.add_job(client["id"], "Fictitious work", price=100)
        extensions.add_recurring_invoice(job["id"], j._today().isoformat())
        data = j._cload()
        data["jobs"][0]["status"] = "cancelled"
        j._csave(data)
        with patch.object(extensions, "save", wraps=extensions.save) as save:
            self.assertEqual(extensions.recurring_due(), [])
            self.assertEqual(extensions.recurring_due(), [])
        save.assert_called_once()
        self.assertFalse(extensions.load()["recurring"][0]["active"])


class ClaimStorage(h.Base):
    def setUp(self):
        super().setUp()
        self.redis = h.FakeRedis()
        self.redis.d[j.LEADER_KEY] = j.INSTANCE_ID
        self.clock = 100.0
        self.calls = []
        j._redis_claims.clear()
        self.addCleanup(j._redis_claims.clear)
        self.addCleanup(patch.stopall)
        patch.object(j, "USE_REDIS", True).start()
        patch.object(j, "_fence", {"mode": "on", "leader": True}).start()
        patch.object(j, "_redis", side_effect=self.call).start()
        patch.object(j.time, "monotonic", side_effect=lambda: self.clock).start()

    def call(self, command):
        self.calls.append(command)
        return self.redis(command)

    def test_repeat_claim_skips_set_but_checks_leader_every_time(self):
        self.assertTrue(j._claim("claim:test", 60))
        for _ in range(10):
            self.assertFalse(j._claim("claim:test", 60))
        self.assertEqual(sum(cmd[0] == "SET" for cmd in self.calls), 1)
        self.assertEqual(sum(cmd == ["GET", j.LEADER_KEY] for cmd in self.calls), 11)

    def test_cached_claim_never_bypasses_lost_leadership(self):
        self.assertTrue(j._claim("claim:test", 60))
        self.redis.d[j.LEADER_KEY] = "new-instance"
        with self.assertRaises(j.StaleInstance):
            j._claim("claim:test", 60)
        self.assertFalse(j._fence["leader"])

    def test_expiry_and_explicit_release_allow_a_new_redis_claim(self):
        self.assertTrue(j._claim("claim:test", 60))
        self.clock += 61
        self.redis.d.pop("claim:test")  # fictitious Redis TTL expired
        self.assertTrue(j._claim("claim:test", 60))
        j._unclaim("claim:test")
        self.assertTrue(j._claim("claim:test", 60))

    def test_failed_or_foreign_claim_is_not_cached(self):
        self.redis.d["claim:foreign"] = "1"
        self.assertFalse(j._claim("claim:foreign", 60))
        self.assertEqual(j._redis_claims, {})
        self.redis.d.pop("claim:foreign")
        self.assertTrue(j._claim("claim:foreign", 60))

    def test_cache_is_bounded_and_rechecks_evicted_claim_in_redis(self):
        with patch.object(j, "_REDIS_CLAIMS_MAX", 2):
            for n in range(3):
                self.assertTrue(j._claim(f"claim:{n}", 60))
            self.assertEqual(len(j._redis_claims), 2)
            self.assertFalse(j._claim("claim:0", 60))

    def test_parallel_attempts_still_only_acquire_once(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: j._claim("claim:parallel", 60), range(8)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(sum(cmd[0] == "SET" for cmd in self.calls), 1)


if __name__ == "__main__":
    unittest.main()
