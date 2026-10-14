"""Voz automática, puente del mouse autónomo (simulado) y ciclo local: sin red, sin mouse real."""
import json, os, pathlib, sys, tempfile, unittest
from datetime import timedelta

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
_tmp = tempfile.mkdtemp()
os.environ["JARVIS_CONTROL_DIR"] = os.path.join(_tmp, "control")
os.environ["JARVIS_OWNER_DIR"] = os.path.join(_tmp, "owner")
import ciclo  # noqa: E402
import mouse_autonomo as ma  # noqa: E402
from audio import engines  # noqa: E402


class Voz(unittest.TestCase):
    def test_auto_elige_backend(self):
        cfg = {"VOICE_PIPER_BIN": "/x/piper", "VOICE_TTS_VOICE": "/x/v.onnx"}
        self.assertEqual(engines.pick_tts(cfg, platform="darwin", which=lambda c: c == "say"), "macos_say")
        self.assertEqual(engines.pick_tts(cfg, platform="linux", which=lambda c: None, exists=lambda p: True), "piper")
        self.assertEqual(engines.pick_tts(cfg, platform="linux", which=lambda c: None, exists=lambda p: False), "none")

    def test_alan_britanico_por_defecto(self):
        cfg = {"JARVIS_REPLY_LANGUAGE": "en-GB", "VOICE_PIPER_DIR": "/v"}
        self.assertEqual(engines.default_voice(cfg, exists=lambda p: p == "/v/" + engines.ALAN), "/v/" + engines.ALAN)
        self.assertEqual(engines.default_voice(dict(cfg, VOICE_TTS_VOICE="/x.onnx")), "/x.onnx")
        self.assertEqual(engines.default_voice({"JARVIS_REPLY_LANGUAGE": "es"}, exists=lambda p: True), "")
        import app
        self.assertEqual(app.DEFAULTS["JARVIS_REPLY_LANGUAGE"], "en-GB")

    def test_defaults_voz_encendida(self):
        import app
        self.assertEqual(app.DEFAULTS["VOICE_TTS_BACKEND"], "auto")
        self.assertEqual(app.DEFAULTS["VOICE_STARTUP_AUDIO"], "true")
        self.assertEqual(app.local_player(which=lambda c: None), None)
        self.assertEqual(app.local_player(which=lambda c: c == "afplay"), ["afplay"])


class Arranque(unittest.TestCase):
    def test_sonido_original_y_propio(self):
        import app
        p, ct = app.startup_sound({})
        self.assertEqual(p.name, "arranque.wav"); self.assertEqual(ct, "audio/wav"); self.assertTrue(p.is_file())
        own = pathlib.Path(tempfile.mkdtemp()) / "mio.mp3"; own.write_bytes(b"ID3fake")
        self.assertEqual(app.startup_sound({"JARVIS_STARTUP_SOUND": str(own)}), (own, "audio/mpeg"))
        self.assertEqual(app.startup_sound({"JARVIS_STARTUP_SOUND": "/no/existe.mp3"})[0].name, "arranque.wav")
        bad = own.with_suffix(".exe"); bad.write_bytes(b"x")
        self.assertEqual(app.startup_sound({"JARVIS_STARTUP_SOUND": str(bad)})[0].name, "arranque.wav")
        self.assertIn("arranque.js", (ROOT / "desktop/ui/index.html").read_text("utf-8"))
        import wave
        with wave.open(str(p)) as w:
            self.assertAlmostEqual(w.getnframes() / w.getframerate(), 5.2, places=1)


class Mouse(unittest.TestCase):
    def setUp(self):
        ma.auto.end_session(); (ma.ae.control_dir() / "STOP").unlink(missing_ok=True)
        (ma.auto.auto_dir() / "siguiente.json").unlink(missing_ok=True)

    def abrir(self):
        m = ma.ae.now()
        ma.auto.session_path().write_text(json.dumps({"agent": "jarvis", "started": ma.ae.stamp(m),
                                                      "expires": ma.ae.stamp(m + timedelta(minutes=5))}))

    def test_sin_sesion_no_encarga(self):
        self.assertFalse(ma.encargar({"action": "scroll", "amount": -3})["ok"])
        self.assertFalse(ma.estado()["sesion"])

    def test_reglas_y_stop(self):
        self.abrir()
        self.assertTrue(ma.encargar({"action": "screenshot"})["ok"])
        (ma.auto.auto_dir() / "siguiente.json").unlink()
        for bad in ({"action": "hotkey", "keys": ["cmd", "q"]}, {"action": "open_app", "app": "Terminal"},
                    {"action": "open_app", "app": "Finder"}, {"action": "click", "x": 1, "y": 1},
                    {"action": "open_url", "url": "https://www.bancopopular.com"}):
            self.assertFalse(ma.encargar(bad)["ok"], bad)
        (ma.ae.control_dir() / "STOP").touch()
        r = ma.encargar({"action": "screenshot"})
        self.assertEqual(r["motivo"], "STOP activo"); self.assertTrue(ma.estado()["stop"])


class Ciclo(unittest.TestCase):
    def test_vuelta_lectura_y_bloqueos(self):
        home = pathlib.Path(tempfile.mkdtemp()); base = home / "archivos"; base.mkdir()
        (base / "nota.md").write_text("Hola\nlinea dos\n"); (base / ".env").write_text("X=1")
        cola = [{"tipo": "web", "url": "https://ejemplo.test/"}, {"tipo": "archivo", "ruta": "nota.md"},
                {"tipo": "archivo", "ruta": ".env"}, {"tipo": "archivo", "ruta": "../../etc/passwd"},
                {"tipo": "web", "url": "https://x.test/enviar-correo", "nota": "enviar correo"}, {"tipo": "shell"}]
        (home / "encargos.jsonl").write_text("\n".join(json.dumps(c) for c in cola))
        ev, voz = [], []
        c = ciclo.Ciclo(home, base=base, emit=ev.append, speak=voz.append, stopped=lambda: False,
                        fetch=lambda u: "<title>Prueba</title><p>texto ficticio</p>")
        out = c.vuelta()
        self.assertIn("Prueba", out[0]); self.assertIn("nota.md: 2 líneas", out[1])
        self.assertIn("sensible", out[2]); self.assertIn("fuera", out[3])
        self.assertIn("bloqueado", out[4]); self.assertEqual(out[5], "tipo no permitido")
        self.assertEqual(len(voz), 6); self.assertEqual(c.vuelta(), [])   # no repite
        c2 = ciclo.Ciclo(home, base=base, emit=ev.append, speak=voz.append, stopped=lambda: True)
        self.assertEqual(c2.vuelta(), []); self.assertIn("STOP", c2.ultimo)


if __name__ == "__main__":
    unittest.main()
