"""Owner-supplied cash/costs, safe drafts, durable limits; no live accounts or sends."""
import asyncio
import datetime as dt
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import test_jarvis as base

j = base.j
w = j._business_workflows
g = j._growth


class Workflows(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.env = patch.dict(os.environ, {'DATA_ENCRYPTION_KEY': '', 'YOUTUBE_API_KEY': 'test-key', 'BUSINESS_REQUESTS_ENABLED': 'false'})
        self.env.start()
        self.addCleanup(self.env.stop)
        j.DATA_DIR = Path(self.temp.name)
        j.USE_REDIS = False
        j._fence.update(mode='off', leader=True)
        j._seal_paused['on'] = False
        self.today = j._today()
        self.future = (self.today + dt.timedelta(days=5)).isoformat()

    def bank(self, amount=400, date=None, key='checking', type='CHECKING'):
        d = j._kload()
        d['accounts'][key] = {'balance': amount, 'balance_date': date or self.today.isoformat(), 'type': type, 'name': 'Bank'}
        j.kv_set(j.K_KEY, d)

    def job(self, amount=150, due=None):
        c = j.add_client('Client', phone='17875551234')
        return j.add_job(c['id'], 'Repair', price=amount, status='confirmed', due_date=due or self.future)

    def bill(self, amount=380):
        # Select an actual monthly occurrence in the seven-day window, even across a month boundary.
        return j.add_bill('Utilities', (self.today + dt.timedelta(days=6)).day, amount=str(amount))

    def test_corrected_grok_arithmetic_no_false_deficit(self):
        self.bank(); self.job(); self.bill()
        r = w.cash_flow_report()
        self.assertEqual(r['projection']['end_balance'], 170)
        self.assertFalse(r['warning'])
        self.assertEqual(r['projection']['without_collections'], 20)

    def test_books_income_never_becomes_bank_cash(self):
        self.bank(); self.job(); self.bill(); j.add_income(99999)
        r = w.cash_flow_report()
        self.assertEqual(r['recorded']['income'], 99999)
        self.assertEqual(r['projection']['end_balance'], 170)

    def test_empty_data_no_projection_or_warning(self):
        r = w.cash_flow_report()
        self.assertIsNone(r['projection']); self.assertFalse(r['warning'])
        self.assertIn('importación', w.cash_text(r))

    def test_fitid_not_required_for_observed_balance(self):
        self.bank(); self.bill()
        self.assertEqual(w.cash_flow_report()['projection']['end_balance'], 20)

    def test_stale_balance_cannot_claim_current_cash(self):
        self.bank(date=(self.today - dt.timedelta(days=4)).isoformat()); self.bill()
        r = w.cash_flow_report()
        self.assertTrue(r['observed'][0]['stale']); self.assertIsNone(r['projection'])
        self.assertIn('saldo viejo', w.cash_text(r))

    def test_future_balance_date_blocks_projection(self):
        self.bank(date=self.future); self.bill()
        self.assertIsNone(w.cash_flow_report()['projection'])

    def test_missing_due_date_blocks_projection(self):
        self.bank(); self.bill(); job = self.job()
        d = j._cload(); d['jobs'][0]['due_date'] = ''; j._csave(d)
        self.assertIsNone(w.cash_flow_report()['projection'])

    def test_missing_bill_amount_does_not_mean_zero(self):
        self.bank(); self.bill('')
        self.assertIsNone(w.cash_flow_report()['projection'])

    def test_credit_balance_is_not_cash(self):
        self.bank(type='CREDITCARD'); self.bill()
        self.assertIsNone(w.cash_flow_report()['projection'])

    def test_multiple_accounts_need_owner_selection(self):
        self.bank(); self.bank(100, key='savings'); self.bill()
        self.assertIsNone(w.cash_flow_report()['projection'])
        self.assertEqual(w.cash_flow_report('checking')['projection']['end_balance'], 20)

    def test_paid_bill_and_paid_job_are_not_counted(self):
        self.bank(); job = self.job(); bill = self.bill()
        j.record_job_payment(job['id'], 150)
        due = j.upcoming(7)['bills'][0]
        j.mark_bill_paid(bill['id'], due['month'])
        r = w.cash_flow_report()
        self.assertEqual(r['incoming'], []); self.assertEqual(r['outgoing'], [])

    def test_future_ledger_entries_and_other_currencies_not_added(self):
        self.bank(); self.bill()
        j.add_income(25, date=self.future); j.add_income(80, currency='EUR')
        self.assertEqual(w.cash_flow_report()['recorded']['income'], 0)

    def test_calendar_duplicate_requires_reconciliation(self):
        self.bank(); self.job(); self.bill()
        j.add_event('Collection', self.future, type='collection', amount='150')
        r = w.cash_flow_report()
        self.assertIsNone(r['projection'])
        self.assertEqual(len(r['incoming']), 1)

    def test_warning_exact_fixed_threshold(self):
        self.bank(0); self.bill(50)
        self.assertTrue(w.cash_flow_report()['warning'])
        self.bank(1)
        self.assertFalse(w.cash_flow_report()['warning'])

    def test_alert_attempt_once_across_restart(self):
        self.bank(0); self.bill(100)
        now = j._now().replace(hour=8)
        with patch.object(j, 'BRIEF_HOUR', '8'), patch.object(j, '_tg_send', new=AsyncMock()) as send:
            asyncio.run(w.cash_tick(now, True))
            # A fresh read of persistent claims simulates restart; no module flag provides dedupe.
            asyncio.run(w.cash_tick(now, True))
            self.assertEqual(send.await_count, 1)
        self.assertEqual(j._bload()['income'], [])

    def test_ambiguous_send_not_retried_that_day(self):
        self.bank(0); self.bill(100)
        with patch.object(j, 'BRIEF_HOUR', '8'), patch.object(j, '_tg_send', new=AsyncMock(side_effect=OSError())) as send:
            asyncio.run(w.cash_tick(j._now().replace(hour=8), True))
            asyncio.run(w.cash_tick(j._now().replace(hour=8), True))
            self.assertEqual(send.await_count, 1)

    def test_read_only_cannot_register_business(self):
        token = j._WRITE_BLOCK.set('voice')
        try:
            with self.assertRaises(j.ReadOnlyViolation):
                w.business_card(j.BUSINESS_NAME, 'Contractor', 'Puerto Rico')
            self.assertIn('solo lectura', asyncio.run(j.run_tool('register_business_card', {}, read_only='voice'))['error'])
        finally:
            j._WRITE_BLOCK.reset(token)

    def test_amazon_owner_costs_correct_margin_without_network(self):
        with patch.object(g, '_json_request', new=AsyncMock()) as request:
            r = w.amazon_margin(25, 10, 8, 0, 15)
            self.assertEqual(r['estimated_margin'], 3.25)
            self.assertEqual(r['units_sold'], 'no disponible')
            request.assert_not_called()

    def test_amazon_requires_shipping_and_packaging(self):
        for field in ('shipping_pr', 'packaging'):
            kw = dict(sale_price=25, unit_cost=10, shipping_pr=8, packaging=0, referral_percent=15)
            del kw[field]
            with self.assertRaises(TypeError): w.amazon_margin(**kw)

    def test_invalid_costs_refused(self):
        for value in (True, 'NaN', '-1', 'Infinity'):
            with self.assertRaises(ValueError): w.amazon_margin(25, value, 8, 0, 15)
        with self.assertRaises(ValueError): w.amazon_margin(25, 10, 8, 0, 101)

    def test_spoofed_amazon_url_rejected(self):
        with self.assertRaises(ValueError):
            w.amazon_margin(25, 10, 8, 0, 15, source_url='https://amazon.com.evil.test/x')

    def test_package_needs_owner_price(self):
        with self.assertRaises(ValueError): w.adult_package('Lesson')
        self.assertEqual(w.load()['packages'], [])
        self.assertEqual(w.adult_package('Lesson', 5)['status'], 'draft')
        self.assertEqual(j._bload()['income'], [])

    def test_unregistered_business_cannot_generate_page(self):
        with self.assertRaises(ValueError): w.business_page('Channel')
        with self.assertRaises(ValueError): w.business_card('Channel', 'Videos', 'PR')
        self.assertFalse(list(j.DATA_DIR.glob('*.html')))

    def test_known_business_needs_trade_and_zone(self):
        for trade, zone in (('', 'PR'), ('Repairs', '')):
            with self.assertRaises(ValueError): w.business_card(j.BUSINESS_NAME, trade, zone)

    def test_html_escapes_untrusted_fields_no_script_or_payment(self):
        w.business_card(j.BUSINESS_NAME, '<script>alert(1)</script>', 'PR', '17875551234')
        page = w.business_page(j.BUSINESS_NAME)
        self.assertNotIn('<script>', page); self.assertIn('&lt;script&gt;', page)
        self.assertIn('https://wa.me/17875551234', page)
        self.assertNotIn('<form', page); self.assertNotIn('type="password"', page)

    def test_corrupted_saved_phone_cannot_inject_html(self):
        w.business_card(j.BUSINESS_NAME, 'Repairs', 'PR')
        d = w.load(); d['businesses'][0]['phone'] = '\" onclick=\"alert(1)'
        j.kv_set(w.KEY, d)
        with self.assertRaises(ValueError): w.business_page(j.BUSINESS_NAME)
        with self.assertRaises(ValueError): j.restore_snapshot(j.snapshot())

    def test_command_generates_file_only_for_review(self):
        w.business_card(j.BUSINESS_NAME, 'Repairs', 'PR')
        with patch.object(j, '_tg_send_document', new=AsyncMock()) as send:
            asyncio.run(w.command('owner', '/pagina', j.BUSINESS_NAME))
            self.assertEqual(send.await_count, 1)
        self.assertEqual(len(list(j.DATA_DIR.glob('*.html'))), 1)

    def test_business_unknown_sensitive_fields_rejected(self):
        with self.assertRaises(TypeError):
            w.business_card(j.BUSINESS_NAME, 'Repairs', 'PR', ein='secret')
        self.assertEqual(w.load()['businesses'], [])

    def test_original_character_request_rejected_before_network_or_llm(self):
        with patch.object(g, '_json_request', new=AsyncMock()) as req, patch.object(j.client.messages, 'create', new=AsyncMock()) as llm:
            for topic in ('Peppa', 'Mickey', 'Copia el video https://example.com/'):
                with self.assertRaises(ValueError): asyncio.run(g.youtube_research(topic))
                with self.assertRaises(ValueError): asyncio.run(g.create_video_plan(topic))
            req.assert_not_called(); llm.assert_not_called()

    def research(self):
        return [{'items': [{'id': {'videoId': 'abc'}}]}, {'items': [{'id': 'abc', 'snippet': {'title': 'Counting', 'channelTitle': 'Education'}, 'statistics': {'viewCount': '25', 'likeCount': '2'}, 'contentDetails': {'duration': 'PT1M'}}]}]

    def test_youtube_observed_counts_and_private_metrics_unavailable(self):
        with patch.object(g, '_json_request', new=AsyncMock(side_effect=self.research())) as req:
            r = asyncio.run(g.youtube_research('contar'))
            v = r['videos'][0]
            self.assertEqual((v['views'], v['likes'], v['comments']), (25, 2, None))
            self.assertEqual(v['retention'], 'no disponible'); self.assertEqual(v['income'], 'no disponible')
            self.assertEqual(req.call_args_list[0].kwargs['params']['relevanceLanguage'], 'es')

    def test_youtube_cache_and_other_query_capped_after_restart(self):
        with patch.object(g, '_json_request', new=AsyncMock(side_effect=self.research())) as req:
            asyncio.run(g.youtube_research('contar'))
            self.assertTrue(asyncio.run(g.youtube_research('contar'))['cached'])
            with self.assertRaises(ValueError): asyncio.run(g.youtube_research('colores'))
            self.assertEqual(req.await_count, 2)

    def test_youtube_failure_does_not_create_retry_storm(self):
        with patch.object(g, '_json_request', new=AsyncMock(side_effect=ValueError('HTTP 429'))) as req:
            for _ in range(2):
                with self.assertRaises(ValueError): asyncio.run(g.youtube_research('contar'))
            self.assertEqual(req.await_count, 1)

    def test_youtube_ten_unique_maximum(self):
        ids = ['v' + str(i) for i in range(15)]
        replies = [{'items': [{'id': {'videoId': x}} for x in ids]},
                   {'items': [{'id': x, 'snippet': {}, 'statistics': {}} for x in ids]}]
        with patch.object(g, '_json_request', new=AsyncMock(side_effect=replies)):
            self.assertEqual(len(asyncio.run(g.youtube_research('contar'))['videos']), 10)

    def test_sourcing_links_do_not_use_paid_research(self):
        with patch.object(j, 'research_topic', new=AsyncMock()) as paid:
            r = asyncio.run(g.sourcing_research('snacks'))
            self.assertIn('no investigación', r['source_status']); paid.assert_not_called()

    def test_hidden_payment_refused_without_mutating_jobs_or_books(self):
        job = self.job(); before = j._cload()
        with self.assertRaises(ValueError): j.record_job_payment(job['id'], 50, add_to_books=False)
        self.assertEqual(j._cload(), before); self.assertEqual(j._bload()['income'], [])

    def test_existing_income_linked_once_without_duplicate_or_omission(self):
        job = self.job(); inc = j.add_income(50)
        j.record_job_payment(job['id'], 50, add_to_books=False, existing_income_id=inc['id'])
        self.assertEqual(len(j._bload()['income']), 1)
        self.assertEqual(j._bload()['income'][0]['amount'], 50)
        before = j._cload()
        with self.assertRaises(ValueError): j.record_job_payment(job['id'], 50, existing_income_id=inc['id'])
        self.assertEqual(j._cload(), before)

    def test_wrong_existing_income_cannot_mark_job_paid(self):
        job = self.job(); inc = j.add_income(25); before = j._cload()
        with self.assertRaises(ValueError): j.record_job_payment(job['id'], 50, existing_income_id=inc['id'])
        self.assertEqual(j._cload(), before); self.assertEqual(j._bload()['income'][0]['amount'], 25)

    def test_hiding_income_and_credit_application_never_reach_llm(self):
        j.add_income(50); before = j._bload()
        with patch.object(j.client.messages, 'create', new=AsyncMock()) as llm:
            self.assertIn('No oculto', asyncio.run(j.run('owner', 'Oculta este ingreso')))
            self.assertIn('No tramito', asyncio.run(j.run('owner', 'Pide la tarjeta con el EIN')))
            llm.assert_not_called()
        self.assertEqual(j._bload(), before)
        self.assertIsNone(w.blocked_request('Avísame el día 20 el pago de la tarjeta, $40'))

    def test_corrupt_workflow_backup_refused(self):
        snap = j.snapshot(); snap['business_workflows']['businesses'] = [{'name': 'Bad'}]
        with self.assertRaises(ValueError): j.restore_snapshot(snap)

    def test_read_only_reports_and_core_safeguards(self):
        self.assertIn('cash_flow_report', j.READ_ONLY_TOOLS)
        self.assertNotIn('register_business_card', j.READ_ONLY_TOOLS)
        self.assertEqual((j.MONEY_MAX_ORDER, j.MONEY_MAX_DAY), (100, 300))
        with self.assertRaises(ValueError): j._tg_enqueue(123, {'text': '/confirmar 1 123456'})
        self.assertFalse(j.CB_TRADING)

    def test_backup_includes_local_drafts(self):
        w.adult_package('Lesson', 5)
        self.assertEqual(j.snapshot()['business_workflows']['packages'][0]['price_usd'], 5)


class QuoteRequests(Workflows):
    # Avoid inheriting the suite: selected below via load_tests.
    def payload(self):
        w.business_card(j.BUSINESS_NAME, 'Repairs', 'PR')
        return dict(business=w.business_slug(j.BUSINESS_NAME), name='Adult', phone='17875551234', message='Please quote repairs', adult=True)

    def test_receipt_only_when_stored_and_no_income_or_send(self):
        data = self.payload()
        with patch.dict(os.environ, {'BUSINESS_REQUESTS_ENABLED': 'true'}), patch.object(j, '_tg_send', new=AsyncMock()) as send:
            result = w.receive_request(**data)
            self.assertIn('Recibido, sin precio', result['message'])
            self.assertEqual(len(w.request_report()['requests']), 1)
            self.assertEqual(j._bload()['income'], []); send.assert_not_called()

    def test_phone_throttle_survives_reload(self):
        data = self.payload()
        with patch.dict(os.environ, {'BUSINESS_REQUESTS_ENABLED': 'true'}):
            w.receive_request(**data)
            with self.assertRaises(ValueError): w.receive_request(**{**data, 'phone': '+17875551234'})
            self.assertEqual(len(w.load()['requests']), 1)

    def test_incoming_disabled_by_default(self):
        data = self.payload()
        with self.assertRaises(ValueError): w.receive_request(**data)
        self.assertEqual(w.load()['requests'], [])

    def test_child_sensitive_unknown_business_and_honeypot_rejected(self):
        data = self.payload()
        with patch.dict(os.environ, {'BUSINESS_REQUESTS_ENABLED': 'true'}):
            for changes in ({'adult': False}, {'message': 'EIN 12345'}, {'business': 'unknown'}, {'website': 'bot'}):
                with self.assertRaises(ValueError): w.receive_request(**{**data, **changes})
        self.assertEqual(w.load()['requests'], [])

    def test_endpoint_body_limit_and_actual_receipt(self):
        data = self.payload()
        async def run():
            async with j.httpx.AsyncClient(transport=j.httpx.ASGITransport(app=j.app), base_url='https://jarvis.test') as c:
                with patch.dict(os.environ, {'BUSINESS_REQUESTS_ENABLED': 'true'}):
                    too_big = await c.post('/public/business-requests', content=b'x'*5001)
                    self.assertEqual(too_big.status_code, 413)
                    response = await c.post('/public/business-requests', json=data)
                    self.assertEqual(response.status_code, 200)
                    duplicate = await c.post('/public/business-requests', json=data)
                    self.assertEqual(duplicate.status_code, 400)
        asyncio.run(run())

    def test_followups_are_drafts_and_leave_jobs_and_books_unchanged(self):
        job = self.job()
        before = j._cload()
        with patch.object(j, '_tg_send', new=AsyncMock()) as send:
            drafts = w.prepare_cash_followups()
            self.assertEqual(len(drafts), 1)
            self.assertEqual(w.prepare_cash_followups(), [])
            send.assert_not_called()
        self.assertEqual(j._cload(), before); self.assertEqual(j._bload()['income'], [])
        self.assertEqual(j._oload()['drafts'][0]['status'], 'pending')

    def test_close_request_not_payment(self):
        data = self.payload()
        with patch.dict(os.environ, {'BUSINESS_REQUESTS_ENABLED': 'true'}):
            row = w.receive_request(**data)
        self.assertEqual(w.request_report('cerrar '+str(row['id']))['status'], 'closed')
        self.assertEqual(w.request_report()['requests'], [])
        self.assertEqual(j._bload()['income'], [])


def load_tests(loader, tests, pattern):
    suite = loader.loadTestsFromTestCase(Workflows)
    for name in QuoteRequests.__dict__:
        if name.startswith('test_'):
            suite.addTest(QuoteRequests(name))
    return suite
