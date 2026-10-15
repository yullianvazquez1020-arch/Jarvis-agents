import unittest
import os
from unittest.mock import patch
import jarvis_amazon_config as c

class AmazonConfigTests(unittest.TestCase):
    def test_complete_legacy_preserved(self):
        with patch.dict(os.environ, dict(zip(c.LEGACY,['old']*5)), clear=True):
            self.assertTrue(c.status()['configured'])
            self.assertEqual(c.value('SPAPI_REFRESH_TOKEN'),'old')
    def test_complete_grok_set_recognized(self):
        with patch.dict(os.environ, dict(zip(c.SPAPI,['new']*5)), clear=True):
            self.assertTrue(c.status()['configured'])
            self.assertEqual(c.value('AMAZON_CLIENT_SECRET'),'new')
            self.assertNotIn('new',str(c.status()))
    def test_partial_accounts_not_mixed(self):
        env=dict(zip(c.LEGACY[:3],['old']*3));env.update(dict(zip(c.SPAPI[3:],['new']*2)))
        with patch.dict(os.environ,env,clear=True):
            self.assertFalse(c.status()['configured'])
            self.assertEqual(c.value('AMAZON_SELLER_ID'),'')
    def test_complete_legacy_wins_over_other_account(self):
        env=dict(zip(c.LEGACY,['old']*5));env.update(dict(zip(c.SPAPI,['new']*5)))
        with patch.dict(os.environ,env,clear=True):
            self.assertEqual(c.value('SPAPI_SELLER_ID'),'old')
    def test_diagnostics_agree_with_runtime(self):
        from tests.test_hardening import j
        with patch.dict(os.environ,dict(zip(c.SPAPI,['new']*5)),clear=True):
            self.assertTrue(j._growth.growth_status()['amazon_credentials_configured'])
