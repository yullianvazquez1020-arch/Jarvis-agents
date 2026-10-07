"""Regressions found in review of Claude's patch; no live integrations."""
import asyncio
import datetime
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import test_jarvis as base
from test_hardening import bad_request, ai_text
j = base.j

class ReviewTests(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp())
        j.USE_REDIS = False
        j._fence.update(mode='off', leader=True)
        j._seen_updates.clear(); j._rate_hits.clear()
        j.conversations.clear()

    def msg(self, text, user=123, chat_type='private'):
        return {'chat': {'id': 123, 'type': chat_type}, 'from': {'id': user}, 'text': text}

    def test_queue_redacts_before_storage(self):
        secret = 'sk-ant-api03-' + 'Z' * 40
        j._tg_enqueue(100, {**self.msg('mi clave '+secret), 'caption': secret})
        raw = json.dumps(j.kv_get(j.TG_INBOX_KEY, {}))
        self.assertNotIn(secret, raw)
        self.assertIn('OMITIDA', raw)

    def test_queue_never_stores_confirmation_code(self):
        with self.assertRaises(ValueError): j._tg_enqueue(101, self.msg('/confirmar 0 678912'))
        self.assertEqual(j._tg_pending_ids(), [])

    def test_failed_local_enqueue_can_be_retried(self):
        with patch.object(j, 'kv_set', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError): j._tg_enqueue(102, self.msg('/hoy'))
        self.assertEqual(j._tg_enqueue(102, self.msg('/hoy')), 'new')

    def test_cancelled_processing_retains_running_record(self):
        j._tg_enqueue(103, self.msg('registrar pago'))
        with patch.object(j, '_tg_route', new=AsyncMock(side_effect=asyncio.CancelledError)):
            with self.assertRaises(asyncio.CancelledError): asyncio.run(j._tg_process(103))
        self.assertEqual(j._tg_job_get(103)['state'], 'running')
        self.assertIsNone(j._tg_claim(103))

    def test_tools_are_not_replayed_on_history_error(self):
        block = MagicMock(type='tool_use', id='tool-1', input={'amount': 25})
        block.name = 'add_income'
        reply = MagicMock(content=[block], stop_reason='tool_use')
        with patch.object(j, 'AI_READY', True), patch.object(j, '_ai_call', new=AsyncMock(side_effect=[reply, bad_request('messages.1: tool_use without tool_result')])) as api, patch.object(j, 'run_tool', new=AsyncMock(return_value={'saved':True})) as tool:
            with self.assertRaises(j.AIModelError): asyncio.run(j.run('review', 'registra 25'))
        self.assertEqual(tool.await_count, 1)
        self.assertEqual(api.await_count, 2)

    def test_truncated_tool_call_is_not_saved_or_executed(self):
        reply = MagicMock(content=[MagicMock(type='tool_use', id='partial')], stop_reason='max_tokens')
        with patch.object(j, 'AI_READY', True), patch.object(j, '_ai_call', new=AsyncMock(return_value=reply)), patch.object(j, 'run_tool', new=AsyncMock()) as tool:
            result = asyncio.run(j.run('review', 'hola'))
        tool.assert_not_called()
        self.assertIn('interrumpida', result)
        self.assertEqual(j.conversations['review'][-1]['content'][0]['type'], 'text')

    def test_empty_reply_has_valid_history(self):
        with patch.object(j, 'AI_READY', True), patch.object(j, '_ai_call', new=AsyncMock(return_value=MagicMock(content=[], stop_reason='end_turn'))):
            self.assertEqual(asyncio.run(j.run('review', 'hola')), '(sin respuesta)')
        self.assertTrue(j.conversations['review'][-1]['content'])

    def test_practice_blocks_all_private_coinbase_requests(self):
        with patch.object(j, 'CRYPTO_PRACTICE_ONLY', True), patch.object(j.httpx, 'AsyncClient') as http:
            for path in ('/api/v3/brokerage/accounts', '/api/v3/brokerage/orders', '/api/v3/brokerage/orders/preview'):
                with self.assertRaisesRegex(ValueError, 'Solo práctica'): asyncio.run(j._cb('POST', path))
        http.assert_not_called()

    def test_paper_step_never_uses_private_api(self):
        market = dict(price=100, sma20=101, sma50=99, trend='alcista', rsi=55)
        with patch.object(j, 'PAPER_PRODUCTS', ['BTC-USD']), patch.object(j, 'paper_market', new=AsyncMock(return_value=market)), patch.object(j, '_cb', new=AsyncMock(side_effect=AssertionError('private API'))) as private:
            events, errors = asyncio.run(j.paper_step())
        private.assert_not_called()
        self.assertEqual(errors, [])
        self.assertTrue(events)

    def test_confirmation_expires_and_is_one_use(self):
        g = j._gload(); code = j.gate_issue_code(g, 'practice#0')
        self.assertTrue(j.gate_check_code(g, 'practice#0', code)['ok'])
        self.assertFalse(j.gate_check_code(g, 'practice#0', code)['ok'])
        code = j.gate_issue_code(g, 'practice#0')
        with patch.object(j, '_now', return_value=j._now()+datetime.timedelta(minutes=6)):
            self.assertFalse(j.gate_check_code(g, 'practice#0', code)['ok'])

    def test_owner_confirmation_is_inline_and_deduplicated(self):
        from fastapi.testclient import TestClient
        with patch.object(j, 'TG_SECRET', 'review-webhook'), patch.object(j, '_tg_cb_cmd', new=AsyncMock()) as confirm, patch.object(j, '_tg_enqueue', side_effect=AssertionError('must not persist')):
            c = TestClient(j.app); headers={'x-telegram-bot-api-secret-token':'review-webhook'}
            for user, ctype in [(999,'private'), (123,'group'), (123,'private'), (123,'private')]:
                r=c.post('/telegram', headers=headers, json={'update_id':104, 'message':self.msg('/confirmar 0 678912',user,ctype)})
                self.assertEqual(r.status_code, 200)
        confirm.assert_awaited_once_with('123','/confirmar','0 678912')

    def test_bad_webhook_secret_and_malformed_sender(self):
        from fastapi.testclient import TestClient
        with patch.object(j, 'TG_SECRET', 'review-webhook'):
            c=TestClient(j.app)
            self.assertEqual(c.post('/telegram',json={}).status_code,401)
            r=c.post('/telegram',headers={'x-telegram-bot-api-secret-token':'review-webhook'},json={'update_id':105,'message':{**self.msg('/hoy'),'from':'invalid'}})
            self.assertEqual(r.status_code,200)

    def test_ana_does_not_match_mariana(self):
        self.assertIsNone(j._client_by_name([{'id':1,'name':'Mariana López'}], 'Ana'))
        self.assertEqual(j._client_by_name([{'id':2,'name':'Ana López'}], 'Ana')['id'],2)

    def test_bill_previous_month_is_included(self):
        dates = j._bill_due_dates({'day':31}, datetime.date(2026,2,1))
        self.assertIn(('2026-01',datetime.date(2026,1,31)),dates)

    def test_refund_does_not_block_books_proposal(self):
        data=j._kload()
        data['tx']=[dict(id='refund',acct='a',date='2026-10-01',amount=-10,category='refund',desc='refund')]
        j._ksave(data)
        result=j.bank_books_proposal(month='2026-10')
        self.assertIsNone(result['proposal'])

    def test_failed_brief_does_not_stop_paper_scheduler(self):
        with patch.object(j,'BRIEF_HOUR',str(j._now().hour)),patch.object(j,'TG_TOKEN','dummy'),patch.object(j,'TG_OWNER','123'),patch.object(j,'MARKET_ON',False),patch.object(j,'_claim',return_value=True),patch.object(j,'collect_alerts',return_value=[]),patch.object(j,'brief_text',return_value='brief'),patch.object(j,'daily_backup',return_value=True),patch.object(j,'_tg_send',new=AsyncMock(side_effect=RuntimeError('send failed'))),patch.object(j,'_tick_v38',new=AsyncMock()) as tick:
            asyncio.run(j._tick())
        tick.assert_awaited_once()

if __name__=='__main__': unittest.main()
