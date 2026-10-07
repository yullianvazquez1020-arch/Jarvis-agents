"""Desktop/voice turns: one request_id = one effect; retries, conflicts, interruptions and device isolation."""
import unittest
import unittest.mock

from desktop_helpers import DesktopBase, D, ai_text, j


class Idempotency(DesktopBase):
    def test_retry_same_id_same_text_runs_once(self):
        token, _ = self.pair()
        calls = self.ai(ai_text("primera"), ai_text("segunda"))
        a = self.turn(token, "¿cómo va la semana?").json()
        b = self.turn(token, "¿cómo va la semana?").json()
        self.assertEqual(len(calls), 1); self.assertEqual(a["reply"], b["reply"]); self.assertEqual(b["reply"], "primera")

    def test_same_id_different_text_refused(self):
        token, _ = self.pair()
        self.ai(ai_text("ok"))
        self.turn(token, "pregunta uno")
        self.assertEqual(self.turn(token, "pregunta dos").status_code, 409)

    def test_interrupted_turn_is_reported_not_rerun(self):
        token, dev = self.pair()
        calls = self.ai(ai_text("no debería sonar"))
        # a turn left "running" 10 minutes ago (inside retention, older than the stale limit)
        with j._data_lock:
            t = D.load_turns(); stamp = (j._now() - j.datetime.timedelta(minutes=10)).isoformat(timespec="seconds")
            t[f"{dev}:req-00000001"] = {"hash": D._h("hola"), "state": "running", "at": stamp, "device": dev}
            D.save_turns(t)
        r = self.turn(token, "hola").json()
        self.assertEqual(r["state"], "uncertain"); self.assertEqual(calls, [])
        g = self.client.post("/desktop/v1/turns/get", headers=self.hdr(token), json={"request_id": "req-00000001"}).json()
        self.assertEqual(g["state"], "uncertain")

    def test_one_turn_at_a_time_and_rate_limit(self):
        token, dev = self.pair()
        self.ai()
        D._running[dev] = 1
        self.assertEqual(self.turn(token, "hola", rid="busy-00001").status_code, 429)
        D._running[dev] = 0
        for i in range(D.RATE_TURNS):
            self.assertEqual(self.turn(token, "muéstrame la agenda", rid=f"rate-{i:05d}").status_code, 200)
        self.assertEqual(self.turn(token, "muéstrame la agenda", rid="rate-over-1").status_code, 429)

    def test_devices_cannot_see_each_other(self):
        t1, _ = self.pair("Mac 1"); t2, _ = self.pair("Mac 2")
        self.ai(ai_text("respuesta privada"))
        self.turn(t1, "algo privado")
        r = self.client.post("/desktop/v1/turns/get", headers=self.hdr(t2), json={"request_id": "req-00000001"})
        self.assertEqual(r.status_code, 404)

    def test_turn_record_written_before_work(self):
        token, dev = self.pair()
        seen = {}
        async def fake(history, tools, extra):
            seen["state"] = D.load_turns()[f"{dev}:req-00000001"]["state"]
            return ai_text("ok")
        self.ai()
        with unittest.mock.patch.object(j, "_ai_call_scoped", new=fake):
            self.turn(token, "una pregunta")
        self.assertEqual(seen["state"], "running")
        self.assertEqual(D.load_turns()[f"{dev}:req-00000001"]["state"], "done")


if __name__ == "__main__":
    unittest.main()
