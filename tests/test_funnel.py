import os
import unittest

import jarvis_funnel as funnel


class FunnelHubTests(unittest.TestCase):
    def test_rejects_insecure_urls(self):
        self.assertEqual(funnel.https_url('https://gumroad.com/l/kit'), 'https://gumroad.com/l/kit')
        for bad in ('http://gumroad.com/l/kit', 'https://user:pw@gumroad.com/l/kit', 'javascript:alert(1)'):
            with self.assertRaises(ValueError):
                funnel.https_url(bad)

    def test_page_is_the_hub_and_escapes(self):
        os.environ.pop('META_PIXEL_ID', None)
        os.environ.pop('GA4_MEASUREMENT_ID', None)
        html = funnel.page({
            'title': '<script>',
            'bio': 'A&B',
            'links': [{'slug': 'kit', 'name': 'Kit', 'url': 'https://example.com/kit'}],
        })
        self.assertIn('/hub/go/kit', html)
        self.assertNotIn('<script>', html)
        self.assertIn('amp;B', html)
        self.assertNotIn('linktr.ee', html)

    def test_tracking_only_with_real_ids(self):
        os.environ['META_PIXEL_ID'] = '1234567890'
        os.environ['GA4_MEASUREMENT_ID'] = 'not-an-id'
        ids = funnel.tracking()
        self.assertEqual(ids['pixel'], '1234567890')
        self.assertEqual(ids['ga4'], '')
        os.environ.pop('META_PIXEL_ID', None)
        os.environ.pop('GA4_MEASUREMENT_ID', None)
