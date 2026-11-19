"""Opt-in female macOS voice profile. Mocked local voices; no external APIs or playback."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
from audio import engines


LISTING = """Paulina              es_MX    # Spanish
Monica               es_ES    # Spanish
Juan                 es_MX    # Spanish
Serena               en_GB    # English
Kate                 en_GB    # English
Daniel               en_GB    # English
"""


class VoiceStyle(unittest.TestCase):
    def test_legacy_default_remains_male(self):
        with patch.dict(os.environ, {"JARVIS_VOICE_STYLE": "male",
                                      "JARVIS_VOZ_ES": "", "JARVIS_VOZ_EN": ""}):
            self.assertEqual(engines.choose_voices(LISTING), ("Juan", "Daniel"))
            self.assertEqual(engines.MacSay("Paulina").voice, "auto-latino")

    def test_female_opt_in_uses_installed_local_voices(self):
        with patch.dict(os.environ, {"JARVIS_VOICE_STYLE": "female",
                                      "JARVIS_VOZ_ES": "", "JARVIS_VOZ_EN": ""}):
            self.assertEqual(engines.choose_voices(LISTING), ("Paulina", "Serena"))
            speaker = engines.MacSay("auto-latino")
            with patch.object(speaker, "voices", return_value=("Paulina", "Serena")):
                self.assertEqual(speaker.resolve_voice("¿Cómo estás?"), "Paulina")
                self.assertEqual(speaker.resolve_voice("Good morning, how are you?"), "Serena")

    def test_explicit_female_voice_is_not_rejected_when_opted_in(self):
        self.assertEqual(engines.MacSay("Paulina", style="female").resolve_voice("Hola"), "Paulina")
        self.assertEqual(engines.MacSay("Paulina", style="male").voice, "auto-latino")

    def test_build_passes_style_without_network_or_microphone(self):
        cfg = {"VOICE_STT_BACKEND": "none", "VOICE_TTS_BACKEND": "macos_say",
               "VOICE_TTS_VOICE": "auto-latino", "JARVIS_REPLY_LANGUAGE": "es-PR",
               "JARVIS_VOICE_STYLE": "female"}
        stt, tts = engines.build(cfg)
        self.assertEqual(stt.name, "none")
        self.assertEqual(tts.name, "macos_say")
        self.assertEqual(tts.style, "female")
        self.assertEqual(tts.voice, "auto-latino")

    def test_style_is_opt_in(self):
        for setting in ("", "male", "unknown"):
            self.assertFalse(engines.voice_style_female(setting))
        for setting in ("female", "femenina", "FEMALE"):
            self.assertTrue(engines.voice_style_female(setting))


if __name__ == "__main__":
    unittest.main()
