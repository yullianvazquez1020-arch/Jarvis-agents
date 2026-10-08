import base64
import json
import os
import unittest
from unittest.mock import patch

import test_seal_migration as fixtures
import jarvis_private_backup as private
import jarvis_seal as seal

j = fixtures.j


class PrivateBackup(fixtures.Base):
    def seed(self):
        j.phase_a_remember_turn('tg:1', 'private question', 'private answer')
        j.kv_set('jarvis:profile', {'metas': ['private goal']})
        j.kv_set('jarvis:bio', {'text': 'private biography'})
        j.kv_set('jarvis:diary', ['private diary'])
        j.add_income(50)

    def test_full_roundtrip_in_fresh_storage(self):
        self.seed()
        original = {key: j.kv_get(key, None) for key in private.KEYS.values()}
        snap = json.loads(json.dumps(j.snapshot()))
        encoded = json.dumps(snap)
        for secret in ('private question', 'private goal', 'private biography', 'private diary', self.key_a):
            self.assertNotIn(secret, encoded)
        self.restart()
        import tempfile
        from pathlib import Path
        j.DATA_DIR = Path(tempfile.mkdtemp())
        r = j.restore_snapshot(snap, dry_run=False)
        self.assertFalse(r['dry_run'])
        for key, expected in original.items():
            self.assertEqual(j.kv_get(key, None), expected)
            self.assertTrue(seal.is_sealed(self.raw(key)))
        self.assertEqual(len(j.phase_a_restore('tg:1')), 2)
        self.assertEqual(len(j._bload()['income']), 1)
        self.assertEqual((j.MONEY_MAX_ORDER, j.MONEY_MAX_DAY), (100, 300))
        self.assertEqual(j._gload()['codes'], {})

    def test_wrong_key_refuses_before_any_business_write(self):
        self.seed(); snap = j.snapshot(); j.add_income(7)
        before = j._bload()
        with self.key(fixtures.new_key()):
            with self.assertRaises(ValueError):
                j.restore_snapshot(snap, dry_run=False)
        self.assertEqual(j._bload(), before)

    def test_ciphertext_can_be_exported_without_key_but_not_restored(self):
        self.seed()
        raw = self.raw('jarvis:history')
        with self.key(''):
            snap = j.snapshot()
            self.assertEqual(snap['private_data']['values']['history'], raw)
            with self.assertRaises(ValueError): j.restore_snapshot(snap, dry_run=False)

    def test_legacy_backup_leaves_private_data_unchanged(self):
        self.seed(); snap = j.snapshot(); del snap['private_data']
        raw = self.raw('jarvis:history')
        j.restore_snapshot(snap, dry_run=False)
        self.assertEqual(self.raw('jarvis:history'), raw)

    def test_damaged_ciphertext_or_schema_rejected(self):
        self.seed(); snap = j.snapshot()
        snap['private_data']['values']['history'] = 'sealed:v1:bad'
        with self.assertRaises(ValueError): j.restore_snapshot(snap)
        snap['private_data']['values']['history'] = {'bad': 'history'}
        with self.assertRaises(ValueError): j.restore_snapshot(snap)
        del snap['private_data']['values']['bio']
        with self.assertRaises(ValueError): j.restore_snapshot(snap)

    def test_preview_and_empty_sections_preserve_newer_history(self):
        snap = j.snapshot()
        self.seed(); raw = self.raw('jarvis:history')
        j.restore_snapshot(snap)
        self.assertEqual(self.raw('jarvis:history'), raw)
        j.restore_snapshot(snap, dry_run=False)
        self.assertEqual(self.raw('jarvis:history'), raw)

    def test_clear_legacy_export_is_sealed_when_key_available(self):
        with self.key(''): j.phase_a_remember_turn('tg:1', 'private question', 'private answer')
        raw = self.raw('jarvis:history')
        snap = j.snapshot()
        self.assertTrue(seal.is_sealed(snap['private_data']['values']['history']))
        self.assertEqual(self.raw('jarvis:history'), raw)

    def test_boot_requires_exact_opt_in_and_is_idempotent(self):
        with self.key(''): j.phase_a_remember_turn('tg:1', 'private question', 'private answer')
        with patch.dict(os.environ, {'SEAL_MIGRATE_KEY_FINGERPRINT': ''}):
            private.boot_migrate(j)
        self.assertIsInstance(self.raw('jarvis:history'), list)
        with patch.dict(os.environ, {'SEAL_MIGRATE_KEY_FINGERPRINT': 'wrong'}):
            with self.assertRaises(RuntimeError): private.boot_migrate(j)
        with patch.dict(os.environ, {'SEAL_MIGRATE_KEY_FINGERPRINT': seal.fingerprint()}):
            with patch.object(j, 'daily_backup', return_value=True) as backup:
                private.boot_migrate(j)
                raw = self.raw('jarvis:history')
                private.boot_migrate(j)
                self.assertEqual(self.raw('jarvis:history'), raw)
                self.assertEqual(backup.call_count, 2)
        self.assertTrue(seal.is_sealed(raw))


class RedisPrivateBackup(fixtures.RealRedis):
    def test_private_backup_migration_and_recovery_in_real_redis(self):
        self.clear_data()
        with patch.dict(os.environ, {'SEAL_MIGRATE_KEY_FINGERPRINT': seal.fingerprint()}):
            private.boot_migrate(j)
        saved = json.loads(self.r(['GET', 'jarvis:backup:' + j._today().isoformat()]))
        self.assertTrue(seal.is_sealed(saved['private_data']['values']['history']))
        original = j.kv_get('jarvis:history', [])
        self.r(['DEL', 'jarvis:history', 'jarvis:profile'])
        self.restart()
        j.restore_snapshot(saved, dry_run=False)
        self.assertEqual(j.kv_get('jarvis:history', []), original)
        self.assertEqual(len(j.phase_a_restore('tg:1')), 4)


def load_tests(loader, tests, pattern):
    # Run the new Redis case once; do not inherit and repeat the existing migration suite.
    return unittest.TestSuite([loader.loadTestsFromTestCase(PrivateBackup),
        RedisPrivateBackup('test_private_backup_migration_and_recovery_in_real_redis')])
