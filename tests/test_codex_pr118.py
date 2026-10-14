"""Arreglos de la revisión Codex PR #118 (datos ficticios, sin red)."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
import app as desk                      # noqa: E402
import mouse_autonomo as ma             # noqa: E402


class CicloEnv(unittest.TestCase):
    def test_voice_ciclo_y_dir_desde_entorno(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"VOICE_CICLO": "false", "VOICE_CICLO_DIR": d}):
            cfg = desk.load_config(path=str(Path(d) / "no-existe.env"))
        self.assertEqual(cfg["VOICE_CICLO"], "false")
        self.assertEqual(cfg["VOICE_CICLO_DIR"], d)


class FakeProc:
    vivos = []

    def __init__(self, cmd, **kw):
        self.cmd = cmd; self.done = threading.Event(); FakeProc.vivos.append(self)

    def poll(self):
        return 0 if self.done.is_set() else None

    def wait(self, timeout=None):
        if not self.done.wait(timeout):
            raise desk.subprocess.TimeoutExpired(self.cmd, timeout)

    def terminate(self):
        self.done.set()

    kill = terminate


class VozLocal(unittest.TestCase):
    def make(self, d):
        c = desk.Companion.__new__(desk.Companion)
        c.cfg = {"VOICE_SERVER_PLAYBACK": "auto"}; c.home = Path(d)
        return c

    def test_cola_serializa_y_stop_corta(self):
        FakeProc.vivos = []
        with tempfile.TemporaryDirectory() as d, patch.object(desk, "local_player", return_value=["fakeplay"]), \
                patch.object(desk.subprocess, "Popen", FakeProc):
            c = self.make(d)
            c._play_local(b"RIFF1"); c._play_local(b"RIFF2"); c._play_local(b"RIFF3")
            time.sleep(0.3)
            self.assertEqual(len(FakeProc.vivos), 1)          # una sola frase sonando, sin solapes
            c.stop_local_audio()                                # stop: corta y descarta la cola
            time.sleep(0.3)
            self.assertTrue(FakeProc.vivos[0].done.is_set())
            self.assertEqual(len(FakeProc.vivos), 1)
            c._play_local(b"RIFF4"); time.sleep(0.3)
            self.assertEqual(len(FakeProc.vivos), 2)
            c.stop_local_audio()


class OrdenAtomica(unittest.TestCase):
    def test_siguiente_json_atomico_y_unico(self):
        with tempfile.TemporaryDirectory() as d:
            ses = {"agent": "jarvis"}
            with patch.object(ma.ae, "stopped", return_value=False), patch.object(ma.auto, "read_session", return_value=ses), \
                    patch.object(ma.auto, "auto_dir", return_value=Path(d)), patch.object(ma, "precheck", return_value=None), \
                    patch.object(ma.os, "replace", wraps=os.replace) as rep:
                res = []
                hs = [threading.Thread(target=lambda: res.append(ma.encargar({"action": "abrir", "url": "https://example.com"})))
                      for _ in range(8)]
                [h.start() for h in hs]; [h.join() for h in hs]
            self.assertEqual(sum(r["ok"] for r in res), 1)
            self.assertTrue(rep.called)
            self.assertEqual(json.loads((Path(d) / "siguiente.json").read_text())["action"], "abrir")
            self.assertEqual([p.name for p in Path(d).iterdir()], ["siguiente.json"])


class VozAlan(unittest.TestCase):
    def test_length_scale_y_sin_voz_femenina(self):
        from audio import engines
        self.assertEqual(engines.Piper("piper", "x.onnx").length_scale, 1.18)
        self.assertEqual(engines.DANIEL_WPM, 165)
        cfg = {"JARVIS_REPLY_LANGUAGE": "en-GB", "VOICE_TTS_VOICE": "Samantha", "VOICE_TTS_BACKEND": "none"}
        self.assertTrue(engines.is_female_en("Samantha")); self.assertFalse(engines.is_female_en("Daniel"))
        self.assertFalse(engines.is_female_en("/x/en_GB-alan-medium.onnx"))
        engines.build(cfg)                                   # no debe fallar; la voz femenina se descarta



class RayosObjetivo(unittest.TestCase):
    def test_temas_de_voz_solo_etiquetas(self):
        self.assertEqual(desk.speech_topics("Sir, BTC is up and Ethereum is flat"), ["BTC", "ETH"])
        self.assertEqual(desk.speech_topics("Todo en orden"), [])
        js = (Path(__file__).resolve().parents[1] / "desktop/ui/torre-cine.js").read_text("utf-8")
        for k in ("raysMode", "cripto", "negocio", "jarvis-rayos", "drawBeam", "speaking_topics", "uLvl", "updReactor", "bezel", "updBolts", "DEMO", "boltR"):
            self.assertIn(k, js, k)
        neg = (Path(__file__).resolve().parents[1] / "desktop/ui/negocios.js").read_text("utf-8")
        self.assertIn("data-negocio", neg); self.assertIn("data-cripto", neg); self.assertIn("jarvis-scan", neg)


if __name__ == "__main__":
    unittest.main()
