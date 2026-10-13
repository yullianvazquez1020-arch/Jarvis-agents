import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch
import test_jarvis as base

j = base.j
b = j._business


class BusinessTests(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp())
        j.USE_REDIS = False
        j._fence.update(mode='off', leader=True)

    def test_british_reply_preference_preserves_marketing_language(self):
        with patch.dict(os.environ,{'JARVIS_REPLY_LANGUAGE':'en-GB'}):
            prompt=j.system_prompt()
            self.assertIn('respond in British English',prompt)
            self.assertIn('marketing drafts in their original language',prompt)

    def test_read_no_ai_no_write_and_owner_only(self):
        before = j._store.load()
        with patch.object(j, '_tg_safe_send', new_callable=AsyncMock) as send, patch.object(j, '_ai_call', new_callable=AsyncMock) as ai:
            asyncio.run(j._extensions.command('999', '/negocios', 'preparar'))
            send.assert_not_awaited()
            asyncio.run(j._extensions.command(j.TG_OWNER, '/negocios', ''))
            self.assertIn('Gumroad $9', send.call_args.args[1])
            ai.assert_not_awaited()
        self.assertEqual(j._store.load(), before)

    def test_prepare_preserves_existing_records_budget_and_completed_tasks(self):
        j._store.reply('nombre Mi tienda')
        j._store.reply('presupuesto 12')
        j._store.reply('tarea Trabajo existente')
        before_books = j._bload()
        b.prepare()
        d = j._store.load()
        self.assertEqual(d['name'], 'Mi tienda')
        self.assertEqual(d['daily_budget'], 12)
        self.assertEqual(d['entries'][0]['text'], 'Trabajo existente')
        self.assertEqual(len(d['entries']), 7)
        task = next(r for r in d['entries'] if r['kind'] == 'tarea')
        j._store.reply(f"listo {task['id']}")
        before = j._store.load()
        b.prepare()
        self.assertEqual(j._store.load(), before)
        self.assertEqual(j._bload(), before_books)
        self.assertFalse(b.status()['publication_verified'])
        self.assertIsNone(b.status()['revenue_verified'])

    def test_prepare_atomic_when_store_full(self):
        d = j._store.empty()
        d['name'] = 'Llena'
        d['entries'] = [{'id': n, 'kind': 'tarea', 'text': str(n), 'done': False} for n in range(1, 500)]
        j.kv_set(j._store.KEY, d)
        with self.assertRaises(ValueError):
            b.prepare()
        self.assertEqual(j._store.load(), d)

    def test_voice_readonly_cannot_seed(self):
        token = j._WRITE_BLOCK.set('voice')
        try:
            self.assertIn('NEGOCIOS', b.reply('hoy'))
            with self.assertRaises(Exception):
                b.prepare()
        finally:
            j._WRITE_BLOCK.reset(token)
        self.assertEqual(j._store.load(), j._store.empty())

    def test_resume_uses_real_saved_tasks_and_read_tool(self):
        b.prepare()
        d = b.status()
        self.assertEqual(len(d['store']['entries']), 6)
        self.assertIn('business_plan', j.READ_ONLY_TOOLS)
        self.assertIn('business_plan', j.system_prompt())
        self.assertIn('producto existente', b.reply(''))
        self.assertNotIn('recuperar el kit', b.reply(''))
        for key in ('gumroad', 'fiverr'):
            self.assertIn('BORRADOR', b.reply(key))
            self.assertLess(len(b.reply(key)), 3500)
        self.assertIn('store', j.snapshot())

    def test_develop_idempotent_without_external_effects(self):
        before = (j._bload(), j._oload(), j._gload())
        with patch.object(j, '_ai_call', new_callable=AsyncMock) as ai:
            result = b.develop()
            saved = j._store.load()
            self.assertEqual(len(saved['entries']), 9)
            self.assertIn('ketec', result)
            self.assertIn('guion', result)
            self.assertEqual(b.develop(), result)
            self.assertEqual(j._store.load(), saved)
            ai.assert_not_awaited()
        self.assertEqual((j._bload(), j._oload(), j._gload()), before)
        self.assertNotIn('business_develop', j.READ_ONLY_TOOLS)
        token = j._WRITE_BLOCK.set('voice')
        try:
            j.DATA_DIR = Path(tempfile.mkdtemp())
            with self.assertRaises(Exception):
                b.develop()
        finally:
            j._WRITE_BLOCK.reset(token)

    def test_capabilities_reflect_unavailable_module(self):
        with patch.object(j, 'EVOLVE_STATUS', 'apagado'):
            self.assertFalse(b.status()['capabilities']['kit_routes_available'])
            self.assertIn('no está disponible', b.summary())

    def test_old_setup_tasks_preserved_but_not_resurfaced(self):
        j._store.reply('nombre AINCRAD')
        j._store.reply('tarea ' + b.LEGACY_TASKS[0])
        before = j._store.load()
        self.assertNotIn('recuperar', b.summary())
        self.assertEqual(j._store.load(), before)
        self.assertIn(b.LEGACY_TASKS[0], b.status()['superseded_task_texts'])
