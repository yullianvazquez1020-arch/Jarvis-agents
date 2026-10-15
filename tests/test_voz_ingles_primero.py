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

    def test_fixed_juan_or_daniel_still_english_first(self):
        for voice in ("", "Juan", "Daniel", "auto-latino"):
            self.assertEqual(self._say(voice), ("Daniel", "Juan"), voice)

    def test_custom_voice_respected(self):
        self.assertEqual(self._say("Oliver"), ("Oliver", "Oliver"))

    def test_natural_rate_and_piper(self):
        self.assertTrue(190 <= engines.speech_rate() <= 200)
        self.assertEqual(engines.Piper("piper", "x.onnx").length_scale, 1.0)

    def test_no_spanish_startup_greeting(self):
        self.assertNotIn("_announce_focus", SRC)
        self.assertNotIn('"-r", "142"', SRC)
        self.assertIn('GREETING = "Good morning, sir.', SRC)

    def test_native_player_claims_single_voice(self):
        self.assertIn("una_voz.claim()", SRC); self.assertIn('una_voz.register(getattr(proc, "pid", 0))', SRC)


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
