"""Silence rejection and animated canvas lifecycle regressions."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'desktop'))
from audio.wav import make_wav, has_voice_energy
from audio.engines import WhisperCpp

class SilenceGate(unittest.TestCase):
    def test_silence_and_click_are_not_sent_to_whisper(self):
        self.assertFalse(has_voice_energy(make_wav([0] * 16000)))
        self.assertFalse(has_voice_energy(make_wav([10000] * 160 + [0] * 15840)))
        engine = WhisperCpp.__new__(WhisperCpp)
        engine.language = 'es'
        with patch.object(engine, 'problem', return_value=''), patch('audio.engines._run') as run:
            self.assertEqual(engine.transcribe(make_wav([0] * 16000))['text'], '')
            run.assert_not_called()

    def test_audible_signal_is_retained(self):
        self.assertTrue(has_voice_energy(make_wav([1000, -1000] * 8000)))

if __name__ == '__main__':
    unittest.main()
