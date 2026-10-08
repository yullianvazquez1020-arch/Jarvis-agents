"""Cifrado 4.2: migración verificable del historial y del perfil a AES-256-GCM, sin perder ni pisar datos.

Cubre: migración (revisión y aplicación), clave incorrecta, datos dañados, fallo de almacenamiento, cambio
concurrente, recuperación tras reinicio, restauración del respaldo, reversión y diagnóstico de tres partes.
Archivos locales en todas; además, la parte de Upstash se repite contra un redis-server REAL (se omite si no
está instalado). Sin red, sin Telegram, sin dinero. Las claves son aleatorias y solo viven en la prueba.
"""
import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import test_jarvis as base
j = base.j
import jarvis_seal

H, P = "jarvis:history", "jarvis:profile"


def new_key():
    return base64.b64encode(os.urandom(32)).decode()


class Base(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True); j.conversations.clear(); j._locks.clear()
        j._seal_ok.clear(); j._seal_warned.clear(); j._seal_paused["on"] = False
        self.addCleanup(j._seal_paused.update, on=False)
        self.key_a = new_key()
        self.env = patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": self.key_a}); self.env.start()
        self.addCleanup(self.env.stop)

    def key(self, value):
        return patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": value})

    def raw(self, key):
        return j._kv_raw(key, None)

    def restart(self):
        """What a new process starts with: no caches, no chats in memory (data stays in storage)."""
        j._seal_ok.clear(); j._seal_warned.clear(); j._seal_paused["on"] = False
        j.conversations.clear(); j._locks.clear()

    def clear_data(self):
        """Data saved in clear by the code that ran before the key existed."""
        with self.key(""):
            j.phase_a_remember_turn("tg:1", "mi proyecto es IslaFix", "Anotado.")
            j.phase_a_remember_turn("tg:1", "secreto 4471", "Entendido.")
            j.kv_set(P, {"metas": ["cash flow"], "techo_usd": 80})
        self.assertEqual(jarvis_seal.inspect(self.raw(H)), "claro")
        return j.kv_get(H, []), j.kv_get(P, {})


class Fingerprint(Base):
    def test_public_fingerprint(self):
        fp = jarvis_seal.fingerprint()
        self.assertRegex(fp, r"^[0-9a-f]{8}$"); self.assertEqual(fp, jarvis_seal.fingerprint())
        self.assertNotIn(fp, base64.b64decode(self.key_a).hex())
        with self.key(new_key()):
            self.assertNotEqual(jarvis_seal.fingerprint(), fp)
        for value in ("", "no-es-base64!!"):
            with self.key(value):
                self.assertIsNone(jarvis_seal.fingerprint())

    def test_inspect_never_returns_content(self):
        token = jarvis_seal.seal({"t": "secreto"})
        self.assertEqual([jarvis_seal.inspect(v) for v in (None, [1], token)], ["vacio", "claro", "cifrado"])
        with self.key(new_key()):
            self.assertEqual(jarvis_seal.inspect(token), "ilegible")
        with self.key(""):
            self.assertEqual(jarvis_seal.inspect(token), "sin_llave")
        self.assertEqual(jarvis_seal.inspect(token[:-6] + "AAAAAA"), "ilegible")
        self.assertEqual(jarvis_seal.inspect("sealed:v1:%%%"), "ilegible")


class WrongKey(Base):
    """Before this patch a wrong key in Render made the next turn REPLACE the sealed history: it was lost."""
    def test_wrong_key_never_overwrites_and_original_key_still_opens(self):
        j.phase_a_remember_turn("tg:1", "dato importante", "ok")
        sealed = self.raw(H)
        with self.key(new_key()):
            self.assertEqual(j.kv_get(H, []), [])                                     # unreadable -> default
            with self.assertRaises(RuntimeError):
                j.phase_a_remember_turn("tg:1", "nuevo", "ok")
            asyncio.run(j._phase_a_remember_turn("tg:1", "nuevo", "ok"))              # the chat path never raises
            with self.assertRaises(RuntimeError):
                j.kv_set_many({H: [], j.B_KEY: {"income": [], "expenses": []}})      # all-or-nothing
            self.assertIn("ILEGIBLE", j.seal_status_text())
            j.add_income(7)                                                           # unrelated data still works
        self.assertEqual(self.raw(H), sealed)
        self.assertEqual(j.kv_get(H, [])[0]["text"], "dato importante")

    def test_mismatch_with_migration_key_is_reported(self):
        self.clear_data(); self.assertTrue(j.seal_migrate(apply=True)["ok"])
        fp_a = jarvis_seal.fingerprint()
        with self.key(new_key()):
            self.assertIn(f"otra clave (huella {fp_a})", j.seal_status_text())
            self.assertIn("pon esa clave en Render", j.seal_status_text())


