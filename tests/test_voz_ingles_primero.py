import os, signal, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "desktop"))
from audio import engines, una_voz  # noqa: E402

FULL = "Juan es_MX # Hola\nDaniel en_GB # Hello\nMonica es_ES # Hola\n"
SRC = (Path(__file__).parents[1] / "desktop" / "app.py").read_text()


class InglesPrimero(unittest.TestCase):
    def _say(self, voice):
        listing = type("L", (), {"stdout": FULL})()
        with patch.object(engines.subprocess, "run", return_value=listing):
            v = engines.MacSay(voice)
            return v.resolve_voice("Good morning, sir. All systems are online."), v.resolve_voice("Hola señor, ¿cómo está?")

    def test_english_only_daniel_even_for_spanish_text(self):
        for voice in ("", "Juan", "Daniel", "auto-latino"):
            self.assertEqual(self._say(voice), ("Daniel", "Daniel"), voice)

    def test_custom_voice_respected(self):
        self.assertEqual(self._say("Oliver"), ("Oliver", "Oliver"))

    def test_natural_rate_and_piper(self):
        self.assertEqual(engines.speech_rate(), 160)
        with patch.dict(os.environ, {"JARVIS_VOZ_RATE": "175"}):
            self.assertEqual(engines.speech_rate(), 175)
        self.assertEqual(engines.Piper("piper", "x.onnx").length_scale, 1.1)

    def test_no_spanish_startup_greeting(self):
        self.assertNotIn("_announce_focus", SRC)
        self.assertNotIn('"-r", "142"', SRC)
        self.assertIn('GREETING = "Good morning, sir.', SRC)

    def test_native_player_claims_single_voice(self):
        self.assertIn("una_voz.claim()", SRC); self.assertIn('una_voz.register(getattr(proc, "pid", 0))', SRC)


class Latencia(unittest.TestCase):
    def test_first_clause_short(self):
        import app
        self.assertEqual(app.speech_chunks("Very well, sir, the agenda is clear today."),
                         ["Very well,", "sir, the agenda is clear today."])
        first = app.speech_chunks("The quarterly numbers look healthy and collections are up across every client")[0]
        self.assertLessEqual(len(first.split()), 6)
        self.assertEqual(app.speech_chunks("Yes, sir."), ["Yes, sir."])
        self.assertEqual(app.speech_chunks("I left it on screen, sir."), ["I left it on screen, sir."])

    def test_log_line(self):
        from audio import latencia
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {"JARVIS_LATENCIA_LOG": d + "/l.log"}):
            rec = latencia.write("t1", {"vad_ms": 450, "stt_ms": 200, "llm_first_token_ms": 100, "tts_first_audio_ms": 50})
            self.assertEqual(rec["total_ms"], 800.0)
            self.assertIn('"stt_ms": 200.0', Path(d, "l.log").read_text())

    def test_vad_and_prewarm(self):
        js = (Path(__file__).parents[1] / "desktop" / "ui" / "app.js").read_text()
        self.assertIn("silenceMs: 350", js)
        self.assertIn("app.prewarm_tts()", SRC)
        self.assertIn("ONLY in", (Path(__file__).parents[1] / "jarvis_desktop_api.py").read_text())


class Fondo(unittest.TestCase):
    def test_fondo_original_loop_quiet(self):
        import wave, numpy as np
        f = Path(__file__).parents[1] / "desktop" / "ui" / "audio" / "fondo.wav"
        with wave.open(str(f)) as w:
            ch = w.getnchannels(); sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, ch) / 32768.0
        self.assertEqual(ch, 2)                                        # v2: estéreo por capas
        self.assertAlmostEqual(len(x) / sr, 32.0, places=1)
        self.assertAlmostEqual(20 * np.log10(np.sqrt(np.mean(x ** 2))), -24.0, delta=0.5)
        self.assertLess(np.abs(x[-1] - x[0]).max(), 0.02)
        self.assertLess(np.abs(x[-1] - x[0]).max(), 3 * np.abs(np.diff(x, axis=0)).mean() + 0.01)                      # bucle sin costura
        for name in ("ambiente.wav", "encendido.wav"):
            self.assertTrue((f.parent / name).is_file())               # música existente intacta
        js = (Path(__file__).parents[1] / "desktop" / "ui" / "startup.js").read_text()
        self.assertIn("/api/fondo-music", js); self.assertIn("fondoLevel()", js)
        self.assertIn('"JARVIS_FONDO"', SRC)


class UnaVoz(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"JARVIS_VOZ_LOCK": os.path.join(self.tmp.name, "v.pid")}); self.env.start()

    def tearDown(self):
        self.env.stop(); self.tmp.cleanup()

    def test_kills_previous_player_only(self):
        killed = []
        una_voz.register(4321)
        self.assertTrue(una_voz.claim(kill=lambda p, s: killed.append((p, s)), name_of=lambda p: "say"))
        self.assertEqual(killed, [(4321, signal.SIGTERM)])
        killed.clear(); una_voz.register(4321)
        self.assertFalse(una_voz.claim(kill=lambda p, s: killed.append(p), name_of=lambda p: "Safari"))
        self.assertEqual(killed, [])

    def test_no_lock_is_noop(self):
        self.assertFalse(una_voz.claim(kill=lambda p, s: self.fail("no debe matar")))


if __name__ == "__main__":
    unittest.main()
