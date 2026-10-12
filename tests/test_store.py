"""Store persistence, owner boundaries and backup validation; no external services."""
import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import test_jarvis as base

j = base.j
s = j._store


class StoreTests(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp())
        j.USE_REDIS = False
        j._fence.update(mode='off', leader=True)

    def test_persist_and_share_with_read_tool_and_hud(self):
        s.reply('nombre ISLAFIX')
        s.reply('producto Plantilla de cotizaciones')
        s.reply('tarea Revisar descripción')
        s.reply('listo 2')
        d = j.HANDLERS['store_status']()
        self.assertEqual(d['name'], 'ISLAFIX')
        self.assertTrue(d['entries'][1]['done'])
        self.assertEqual(j.kv_get(s.KEY, {})['entries'], d['entries'])
        import jarvis_desktop_api as desktop
        with patch.object(desktop, "core", j, create=True):
            cards = desktop._hud_cards()
        self.assertEqual(next(c for c in cards if c['id'] == 'caja')['value'], 'ISLAFIX')
        self.assertIn('store_status', j._desktop.READ_TOOLS)
        self.assertNotIn('store_save', j.HANDLERS)

    def test_invalid_budget_does_not_change_data(self):
        s.reply('nombre Prueba')
        before = s.load()
        for value in ('nan', 'inf', '-1', '301', 'true'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                s.reply('presupuesto ' + value)
            self.assertEqual(s.load(), before)

    def test_retry_and_results_never_change_books_or_gate(self):
        before = (j._bload(), j._gload())
        s.reply('nombre Prueba')
        for _ in range(2):
            s.reply('resultado Vendí 5000 según mi nota')
        s.reply('presupuesto 100')
        self.assertEqual(len(s.load()['entries']), 1)
        self.assertEqual((j._bload(), j._gload()), before)
        self.assertFalse(s.status()['spending_authorized'])

    def test_backup_and_corrupt_restore(self):
        s.reply('nombre Prueba')
        snap = j.snapshot()
        self.assertEqual(snap['store']['name'], 'Prueba')
        self.assertIn('store', j._validate_backup(snap))
        snap['store']['entries'] = [{'id': 1, 'kind': 'tarea', 'text': '', 'done': False}]
        with self.assertRaises(ValueError):
            j.restore_snapshot(snap)
        self.assertEqual(s.load()['entries'], [])

    def test_nonowner_cannot_write(self):
        send = AsyncMock()
        with patch.object(j, '_tg_safe_send', send):
            asyncio.run(j._extensions.command('999', '/tienda', 'nombre Intruso'))
        self.assertEqual(s.load()['name'], '')
        send.assert_not_awaited()

    def test_readonly_context_blocks_write(self):
        token = j._WRITE_BLOCK.set(True)
        try:
            with self.assertRaises(Exception):
                s.reply('nombre Intruso')
        finally:
            j._WRITE_BLOCK.reset(token)
        self.assertEqual(s.load()['name'], '')

    def test_owner_command_without_ai(self):
        with patch.object(j, '_tg_safe_send', new_callable=AsyncMock) as send, patch.object(j, '_ai_call', new_callable=AsyncMock) as ai:
            asyncio.run(j._extensions.command(j.TG_OWNER, '/tienda', 'nombre Prueba'))
            self.assertIn('Guardado en Jarvis', send.call_args.args[1])
            ai.assert_not_awaited()

    def test_full_text_and_unknown_task(self):
        s.reply('nombre Prueba')
        s.reply('borrador ' + 'a' * 1500)
        self.assertIn('a' * 1500, s.reply('ver 1'))
        with self.assertRaises(ValueError):
            s.reply('listo 1')

    def test_credit_error_remains_distinct_from_configuration(self):
        text = j._fail_text(j.AIModelError('credit balance is too low'))
        self.assertIn('sin saldo', text)
        self.assertNotIn('CLAUDE_MODEL', text)
        self.assertIn('configuración', j._fail_text(j.AIModelError('model: invalid model')))