class CorruptData(Base):
    def test_damaged_value_is_kept_and_reported(self):
        j.phase_a_remember_turn("tg:1", "hola", "ok")
        damaged = self.raw(H)[:-8] + "AAAAAAAA"
        j._atomic_file(j.DATA_DIR / "jarvis_history.json", json.dumps(damaged))
        self.assertEqual(j.kv_get(H, []), [])
        with self.assertRaises(RuntimeError):
            j.phase_a_remember_turn("tg:1", "otro", "ok")
        self.assertEqual(self.raw(H), damaged)
        r = j.seal_migrate(apply=True)
        self.assertEqual(next(x for x in r["rows"] if x["key"] == H)["after"], "ilegible")
        self.assertEqual(self.raw(H), damaged)                                        # migration never touches it


class GuardRegression(Base):
    def test_previously_read_value_cannot_hide_replaced_unreadable_data(self):
        j.kv_set(H, [{"text": "original"}])
        self.assertEqual(j.kv_get(H, []), [{"text": "original"}])
        with self.key(new_key()):
            foreign = jarvis_seal.seal([{"text": "keep me"}])
        j._atomic_file(j.DATA_DIR / "jarvis_history.json", json.dumps(foreign))
        with self.assertRaises(j.SealGuardError):
            j.kv_set(H, [])
        self.assertEqual(self.raw(H), foreign)

    def test_restore_with_invalid_key_never_writes_plaintext(self):
        self.clear_data()
        self.assertTrue(j.seal_migrate(apply=True)["ok"])
        before = {k: self.raw(k) for k in (H, P)}
        with self.key("invalid-key"):
            result = j.seal_restore_backup(force=True)
        self.assertFalse(result["ok"])
        self.assertEqual({k: self.raw(k) for k in (H, P)}, before)


class Migration(Base):
    def test_dry_run_changes_nothing(self):
        hist, prof = self.clear_data()
        before = {k: self.raw(k) for k in (H, P)}
        text = j.seal_command_text("revisar")
        self.assertIn("no cambié nada", text); self.assertIn("Se cifrarían: historial, perfil", text)
        self.assertNotIn("4471", text); self.assertNotIn("IslaFix", text)
        self.assertEqual({k: self.raw(k) for k in (H, P)}, before)
        self.assertIsNone(j._seal_side_get("backup", H))

    def test_apply_verifies_backs_up_and_keeps_other_data(self):
        hist, prof = self.clear_data()
        j.add_income(25)
        books = self.raw(j.B_KEY)
        r = j.seal_migrate(apply=True)
        self.assertTrue(r["ok"])
        rows = {x["key"]: x for x in r["rows"]}
        self.assertEqual((rows[H]["before"], rows[H]["after"], rows[H]["size"]), ("claro", "cifrado", 4))
        self.assertEqual(rows["jarvis:bio"]["after"], "vacio")
        for key, value in ((H, hist), (P, prof)):
            self.assertTrue(jarvis_seal.is_sealed(self.raw(key))); self.assertNotIn("4471", self.raw(key))
            self.assertEqual(j.kv_get(key, None), value)
            self.assertEqual(j._seal_side_get("backup", key)["value"], value)        # expiring clear copy
        self.assertIsNone(self.raw("jarvis:bio"))                                     # absent stays absent
        self.assertEqual(self.raw(j.B_KEY), books)                                    # books never sealed
        self.assertEqual(self.raw(j.SEAL_META_KEY)["fingerprint"], jarvis_seal.fingerprint())
        again = j.seal_migrate(apply=True)                                            # idempotent
        self.assertEqual({x["after"] for x in again["rows"]} - {"vacio"}, {"cifrado"})

    def test_turns_stay_atomic_after_migration(self):
        self.clear_data(); j.seal_migrate(apply=True)
        j.phase_a_remember_turn("tg:1", "tercera", "respuesta")
        roles = [x["role"] for x in j.kv_get(H, [])]
        self.assertEqual(roles, ["user", "assistant"] * 3)
        self.assertTrue(jarvis_seal.is_sealed(self.raw(H)))

    def test_refuses_without_valid_key(self):
        self.clear_data()
        for value, word in (("", "falta"), ("corta", "falta o es inválida")):
            with self.key(value):
                r = j.seal_migrate(apply=True)
                self.assertFalse(r["ok"]); self.assertIn(word, r["error"])
        self.assertEqual(jarvis_seal.inspect(self.raw(H)), "claro")

    def test_skips_data_sealed_with_another_key(self):
        other = new_key()
        with self.key(other):
            j.phase_a_remember_turn("tg:1", "de otra clave", "ok")
        foreign = self.raw(H)
        with self.key(""):
            j.kv_set(P, {"techo_usd": 50})
        self.assertFalse(j.seal_migrate(apply=True)["ok"])                             # refused by default
        r = j.seal_migrate(apply=True, force=True)                                    # owner insists
        rows = {x["key"]: x for x in r["rows"]}
        self.assertEqual((rows[H]["after"], rows[P]["after"]), ("ilegible", "cifrado"))
        self.assertEqual(self.raw(H), foreign)
        with self.key(other):
            self.assertEqual(j.kv_get(H, [])[0]["text"], "de otra clave")


