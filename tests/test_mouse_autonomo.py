"""Modo mouse autónomo (opcional). Puntero falso y datos ficticios: aquí nunca se mueve el mouse."""
import json
import os
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from test_agent_executor import Base, Pointer, ae, quiet

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
import intents  # noqa: E402


class Autonomo(Base):
    def on(self):
        p = patch.dict(os.environ, {"JARVIS_AUTONOMO": "1"}); p.start(); self.addCleanup(p.stop)

    def old_session(self):
        (self.dir / "session.json").write_text(json.dumps(
            {"started": ae.stamp(ae.now() - timedelta(seconds=ae.SESSION_SECONDS + 60))}), encoding="utf-8")

    def test_default_mode_unchanged(self):
        self.assertFalse(ae.autonomo())
        self.old_session()
        self.assertFalse(ae.session_open())
        p = Pointer()
        rc, out = quiet(ae.run_actions, self.file([{"agent": "jarvis", "action": "move", "x": 5, "y": 5}]),
                        dry=False, libre=False, pointer=p, automatic=True)
        self.assertEqual(p.calls, []); self.assertNotEqual(rc, 0)
        self.assertEqual(quiet(ae.run_autonomo, p, ciclos=1)[0], 2)

    def test_no_expiry_in_autonomo(self):
        self.on(); self.old_session()
        self.assertTrue(ae.session_open())
        self.assertTrue((self.dir / "autonomo.json").exists())

    def test_allowlist_runs_without_approval(self):
        self.on(); p = Pointer()
        rows = [{"agent": "jarvis", "action": "move", "x": 10, "y": 20},
                {"agent": "jarvis", "action": "click", "x": 10, "y": 20},
                {"agent": "jarvis", "action": "type", "text": "nota ficticia"},
                {"agent": "jarvis", "action": "open_url", "url": "https://github.com/ejemplo"},
                {"agent": "jarvis", "action": "open_app", "app": "Notes"}]
        rc, _ = quiet(ae.run_actions, self.file(rows), dry=False, libre=False, pointer=p)
        self.assertEqual(rc, 0)
        self.assertEqual([c[0] for c in p.calls], ["move", "click", "write", "open_url", "open_app"])
        self.assertIsNone(ae.read_lock())

    def test_blocked_actions_still_refused(self):
        self.on(); p = Pointer()
        bad = [{"agent": "jarvis", "action": "open_url", "url": "https://www.1firstbank.com"},
               {"agent": "jarvis", "action": "open_app", "app": "Terminal"},
               {"agent": "jarvis", "action": "open_app", "app": "Mail"},
               {"agent": "jarvis", "action": "open_app", "app": "Finder"},
               {"agent": "jarvis", "action": "type", "text": "sudo rm -rf /tmp/ficticio"},
               {"agent": "jarvis", "action": "type", "text": "mi contrasena"},
               {"agent": "jarvis", "action": "type", "text": "hola", "enter": True},
               {"agent": "jarvis", "action": "hotkey", "keys": ["cmd", "backspace"]},
               {"agent": "jarvis", "action": "hotkey", "keys": ["cmd", "c"]},
               {"agent": "jarvis", "action": "open_url", "url": "https://ejemplo.invalid"},
               {"agent": "jarvis", "action": "open_app", "app": "Calculator"}]
        for row in bad:
            self.assertFalse(ae.auto_ok(row), row)
            quiet(ae.release_lock, "yullian")
            quiet(ae.run_actions, self.file([row]), dry=False, libre=False, pointer=p, automatic=True)
        self.assertEqual(p.calls, [])
        self.assertEqual(ae.finish(bad[0], "autonomo", p), "BLOQUEADO")
        for frase in ("aprueba el pago", "envia el correo", "borra el archivo", "/confirmar 123456"):
            self.assertEqual(intents.parse(frase)[0], "refuse", frase)

    def test_stop_still_halts(self):
        self.on(); p = Pointer()
        (self.dir / "STOP").write_text("1")
        rc, _ = quiet(ae.run_actions, self.file([{"agent": "jarvis", "action": "move", "x": 1, "y": 1}]),
                      dry=False, libre=False, pointer=p)
        self.assertEqual(p.calls, []); self.assertNotEqual(rc, 0)
        carpeta = self.dir / "autonomo"; carpeta.mkdir(exist_ok=True)
        (carpeta / "entrada.jsonl").write_text(json.dumps({"agent": "jarvis", "action": "move", "x": 1, "y": 1}) + "\n")
        self.assertEqual(quiet(ae.run_autonomo, p, ciclos=1, pausa=0)[0], 0)
        self.assertEqual(p.calls, [])
        (self.dir / "STOP").unlink()
        quiet(ae.run_autonomo, p, ciclos=1, pausa=0)
        self.assertEqual(p.calls, [("move", 1, 1)])

    def test_voice_stop_creates_stop(self):
        for frase in ("para el mouse", "Jarvis, detén el ratón", "stop mouse"):
            self.assertEqual(intents.parse(frase)[0], "stop_mouse", frase)
        self.assertEqual(intents.parse("para")[0], "stop_audio")
        import app
        app._crear_stop_mouse()
        self.assertTrue((self.dir / "STOP").exists())
        self.assertTrue(ae.stopped())


if __name__ == "__main__":
    unittest.main()
