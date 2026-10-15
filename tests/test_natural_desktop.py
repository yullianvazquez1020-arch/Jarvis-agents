import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1] / 'desktop'))
import intents
import app

class NaturalDesktop(unittest.TestCase):
    def test_dialogue_does_not_change_voice_speed(self):
        for text in ('Necesito que respondas más rápido, no que hables rápido',
                     'Please respond faster, do not speak faster',
                     'Quiero que conversemos sobre mis negocios externos',
                     'How are you?', 'Cómo estás'):
            self.assertEqual(intents.parse(text)[0], 'server', text)

    def test_existing_explicit_commands_survive(self):
        for text, kind in [('más rápido', 'faster'), ('habla más despacio', 'slower'),
                           ('speak faster', 'faster'), ('diagnóstico', 'health'),
                           ('abre Safari', 'mouse'), ('silencio', 'stop_audio'),
                           ('/confirmar 123456', 'refuse')]:
            self.assertEqual(intents.parse(text)[0], kind, text)

    def test_sentence_chunks_preserve_every_word(self):
        text = 'The project you mentioned is still here, and we can continue it. What changed today?'
        parts = app.speech_chunks(text)
        self.assertEqual(' '.join(parts), text)
        self.assertEqual(parts[0], 'The project you mentioned is still here, and we can continue it.')
        long_text = ' '.join(['project'] * 180)
        self.assertEqual(' '.join(app.speech_chunks(long_text)), long_text)
        self.assertTrue(all(len(p) <= 450 for p in app.speech_chunks(long_text)))