class StorageFailure(Base):
    def test_failed_write_keeps_clear_data_and_retry_works(self):
        hist, _ = self.clear_data()
        real = j._atomic_file
        def flaky(path, text):
            if path.name == "jarvis_history.json":
                raise OSError("disk full")
            return real(path, text)
        with patch.object(j, "_atomic_file", side_effect=flaky):
            r = j.seal_migrate(apply=True)
            self.assertIn("Migración incompleta", j.seal_command_text("migrar"))
        self.assertFalse(r["ok"])
        row = next(x for x in r["rows"] if x["key"] == H)
        self.assertEqual(row["after"], "error"); self.assertIn("disk full", row["error"])
        self.assertEqual(j.kv_get(H, []), hist)                                       # still there, in clear
        self.assertIsNone(self.raw(j.SEAL_META_KEY))                                  # incomplete: no meta
        self.assertTrue(j.seal_migrate(apply=True)["ok"])                              # retry
        self.assertEqual(j.kv_get(H, []), hist)

    def test_failed_backup_writes_nothing(self):
        hist, _ = self.clear_data()
        with patch.object(j, "_seal_side_put", side_effect=OSError("no space")):
            r = j.seal_migrate(apply=True)
        self.assertFalse(r["ok"])
        self.assertEqual(jarvis_seal.inspect(self.raw(H)), "claro"); self.assertEqual(j.kv_get(H, []), hist)

    def test_turn_saved_meanwhile_is_never_lost(self):
        """Compare-and-set: if the history changes between the read and the write, nothing is written."""
        hist, _ = self.clear_data()
        real_seal = jarvis_seal.seal
        def seal_and_race(obj):
            if isinstance(obj, list) and len(obj) == 4:                             # the history, mid-migration
                j._atomic_file(j.DATA_DIR / "jarvis_history.json", json.dumps(obj + [{"role": "user", "text": "x"}]))
            return real_seal(obj)
        with patch.object(jarvis_seal, "seal", side_effect=seal_and_race):
            r = j.seal_migrate(apply=True)
        self.assertIn("cambió", next(x for x in r["rows"] if x["key"] == H)["error"])
        self.assertEqual(len(j.kv_get(H, [])), 5)                                      # the new turn is kept
        self.assertTrue(j.seal_migrate(apply=True)["ok"]); self.assertEqual(len(j.kv_get(H, [])), 5)

    def test_read_only_channel_cannot_migrate(self):
        self.clear_data()
        token = j._WRITE_BLOCK.set("voice")
        try:
            with self.assertRaises(j.ReadOnlyViolation):
                j.seal_migrate(apply=True)
        finally:
            j._WRITE_BLOCK.reset(token)
        self.assertEqual(jarvis_seal.inspect(self.raw(H)), "claro")


class Restart(Base):
    def test_history_survives_restart_and_restores(self):
        self.clear_data(); self.assertTrue(j.seal_migrate(apply=True)["ok"])
        self.restart()
        turns = j.phase_a_restore("tg:1")
        self.assertEqual([t["role"] for t in turns], ["user", "assistant", "user", "assistant"])
        self.assertIn("IslaFix", turns[0]["content"])
        j.phase_a_remember_turn("tg:1", "después del reinicio", "ok")
        self.assertTrue(jarvis_seal.is_sealed(self.raw(H))); self.assertEqual(len(j.kv_get(H, [])), 6)

    def test_restart_with_wrong_key_keeps_data_until_key_is_back(self):
        self.clear_data(); j.seal_migrate(apply=True)
        sealed = self.raw(H)
        self.restart()
        with self.key(new_key()):
            self.assertEqual(j.phase_a_restore("tg:1"), [])
            asyncio.run(j._phase_a_remember_turn("tg:1", "x", "y"))
        self.restart()
        self.assertEqual(self.raw(H), sealed); self.assertEqual(len(j.phase_a_restore("tg:1")), 4)


