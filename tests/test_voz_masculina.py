import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "desktop"))
from audio import engines  # noqa: E402

FULL = ("Paulina es_MX # Hola\nMónica es_ES # Hola\nJuan es_MX # Hola\nJorge es_ES # Hola\n"
        "Diego es_AR # Hola\nDaniel en_GB # Hello\nKaren en_AU # Hello\n")


class VozMasculina(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=False)
        self.env.start()
        for k in ("JARVIS_VOZ_ES", "JARVIS_VOZ_EN", "JARVIS_VOZ_RATE"):
            os.environ.pop(k, None)

    def tearDown(self):
        self.env.stop()

    def test_preference_order(self):
        self.assertEqual(engines.choose_voices(FULL), ("Juan", "Daniel"))
        self.assertEqual(engines.choose_voices(FULL.replace("Juan es_MX # Hola\n", ""))[0], "Jorge")
        self.assertEqual(engines.choose_voices("Diego es_AR # Hola\nPaulina es_MX # Hola\n")[0], "Diego")

    def test_never_female(self):
        for name in ("Paulina", "Mónica", "Monica", "Soledad", "Marisol", "Angélica", "Angelica"):
            self.assertTrue(engines.is_female(name), name)
        self.assertEqual(engines.choose_voices("Paulina es_MX # H\nSoledad es_CO # H\nMarisol es_ES # H\n"), ("", ""))

    def test_env_overrides(self):
        with patch.dict(os.environ, {"JARVIS_VOZ_ES": "Diego", "JARVIS_VOZ_EN": "Oliver", "JARVIS_VOZ_RATE": "160"}):
            self.assertEqual(engines.choose_voices(FULL), ("Diego", "Oliver"))
            self.assertEqual(engines.speech_rate(), 160)
        self.assertEqual(engines.speech_rate(), 170)
        with patch.dict(os.environ, {"JARVIS_VOZ_RATE": "abc"}):
            self.assertEqual(engines.speech_rate(), 170)

    def test_bilingual_detection_and_voice(self):
        self.assertEqual(engines.detect_lang("Hello sir, how are you? Guess how much money we've made today."), "en")
        self.assertEqual(engines.detect_lang("Hola señor, ¿cómo está?"), "es")
        self.assertEqual(engines.detect_lang("Listo, ya quedó"), "es")
        listing = type("L", (), {"stdout": FULL})()
        with patch.object(engines.subprocess, "run", return_value=listing):
            v = engines.MacSay()
            self.assertEqual(v.resolve_voice("Hello sir, how are you today?"), "Daniel")
            self.assertEqual(v.resolve_voice("Hola señor, ¿cómo está?"), "Juan")

    def test_voz_loop_speaker_male(self):
        sys.path.insert(0, str(Path(__file__).parents[1] / "desktop"))
        import voz_loop
        listing = type("L", (), {"stdout": FULL})()
        with patch.dict(os.environ, {"PIPER_MODEL": "", "JARVIS_SAY_VOICE": "Paulina"}), \
                patch.object(voz_loop.subprocess, "run", return_value=listing):
            cmd = voz_loop.Speaker().command("Hola señor")
            self.assertEqual(cmd[:3], ["say", "-v", "Juan"]); self.assertIn("170", cmd)
            cmd = voz_loop.Speaker().command("Hello sir, how are you?")
            self.assertEqual(cmd[:3], ["say", "-v", "Daniel"]); self.assertIn("170", cmd)


if __name__ == "__main__":
    unittest.main()
