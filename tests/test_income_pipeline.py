import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import test_jarvis as base
j = base.j
m = j._income

class IncomeTests(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp())
        j.USE_REDIS = False
        j._fence.update(mode='off', leader=True)

    def test_catalog_complete_and_unknown_values_explicit(self):
        self.assertEqual(len(m.CATALOG), 100)
        self.assertEqual(len({x['name'] for x in m.CATALOG}), 100)
        for n in range(1, 101):
            self.assertIn('sin dato', m.reply('/fuente', str(n)))
        self.assertEqual(m.load(), {'items': {}})
        self.assertIsNone(m.status()['verified_revenue'])

    def test_select_limit_and_retry(self):
        for n in (11, 2, 1, 11):
            m.reply('/fuente', f'{n} activar')
        before = m.load()
        with self.assertRaises(ValueError):
            m.reply('/fuente', '21 activar')
        self.assertEqual(m.load(), before)
        m.reply('/fuente', '1 pausar')
        m.reply('/fuente', '21 activar')
        self.assertEqual(len(m.status()['active']), 3)

    def test_draft_persists_without_money_or_outbox_effects(self):
        before = (j._bload(), j._gload(), j._oload(), j._paperload())
        text = m.reply('/fuente', '11 borrador')
        self.assertIn('BORRADOR', text)
        self.assertEqual(m.load()['items']['11']['draft'], text)
        self.assertEqual((j._bload(), j._gload(), j._oload(), j._paperload()), before)
        self.assertIn('No se ha enviado', text)

    def test_backup_validation(self):
        m.reply('/fuente', '11 nota Interés por confirmar')
        snap = j.snapshot()
        self.assertIn('income_pipeline', j._validate_backup(snap))
        snap['income_pipeline']['items']['11']['active'] = 'true'
        with self.assertRaises(ValueError):
            j.restore_snapshot(snap)
        self.assertFalse(m.load()['items']['11']['active'])

    def test_resume_includes_paused_notes_and_draft_without_writes(self):
        m.reply('/fuente', '21 nota Preparar plantilla para Gumroad; precio por validar')
        m.reply('/fuente', '21 borrador')
        before = m.load()
        text = m.reply('/ingresosplan', '')
        self.assertIn('Preparar plantilla para Gumroad', text)
        self.assertIn('Borrador guardado: /fuente 21', text)
        self.assertIn('piloto no activo', text)
        self.assertEqual(m.load(), before)

    def test_owner_only_and_no_ai(self):
        with patch.object(j, '_tg_safe_send', new_callable=AsyncMock) as send, patch.object(j, '_ai_call', new_callable=AsyncMock) as ai:
            asyncio.run(j._extensions.command('999', '/fuente', '11 activar'))
            self.assertEqual(m.load()['items'], {})
            send.assert_not_awaited()
            asyncio.run(j._extensions.command(j.TG_OWNER, '/fuente', '11 activar'))
            self.assertTrue(m.load()['items']['11']['active'])
            ai.assert_not_awaited()

    def test_readonly_voice_cannot_write(self):
        token = j._WRITE_BLOCK.set('voice')
        try:
            self.assertIn('100 ideas', m.reply('/ingresosplan', ''))
            with self.assertRaises(Exception):
                m.reply('/fuente', '11 activar')
        finally:
            j._WRITE_BLOCK.reset(token)
        self.assertEqual(m.load()['items'], {})

    def test_pages_and_bounds(self):
        for n in range(1, 11):
            self.assertIn(f'#{n*10} ', m.reply('/fuentes', str(n)))
        for cmd, arg in (('/fuentes','11'),('/fuente','101'),('/fuente','0'),('/fuente','11 nota ' + 'x'*2501)):
            with self.assertRaises(ValueError):
                m.reply(cmd, arg)