class RecoveryAndRollback(Base):
    def test_restore_never_drops_newer_readable_data_without_forzar(self):
        """Review #1: restore used to silently replace newer turns with the older backup."""
        self.clear_data(); j.seal_migrate(apply=True)
        for i in range(3):
            j.phase_a_remember_turn("tg:1", f"nuevo {i}", "ok")
        r = j.seal_restore_backup()
        self.assertFalse(r["ok"]); self.assertIn("forzar", r["rows"][0]["error"])
        self.assertEqual(len(j.kv_get(H, [])), 10)                                    # untouched
        r = j.seal_restore_backup(force=True)
        self.assertTrue(r["ok"]); self.assertEqual(len(j.kv_get(H, [])), 4)
        copy = j._seal_quarantine_list(H)[0][1]
        self.assertEqual(len(jarvis_seal.open_seal(copy["raw"])), 10)                 # the newer 10 rows kept

    def test_wrong_key_restore_is_refused_and_recuperar_brings_newest_back(self):
        """Review #2: with a wrong key, restore is the wrong tool; dated copies are never overwritten."""
        hist, prof = self.clear_data(); j.seal_migrate(apply=True)
        j.phase_a_remember_turn("tg:1", "el más nuevo", "ok")
        newest = j.kv_get(H, [])
        key_b = new_key()
        with self.key(key_b):
            r = j.seal_restore_backup()
            self.assertIn("parece otra clave", r["rows"][0]["error"])
            self.assertEqual(j.seal_restore_backup(force=True)["ok"], True)          # owner insists
        # back to key A: history is now B-sealed (unreadable); a second forced restore must not lose the A copy
        self.assertEqual(j.kv_get(H, []), [])
        self.assertTrue(j.seal_restore_backup(force=True)["ok"])
        self.assertGreaterEqual(len(j._seal_quarantine_list(H)), 2)
        r = j.seal_recover_quarantine()                                               # readable now: refused
        self.assertFalse(r["ok"]); self.assertIn("forzar", r["rows"][0]["error"])
        r = j.seal_recover_quarantine(force=True)                                     # newest copy that A opens
        self.assertTrue(r["ok"]); self.assertEqual(j.kv_get(H, []), newest)
        r = j.seal_recover_quarantine()                                               # readable: refused again
        self.assertFalse(r["ok"]); self.assertEqual(j.kv_get(H, []), newest)

    def test_restore_without_key_puts_clear_back(self):
        hist, _ = self.clear_data(); j.seal_migrate(apply=True)
        with self.key(""):
            self.assertTrue(j.seal_restore_backup()["ok"])
            self.assertEqual(self.raw(H), hist)
            j.phase_a_remember_turn("tg:1", "sin clave", "ok")                       # chat keeps saving in clear
        self.assertEqual(len(j.kv_get(H, [])), 6)
        self.assertEqual(len(j._seal_quarantine_list(H)), 1)                          # the sealed one is kept

    def test_backup_expires_and_local_plaintext_is_deleted(self):
        self.clear_data(); j.seal_migrate(apply=True)
        path = j._seal_side_path(j._seal_side_name("backup", H))
        self.assertTrue(path.exists())
        later = j._now() + j.datetime.timedelta(hours=j.SEAL_BACKUP_HOURS + 1)
        with patch.object(j, "_now", return_value=later):
            self.assertIsNone(j._seal_side_get("backup", H))
            self.assertIn("no hay respaldo vigente", j.seal_command_text("restaurar"))
        self.assertFalse(path.exists())                                               # review #8

    def test_revert_to_clear_and_pause(self):
        hist, prof = self.clear_data(); j.seal_migrate(apply=True)
        r = j.seal_revert()
        self.assertTrue(r["ok"]); self.assertTrue(j._seal_paused["on"])
        self.assertEqual((self.raw(H), self.raw(P)), (hist, prof))
        j.phase_a_remember_turn("tg:1", "en pausa", "ok")
        self.assertEqual(jarvis_seal.inspect(self.raw(H)), "claro")
        self.assertIn("en pausa", j.seal_status_text())
        self.assertFalse(j.seal_migrate(apply=True)["ok"])
        self.restart()                                                                # restarted with key still set
        j.phase_a_remember_turn("tg:1", "otra vez", "ok")
        self.assertTrue(jarvis_seal.is_sealed(self.raw(H)))                           # sealed again, readable
        self.assertEqual(len(j.kv_get(H, [])), 8)

    def test_revert_reports_data_that_stays_sealed(self):
        """Review #9."""
        with self.key(new_key()):
            j.phase_a_remember_turn("tg:1", "de otra clave", "ok")
        r = j.seal_revert()
        self.assertFalse(r["ok"]); self.assertIn("siguen cifrados", j.seal_command_text("revertir"))

    def test_clean_backups(self):
        self.clear_data(); j.seal_migrate(apply=True)
        self.assertIn("Borré 2", j.seal_command_text("limpiar"))
        self.assertIsNone(j._seal_side_get("backup", H))
        self.assertIn("No había", j.seal_command_text("limpiar"))


