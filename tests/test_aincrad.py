import datetime as dt
import unittest

import jarvis_aincrad as a
import jarvis_funnel as funnel


class AincradTests(unittest.TestCase):
    def test_landing_uses_the_real_offer(self):
        html = a.kit_html()
        self.assertIn('Organiza tu remodelación', html)
        self.assertIn('$9', html)
        self.assertIn('https://yullian.gumroad.com/l/ketec', html)
        self.assertIn('class="wa"', html)
        self.assertNotIn('<script>', html.split('<style>')[0])

    def test_sequence_is_five_notes_across_a_week(self):
        start = dt.date(2026, 10, 13)
        sub = {'started': start.isoformat(), 'step': 0, 'tried': ''}
        self.assertEqual(a.pending_step(sub, start), 0)
        sub['step'] = 1
        self.assertIsNone(a.pending_step(sub, start))
        self.assertEqual(a.pending_step(sub, start + dt.timedelta(days=1)), 1)
        sub['step'] = 4
        self.assertEqual(a.pending_step(sub, start + dt.timedelta(days=7)), 4)
        sub['tried'] = (start + dt.timedelta(days=7)).isoformat()
        self.assertIsNone(a.pending_step(sub, start + dt.timedelta(days=7)))
        self.assertEqual(len(a.OFFSETS), 5)
        self.assertEqual(len(a.MEDIUM), 10)
        self.assertEqual(len(a.QUORA), 5)

    def test_sales_reply_names_the_price_and_the_hub(self):
        text = a.sales_reply('cuál es el precio', 'https://ejemplo.com/hub')
        self.assertIn('$9', text)
        self.assertIn('https://ejemplo.com/hub', text)

    def test_pitch_sells_any_product_without_a_fake_discount(self):
        catalog = [{'name': 'Plantillas', 'price': 15, 'url': 'https://ejemplo.com/p', 'benefit': 'Las editas hoy.', 'limit': ''}]
        text = a.sales_reply('está caro', 'https://ejemplo.com/hub', catalog)
        self.assertIn('$15', text)
        self.assertIn('https://ejemplo.com/p', text)
        self.assertIn('sin descuento inventado', text)

    def test_click_bounce_counts_and_escapes(self):
        html = funnel.bounce('https://ejemplo.com/kit?q=1')
        self.assertIn('https://ejemplo.com/kit?q=1', html)
        self.assertNotIn('<script>alert', html)

    def test_affiliate_code_is_stable(self):
        self.assertEqual(a.affiliate_code('Ana'), a.affiliate_code('ana'))
        self.assertEqual(len(a.affiliate_code('Ana')), 8)

    def test_call_text_is_escaped_and_the_number_is_strict(self):
        self.assertIn('&', a.call_twiml('A&B'))
        phone, text = a.parse_call('+17874465095 | Hola')
        self.assertEqual(phone, '+17874465095')
        self.assertEqual(text, 'Hola')
        with self.assertRaises(ValueError):
            a.parse_call('7874465095 | Hola')
