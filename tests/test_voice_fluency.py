"""Speech preserves complete claims, numbers and read-only conversation boundaries."""
import sys
import os
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jarvis_chat_voice as cv


class SpeechPreparation(unittest.TestCase):
    def setUp(self):
        configured_language = patch.dict(os.environ, {"JARVIS_REPLY_LANGUAGE": "es-PR"})
        configured_language.start()
        self.addCleanup(configured_language.stop)

    def test_formatting_and_code_are_not_read_as_instructions(self):
        text = '## Estado\n✅ **No publiqué nada.**\n```bash\nrm -rf private\n```\n[Detalles](https://example.com/a)'
        out = cv.spoken_text(text)
        self.assertIn('No publiqué nada.', out)
        for unwanted in ('#', '*', '✅', 'rm -rf', 'https://'):
            self.assertNotIn(unwanted, out)

    def test_money_and_negation_unchanged(self):
        text = 'No se cobró $1,250.50; el saldo es -35 y el límite es 2%.'
        self.assertEqual(cv.spoken_text(text), text)

    def test_truncation_ends_complete_sentence(self):
        first = 'La tienda sigue en borrador.'
        self.assertEqual(cv.spoken_preview(first + ' ' + 'detalle ' * 100), first)

    def test_decimal_is_not_sentence_boundary(self):
        text = 'El total es $123.45 ' + 'pendiente de confirmar ' * 30
        out = cv.spoken_preview(text)
        self.assertNotIn('$123.', out)
        self.assertIn('por escrito', out)

    def test_does_not_remove_mid_sentence_qualification(self):
        text = 'Puedo preparar ' + 'estos borradores ' * 20 + 'pero no publicarlos.'
        self.assertIn('por escrito', cv.spoken_preview(text))

    def test_table_is_referred_to_once(self):
        out = cv.spoken_text('Resumen.\n| A | B |\n|---|---|\n| 1 | 2 |\nNo hay ventas.')
        self.assertEqual(out.count('tabla completa'), 1)
        self.assertIn('No hay ventas.', out)

    def test_short_plain_reply_is_unchanged(self):
        self.assertEqual(cv.spoken_preview(cv.spoken_text('Claro, lo revisamos.')), 'Claro, lo revisamos.')

    def test_preview_is_bounded(self):
        out = cv.spoken_preview('Hola. ' * 500)
        self.assertLessEqual(len(out), cv.MAX_SPOKEN_REPLY)
        self.assertTrue(out.endswith('.'))