class ReviewFindings(Base):
    def test_migrate_with_wrong_key_changes_nothing(self):
        """Review #3: it used to rewrite the metadata and hide the 'other key' warning."""
        self.clear_data(); j.seal_migrate(apply=True)
        meta = self.raw(j.SEAL_META_KEY)
        with self.key(""):
            j.kv_set("jarvis:diary", ["en claro"])
        key_b = new_key()
        with self.key(key_b):
            r = j.seal_migrate(apply=True)
            self.assertFalse(r["ok"]); self.assertIn("otra clave", r["error"])
            self.assertEqual(self.raw("jarvis:diary"), ["en claro"])                 # not sealed with B
            self.assertEqual(self.raw(j.SEAL_META_KEY), meta)
            self.assertIn("pon esa clave en Render", j.seal_status_text())
            self.assertNotIn("Pendiente", j.seal_status_text())
            self.assertIn("No cambié nada", j.seal_command_text("migrar"))

    def test_unreadable_data_blocks_migration_unless_forced(self):
        with self.key(new_key()):
            j.phase_a_remember_turn("tg:1", "otra clave", "ok")
        with self.key(""):
            j.kv_set(P, {"techo_usd": 40})
        r = j.seal_migrate(apply=True)
        self.assertFalse(r["ok"]); self.assertIn("otra clave", r["error"])
        self.assertEqual(self.raw(P), {"techo_usd": 40})
        r = j.seal_migrate(apply=True, force=True)
        self.assertTrue(jarvis_seal.is_sealed(self.raw(P)))

    def test_first_implicit_seal_also_takes_a_backup(self):
        """Review #4: a normal save with the key set used to seal clear data with no safety copy."""
        hist, _ = self.clear_data()
        j.phase_a_remember_turn("tg:1", "con clave", "ok")
        self.assertTrue(jarvis_seal.is_sealed(self.raw(H)))
        self.assertEqual(j._seal_side_get("backup", H)["value"], hist)

    def test_descartar_lets_history_save_again_and_chat_is_told_once(self):
        """Review #5: unreadable data blocked history forever with only a log line."""
        with self.key(new_key()):
            j.phase_a_remember_turn("tg:1", "otra clave", "ok")
        foreign = self.raw(H)
        j._seal_notice["sent"] = False; self.addCleanup(j._seal_notice.update, sent=False)
        first = asyncio.run(j.run("tg:1", "hola"))
        second = asyncio.run(j.run("tg:1", "gracias"))
        self.assertIn("No guardé esta conversación", first); self.assertNotIn("No guardé", second)
        r = j.seal_discard_unreadable()
        self.assertTrue(r["ok"]); self.assertIsNone(self.raw(H))
        self.assertEqual(j._seal_quarantine_list(H)[0][1]["raw"], foreign)
        j.phase_a_remember_turn("tg:1", "otra vez", "ok")
        self.assertEqual(len(j.kv_get(H, [])), 2)
        self.assertIn("no hay datos ilegibles", j.seal_command_text("descartar"))

    def test_auto_sealed_data_records_its_key_so_wrong_key_is_detected(self):
        """Round 2 N1: data sealed by a normal save (no migration) also protects against a wrong key."""
        j.phase_a_remember_turn("tg:1", "auto", "ok")
        fp_a = jarvis_seal.fingerprint()
        self.assertEqual(self.raw(j.SEAL_META_KEY)["fingerprint"], fp_a)
        with self.key(new_key()):
            r = j.seal_restore_backup()
            self.assertEqual(r["error"], "no hay respaldo vigente")                   # nothing to restore, untouched
            self.assertIn(f"otra clave (huella {fp_a})", j.seal_status_text())

    def test_unreadable_without_recorded_key_needs_forzar(self):
        self.clear_data(); j.seal_migrate(apply=True)
        j._atomic_file(j.DATA_DIR / "jarvis_seal_meta.json", "null")                 # no recorded key
        with self.key(new_key()):
            r = j.seal_restore_backup()
            self.assertIn("no hay huella registrada", r["rows"][0]["error"])
        self.assertEqual(jarvis_seal.inspect(self.raw(H)), "cifrado")

    def test_quarantine_copies_are_sealed_or_short_lived(self):
        """Round 2 N2: replaced clear data never sits in clear for 30 days."""
        self.clear_data(); j.seal_migrate(apply=True); j.seal_revert()
        j.phase_a_remember_turn("tg:1", "clave 9999", "ok")                           # clear while paused
        self.restart()
        j.seal_restore_backup(force=True)                                             # key set: copy is sealed
        stamp, copy = j._seal_quarantine_list(H)[0]
        self.assertTrue(jarvis_seal.is_sealed(copy["raw"])); self.assertFalse(copy["clear"])
        self.assertNotIn("9999", json.dumps(copy))
        with self.key(""):
            j.seal_restore_backup(force=True)                                         # replaces sealed: copy sealed
            self.assertFalse(j._seal_quarantine_list(H)[0][1]["clear"])
            j.seal_restore_backup(force=True)                                         # replaces clear, no key: 72 h
            stamp, copy = j._seal_quarantine_list(H)[0]
            self.assertEqual(j._seal_qindex(H)[-1]["clear"], True)
            self.assertTrue(copy["clear"])
            self.assertIn("en claro", j.seal_status_text())
            self.assertIn("Borré", j.seal_command_text("limpiar"))
            self.assertFalse(any(c["clear"] for _, c in j._seal_quarantine_list(H)))
        self.assertGreaterEqual(len(j._seal_quarantine_list(H)), 1)                  # sealed copies stay

    def test_quarantine_is_capped(self):
        self.clear_data(); j.seal_migrate(apply=True)
        for _ in range(j.SEAL_QUARANTINE_MAX + 3):
            j.seal_restore_backup(force=True)
        self.assertEqual(len(j._seal_quarantine_list(H)), j.SEAL_QUARANTINE_MAX)
        self.assertEqual(len(list(j.DATA_DIR.glob("jarvis_seal_quarantine_jarvis_history_*.json"))),
                         j.SEAL_QUARANTINE_MAX)

    def test_backup_failure_does_not_cost_the_turn(self):
        """Round 2 N4."""
        self.clear_data()
        with patch.object(j, "_seal_side_put", side_effect=OSError("no space")):
            j.phase_a_remember_turn("tg:1", "se guarda igual", "ok")
        self.assertEqual(j.kv_get(H, [])[-2]["text"], "se guarda igual")

    def test_partial_restore_is_not_reported_as_success(self):
        """Round 2 N5."""
        self.clear_data(); j.seal_migrate(apply=True)
        raw = self.raw(P)
        j._atomic_file(j.DATA_DIR / "jarvis_profile.json", json.dumps(raw[:-8] + "AAAAAAAA"))   # profile damaged
        r = j.seal_restore_backup()                                                   # history readable: refused
        self.assertFalse(r["ok"]); self.assertEqual(j.kv_get(P, None), {"metas": ["cash flow"], "techo_usd": 80})
        self.assertIn("No restauré todo", j.seal_command_text("restaurar"))

    def test_notice_comes_back_after_a_successful_save(self):
        """Round 2 N6."""
        j._seal_notice["sent"] = False; self.addCleanup(j._seal_notice.update, sent=False)
        with self.key(new_key()):
            j.phase_a_remember_turn("tg:1", "otra", "ok")
        self.assertIn("No guardé", asyncio.run(j.run("tg:1", "hola")))
        j.seal_discard_unreadable()
        self.assertNotIn("No guardé", asyncio.run(j.run("tg:1", "hola")))            # saved: re-armed
        with self.key(new_key()):
            self.assertIn("No guardé", asyncio.run(j.run("tg:1", "gracias")))

    def test_lost_key_steps_from_the_doc_never_strand_history(self):
        """Round 3 X1: descartar under B, chat, key A found -> recuperar; back to B -> recuperar brings B's history."""
        key_a, key_b = self.key_a, new_key()
        j.phase_a_remember_turn("tg:1", "con A", "ok")
        with self.key(key_b):
            self.assertTrue(j.seal_discard_unreadable()["ok"])
            j.phase_a_remember_turn("tg:1", "con B", "ok")
            b_history = j.kv_get(H, [])
        r = j.seal_recover_quarantine()                                               # A again: B data unreadable
        self.assertTrue(r["ok"]); self.assertEqual(j.kv_get(H, [])[0]["text"], "con A")
        with self.key(key_b):
            r = j.seal_recover_quarantine()                                           # B's history is reachable
            self.assertTrue(r["ok"], r); self.assertEqual(j.kv_get(H, []), b_history)

    def test_deliberate_key_change_moves_the_recorded_key(self):
        """Round 3 X2."""
        j.phase_a_remember_turn("tg:1", "con A", "ok")
        fp_a = jarvis_seal.fingerprint()
        with self.key(new_key()):
            fp_b = jarvis_seal.fingerprint()
            j.seal_discard_unreadable()
            meta = self.raw(j.SEAL_META_KEY)
            self.assertEqual((meta["fingerprint"], meta["previous_fingerprint"]), (fp_b, fp_a))
            self.assertNotIn("otra clave", j.seal_status_text())

    def test_prune_never_drops_copies_this_key_cannot_open(self):
        """Round 3 X3: the A-sealed real data survives many forced operations under a wrong key B."""
        self.clear_data(); j.seal_migrate(apply=True)
        real = self.raw(H)
        with self.key(new_key()):
            for _ in range(j.SEAL_QUARANTINE_MAX + 3):
                j.seal_restore_backup(force=True)
            raws = [c["raw"] for _, c in j._seal_quarantine_list(H)]
        self.assertIn(real, raws)
        r = j.seal_recover_quarantine(force=False)                                    # with A: unreadable B data
        self.assertTrue(r["ok"]); self.assertEqual(self.raw(H) == real or jarvis_seal.inspect(self.raw(H)), "cifrado")

    def test_status_ignores_expired_copies(self):
        """Round 3 X4."""
        self.clear_data(); j.seal_migrate(apply=True)
        with self.key(""):
            j.seal_restore_backup(force=True); j.seal_restore_backup(force=True)      # one sealed + one clear copy
        later = j._now() + j.datetime.timedelta(hours=j.SEAL_BACKUP_HOURS + 1)
        with patch.object(j, "_now", return_value=later):
            rep = j.seal_report()
        self.assertEqual((rep["quarantine"], rep["quarantine_clear"]), (2, 0))      # history + profile, sealed

    def test_failed_restore_write_keeps_every_copy(self):
        """Round 3 X5: pruning happens only after the main write succeeded."""
        self.clear_data(); j.seal_migrate(apply=True)
        for _ in range(j.SEAL_QUARANTINE_MAX):
            j.seal_restore_backup(force=True)
        with patch.object(j, "_seal_cas", side_effect=RuntimeError("cambió")):
            self.assertFalse(j.seal_restore_backup(force=True)["ok"])
        self.assertEqual(len(j._seal_quarantine_list(H)), j.SEAL_QUARANTINE_MAX + 1)
        with patch.object(j, "_seal_side_put", wraps=j._seal_side_put) as put:
            j.seal_restore_backup(force=True)
        kinds = [c.args[0] for c in put.call_args_list]
        self.assertLess(kinds.index("qindex"), kinds.index("quarantine"))            # index before copy
        self.assertEqual(len(j._seal_quarantine_list(H)), j.SEAL_QUARANTINE_MAX)

    def test_key_not_recorded_while_other_data_is_unreadable(self):
        """Round 3 X6."""
        with self.key(new_key()):
            j.phase_a_remember_turn("tg:1", "con otra", "ok")
        j._atomic_file(j.DATA_DIR / "jarvis_seal_meta.json", "null")
        j.kv_set(P, {"techo_usd": 10})                                                # first write of another key
        self.assertIsNone(self.raw(j.SEAL_META_KEY))

    def test_module_missing_still_reports_sealed_data(self):
        """Review #6."""
        j.phase_a_remember_turn("tg:1", "hola", "ok")
        with patch.dict(sys.modules, {"jarvis_seal": None}):
            text = j.seal_status_text()
        self.assertIn("código no disponible", text); self.assertIn("historial cifrado (sin llave", text)

    def test_old_seal_module_without_inspect_still_guards(self):
        j.phase_a_remember_turn("tg:1", "hola", "ok")
        old = type(sys)("jarvis_seal_old")
        for name in ("SEALED_KEYS", "key_state", "is_sealed", "seal", "open_seal", "seal_value", "open_value",
                     "SealError"):
            setattr(old, name, getattr(jarvis_seal, name))
        j._seal_ok.clear()
        with patch.dict(sys.modules, {"jarvis_seal": old}), self.key(new_key()):
            with self.assertRaises(j.SealGuardError):
                j.kv_set(H, [])


