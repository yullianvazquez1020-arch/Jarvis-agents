"""Puente Jarvis -> LaunchAgent del mouse: el pedido del display llega al agente y mueve el puntero (falso)."""
import json
import os
import sys
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from test_agent_executor import Base, ae, quiet

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
import mouse_autonomo as ma  # noqa: E402


class NotesPointer:
    def __init__(self, front="Notes"):
        self.calls, self.front = [], front

    def frontmost(self):
        return self.front

    def page_url(self):
        return ""

    def __getattr__(self, name):
        return lambda *a, **k: self.calls.append((name,) + a)


class Puente(Base):
    def latido(self, edad=0):
        (self.dir / "autonomo.json").write_text(json.dumps(
            {"latido": ae.stamp(ae.now() - timedelta(seconds=edad)), "pid": 1}), encoding="utf-8")

    def correr(self, pointer):
        with patch.dict(os.environ, {"JARVIS_AUTONOMO": "1"}):
            quiet(ae.run_autonomo, pointer, ciclos=1, pausa=0)

    def test_sin_agente_explica(self):
        r = ma.encargar({"action": "move", "x": 400, "y": 300})
        self.assertFalse(r["ok"]); self.assertIn("instalar_mouse_autonomo", r["motivo"])

    def test_latido_viejo_no_vale(self):
        self.latido(edad=120)
        self.assertFalse(ma.encargar({"action": "move", "x": 400, "y": 300})["ok"])

    def test_move_llega_y_mueve(self):
        self.latido()
        r = ma.encargar({"action": "move", "x": 400, "y": 300})
        self.assertEqual(r, {"ok": True, "orden": "move", "via": "launchd"})
        self.assertTrue(ma.estado()["launchd"])
        p = NotesPointer(); self.correr(p)
        self.assertIn(("move", 400, 300), p.calls)

    def test_app_bloqueada_no_mueve(self):
        self.latido(); ma.encargar({"action": "move", "x": 400, "y": 300})
        p = NotesPointer("Mail"); self.correr(p)
        self.assertFalse(any(c[0] == "move" for c in p.calls))

    def test_agente_forzado_y_lista(self):
        self.latido()
        self.assertFalse(ma.encargar({"action": "hotkey", "keys": ["command", "q"]})["ok"])
        self.assertFalse(ma.encargar({"action": "open_app", "app": "Terminal"})["ok"])
        self.assertFalse(ma.encargar({"action": "move", "x": 1, "y": 1})["ok"])
        ma.encargar({"action": "move", "x": 50, "y": 60, "agent": "claude"})
        row = json.loads((self.dir / "autonomo" / "entrada.jsonl").read_text().splitlines()[-1])
        self.assertEqual(row["agent"], "jarvis")

    def test_malformed_request_fails_cleanly(self):
        self.latido()
        for action in (None, [], "move", 1):
            self.assertEqual(ma.encargar(action), {"ok": False, "motivo": "accion"})

    def test_stop(self):
        self.latido(); (self.dir / "STOP").touch()
        self.assertFalse(ma.encargar({"action": "move", "x": 400, "y": 300})["ok"])


import importlib.util as _iu  # noqa: E402
_s = _iu.spec_from_file_location("mac_setup", Path(__file__).resolve().parents[1] / "scripts" / "mac_setup.py")
mac_setup = _iu.module_from_spec(_s); _s.loader.exec_module(mac_setup)


class Informe(Base):
    def test_sin_venv_no_miente(self):
        r = mac_setup.mouse_report(self.dir / "nada" / "python")
        self.assertIn("NO instalado", r); self.assertNotIn("concedida", r)

    def test_sin_quartz_ni_agente(self):
        py = self.dir / "python"; py.touch()
        class R:
            def __init__(s, out, rc=0): s.stdout, s.returncode = out, rc
        salidas = [R('{"python": "/x/python3.9", "modulos": false, "error": "No module named Quartz", "accesibilidad": false}'),
                   R("Could not find service", 113)]
        with patch.object(mac_setup.subprocess, "run", side_effect=lambda *a, **k: salidas.pop(0)):
            r = mac_setup.mouse_report(py, probar=True)
        self.assertIn("FALTAN", r); self.assertIn("NO —", r); self.assertIn("NO cargado", r)
        self.assertNotIn("FUNCIONA", r)
