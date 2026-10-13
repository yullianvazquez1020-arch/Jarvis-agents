import inspect
import os
import unittest

import jarvis_evolve as evolve
import jarvis_video as video


class EvolveTests(unittest.TestCase):
    def test_gumroad_cents_and_seller(self):
        os.environ['GUMROAD_SELLER_ID'] = 'seller-1'
        sale = evolve.sale_from_payload({
            'sale_id': 'sale_abc123', 'seller_id': 'seller-1', 'price': '900',
            'email': 'ana@example.com', 'product_name': 'Kit', 'test': 'false',
        })
        self.assertEqual(sale['amount'], 9.0)
        self.assertEqual(sale['email'], 'ana@example.com')
        with self.assertRaises(ValueError):
            evolve.sale_from_payload({'sale_id': 'sale_abc123', 'seller_id': 'otro', 'price': '900'})
        os.environ.pop('GUMROAD_SELLER_ID', None)

    def test_price_parser_and_host(self):
        html = '<meta property="product:price:amount" content="19.50">'
        self.assertEqual(evolve.extract_price(html), 19.5)
        self.assertEqual(evolve.price_host_ok('https://www.amazon.com/dp/B00TEST'), 'https://www.amazon.com/dp/B00TEST')
        with self.assertRaises(ValueError):
            evolve.price_host_ok('https://evil.example/amazon.com')

    def test_kit_files_and_captions(self):
        pdf = evolve.kit_pdf()
        self.assertTrue(pdf.startswith(b'%PDF'))
        self.assertIn('Ficha', evolve.kit_markdown())
        srt = video.captions_srt('Remodelar', [{'text': 'Cuatro fotos', 'duration': 4}])
        self.assertIn('00:00:01,500 --> 00:00:05,500', srt)
        self.assertIn('Cuatro fotos', srt)

    def test_placeholder_env_is_ignored(self):
        os.environ['GUMROAD_PING_SECRET'] = 'una frase larga tuya'
        os.environ['GUMROAD_SELLER_ID'] = 'AINCRAD <avisos@tu-dominio.com>'
        self.assertEqual(evolve.ping_secret(), '')
        self.assertEqual(evolve.seller_expected(), '')
        os.environ.pop('GUMROAD_PING_SECRET', None)
        os.environ.pop('GUMROAD_SELLER_ID', None)

    def test_social_publish_waits_for_owner_code(self):
        source = inspect.getsource(evolve.install)
        self.assertNotIn('publish_post', source)
        self.assertIn('/confirmarredes', evolve.HELP)
        self.assertIn('publish_post', inspect.getsource(evolve.confirm_command))