class Diagnostics(Base):
    """Three separate facts: code available, key configured, data actually encrypted."""
    def test_states(self):
        with patch.dict(sys.modules, {"jarvis_seal": None}):
            self.assertIn("código no disponible", j.seal_status_text())
        with self.key(""):
            self.assertIn("sin clave", j.seal_status_text())
        with self.key("corta"):
            self.assertIn("clave inválida", j.seal_status_text())
        self.assertIn("historial vacío", j.seal_status_text())
        self.clear_data()
        text = j.seal_status_text()
        self.assertIn(f"clave configurada (huella {jarvis_seal.fingerprint()})", text)
        self.assertIn("historial en claro", text); self.assertIn("Pendiente", text)
        j.seal_migrate(apply=True)
        text = j.seal_status_text()
        self.assertIn("historial cifrado", text); self.assertIn("perfil cifrado", text)
        self.assertIn("Respaldo previo en claro", text); self.assertNotIn("Pendiente", text)
        self.assertNotIn(self.key_a, text)
        j.TG_TOKEN = ""
        self.assertIn("Cifrado: código disponible", asyncio.run(j.diagnostics_text()))

    def test_command_is_private_and_shows_no_content(self):
        self.assertIn("/cifrado", j.PRIVATE_COMMANDS)
        self.clear_data()
        for sub in ("", "revisar", "migrar", "restaurar", "limpiar", "revertir", "otra"):
            text = j.seal_command_text(sub)
            for secret in ("4471", "IslaFix", self.key_a):
                self.assertNotIn(secret, text)

    def test_money_limits_unchanged(self):
        self.assertEqual((j.HARD_MAX_ORDER_USD, j.HARD_MAX_DAY_USD), (100.0, 300.0))


