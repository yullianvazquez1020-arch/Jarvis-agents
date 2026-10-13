"""PERSONALIDAD.md se carga en el system prompt (Telegram, voz y BRAIN usan run -> system_prompt)."""
import sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'tests'))
import test_hardening as h
j = h.j


class Personalidad(unittest.TestCase):
    def test_loaded_in_system_prompt(self):
        self.assertIn('Eres Jarvis', j.PERSONALITY_PROMPT)
        p = j.system_prompt()
        self.assertIn('PERSONALITY', p); self.assertIn('Nada se aprueba por voz', p)

    def test_caps_unchanged(self):
        self.assertEqual((j.HARD_MAX_ORDER_USD, j.HARD_MAX_DAY_USD), (100.0, 300.0))


if __name__ == '__main__':
    unittest.main()
