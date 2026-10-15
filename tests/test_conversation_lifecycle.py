"""Exercise microphone/audio races in the real browser controller with fake devices."""
import subprocess
import unittest
from pathlib import Path


class ConversationLifecycle(unittest.TestCase):
    def test_browser_lifecycle(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(['node', str(root / 'scripts/check_conversation_lifecycle.cjs')],
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class EnglishControls(unittest.TestCase):
    def test_existing_and_english_controls(self):
        from desktop import intents
        for phrase, kind in [("speak slower", "slower"), ("más despacio", "slower"),
                             ("stop the mouse", "stop_mouse"), ("para el mouse", "stop_mouse"),
                             ("turn off the microphone", "mic_off"), ("repeat that", "repeat"),
                             ("approve the payment", "refuse")]:
            with self.subTest(phrase=phrase):
                self.assertEqual(intents.parse(phrase)[0], kind)