@unittest.skipUnless(shutil.which("redis-server"), "redis-server not installed")
class RealRedis(Base):
    """Same migration through Upstash's code path (EVAL fencing, SET EX), on a real local redis-server."""
    @classmethod
    def setUpClass(cls):
        from test_redis_lua import Resp
        s = socket.socket(); s.bind(("127.0.0.1", 0)); cls.port = s.getsockname()[1]; s.close()
        cls.dir = tempfile.mkdtemp()
        cls.proc = subprocess.Popen(["redis-server", "--port", str(cls.port), "--save", "", "--appendonly", "no",
                                     "--dir", cls.dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                cls.r = Resp(cls.port); cls.r(["PING"]); break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("redis-server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.r.sock.close(); cls.proc.terminate(); cls.proc.wait(5)

    def setUp(self):
        super().setUp()
        self.r(["FLUSHALL"])
        p = patch.object(j, "_redis", new=self.r); p.start(); self.addCleanup(p.stop)
        j.USE_REDIS = True; self.addCleanup(setattr, j, "USE_REDIS", False)
        j.fence_take_leadership()
        self.addCleanup(j._fence.update, mode="off", leader=True)

    def test_migration_restart_and_fencing(self):
        hist, prof = self.clear_data()
        r = j.seal_migrate(apply=True)
        self.assertTrue(r["ok"], r)
        self.assertTrue(jarvis_seal.is_sealed(json.loads(self.r(["GET", H]))))
        ttl = self.r(["TTL", "jarvis:seal:backup:" + H])
        self.assertTrue(0 < ttl <= j.SEAL_BACKUP_HOURS * 3600)
        self.restart()
        self.assertEqual(j.kv_get(H, []), hist); self.assertEqual(len(j.phase_a_restore("tg:1")), 4)
        # compare-and-set refuses a value that changed
        self.r(["SET", P, json.dumps({"techo_usd": 1})])
        with self.assertRaises(RuntimeError):
            j._seal_cas(P, json.dumps(prof), json.dumps({"x": 1}))
        # a newer instance took over: this one writes nothing
        self.r(["SET", j.LEADER_KEY, "otra-instancia"])
        before = self.r(["GET", H])
        with self.assertRaises(j.StaleInstance):
            j._seal_cas(H, before, json.dumps([]))
        self.assertEqual(self.r(["GET", H]), before)

    def test_wrong_key_never_overwrites_in_redis(self):
        j.phase_a_remember_turn("tg:1", "en upstash", "ok")
        sealed = self.r(["GET", H])
        with self.key(new_key()):
            asyncio.run(j._phase_a_remember_turn("tg:1", "nuevo", "ok"))
        self.assertEqual(self.r(["GET", H]), sealed)

    def test_clean_deletes_backup(self):
        self.clear_data(); j.seal_migrate(apply=True)
        self.assertIn("Borré 2", j.seal_command_text("limpiar"))
        self.assertIsNone(self.r(["GET", "jarvis:seal:backup:" + H]))

    def test_race_and_non_ascii_through_migrate(self):
        with self.key(""):
            j.phase_a_remember_turn("tg:1", "año, señal, acción — ñandú ✓", "sí")
        real_seal = jarvis_seal.seal
        def seal_and_race(obj):
            if isinstance(obj, list):
                self.r(["SET", H, json.dumps(obj + [{"role": "user", "text": "carrera"}], ensure_ascii=False)])
            return real_seal(obj)
        with patch.object(jarvis_seal, "seal", side_effect=seal_and_race):
            r = j.seal_migrate(apply=True)
        self.assertIn("cambió", next(x for x in r["rows"] if x["key"] == H)["error"])
        self.assertEqual(len(j.kv_get(H, [])), 3)
        self.assertTrue(j.seal_migrate(apply=True)["ok"])
        self.restart()
        self.assertEqual(j.kv_get(H, [])[0]["text"], "año, señal, acción — ñandú ✓")

    def test_quarantine_is_fenced_and_never_overwritten(self):
        self.clear_data(); j.seal_migrate(apply=True)
        with self.key(new_key()):
            j.seal_restore_backup(force=True); j.seal_restore_backup(force=True)
            self.assertEqual(len(j._seal_quarantine_list(H)), 2)
        self.r(["SET", j.LEADER_KEY, "otra-instancia"])
        with self.assertRaises(j.StaleInstance):
            j._seal_quarantine(H, "x", "prueba")
        with self.assertRaises(j.StaleInstance):
            j._seal_side_del("backup", H)


if __name__ == "__main__":
    unittest.main()
