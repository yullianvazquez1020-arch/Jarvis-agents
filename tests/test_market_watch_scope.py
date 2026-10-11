import asyncio
import unittest
from unittest.mock import patch, AsyncMock
import test_jarvis as base
j=base.j

class MarketScope(unittest.TestCase):
    def setUp(self):
        base.Tests.setUp(self)

    def test_scope_has_public_separated_sections_and_requires_live_search(self):
        with patch.object(j,'_claude_research',new=AsyncMock(return_value=('informe verificado',True))) as research:
            self.assertEqual(asyncio.run(j.run_market_brief()),'informe verificado')
        prompt=research.call_args.args[0]
        for label in ('CRIPTO EN OBSERVACIÓN','ACCIONES EN OBSERVACIÓN','NEGOCIO ISLAFIX','sin dato verificado','mercado está cerrado'):
            self.assertIn(label,prompt)
        self.assertTrue(research.call_args.kwargs['need_live'])
        self.assertEqual(j._rload()['last_brief'],'informe verificado')

    def test_missing_live_data_does_not_overwrite_cached_report(self):
        original=j._rload(); original['last_brief']='anterior'; j._rsave(original)
        with patch.object(j,'_claude_research',new=AsyncMock(return_value=(None,False))):
            self.assertIsNone(asyncio.run(j.run_market_brief()))
        self.assertEqual(j._rload()['last_brief'],'anterior')

    def test_report_prompt_does_not_read_owner_books(self):
        with patch.object(j,'_bload',side_effect=AssertionError('private books')),patch.object(j,'_cload',side_effect=AssertionError('private clients')),patch.object(j,'_claude_research',new=AsyncMock(return_value=('público',True))):
            self.assertEqual(asyncio.run(j.run_market_brief()),'público')
