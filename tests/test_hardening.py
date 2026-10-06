"""Jarvis 4.0.1 hardening tests. Every external service is simulated: no real money, messages, tokens or Upstash."""
import os, sys, tempfile, importlib.util, asyncio, unittest, json, logging, io, datetime, copy
from unittest.mock import patch, AsyncMock, MagicMock
for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'): os.environ.pop(name, None)
os.environ.update(ANTHROPIC_API_KEY='test-local-only', AGENT_API_KEY='master-key-for-tests', DATA_DIR=tempfile.mkdtemp(),
                  COINBASE_TRADING_ENABLED='false', TELEGRAM_OWNER_ID='123', TELEGRAM_OWNER_USER_ID='123',
                  SCHEDULER_ENABLED='false')
ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import test_jarvis as base
j = base.j
e = j._extensions
from anthropic import BadRequestError
import httpx


def bad_request(msg):
    req = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')
    return BadRequestError(msg, response=httpx.Response(400, request=req), body={'error': {'message': msg}})


def ai_text(text):
    return MagicMock(content=[MagicMock(type='text', text=text)], stop_reason='end_turn')


class FakeRedis:
    """Enough of Upstash REST for Jarvis: GET/SET(NX,EX,KEEPTTL)/MSET/DEL/SCAN and the three EVAL scripts."""
    def __init__(self): self.d = {}
    def __call__(self, cmd):
        op = cmd[0].upper()
        if op == 'GET': return self.d.get(cmd[1])
        if op == 'SET':
            k, v, flags = cmd[1], cmd[2], [str(x).upper() for x in cmd[3:]]
            if 'NX' in flags and k in self.d: return None
            self.d[k] = v; return 'OK'
        if op == 'MSET':
            for i in range(1, len(cmd), 2): self.d[cmd[i]] = cmd[i + 1]
            return 'OK'
        if op == 'DEL': return int(self.d.pop(cmd[1], None) is not None)
        if op == 'SCAN':
            prefix = cmd[3].rstrip('*'); return ['0', [k for k in self.d if k.startswith(prefix)]]
        if op == 'EVAL':
            script, nkeys = cmd[1], int(cmd[2]); keys = cmd[3:3 + nkeys]; argv = cmd[3 + nkeys:]
            if script == j._FENCED_SET:
                if self.d.get(keys[0]) != argv[0]: return 'FENCED'
                return self('MSET', ) if False else self(['MSET'] + argv[1:])
            if script == j._CLAIM_JOB:
                if self.d.get(keys[0]) != argv[0]: return 'FENCED'
                raw = self.d.get(keys[1])
                if not raw: return ''
                # mirrors the v4.0.2 string-only script (no cjson); the real script is tested in test_redis_lua.py
                prefix = argv[3]
                if not raw.startswith(prefix):
                    return '' if raw.startswith('{"state": "') else 'BADFORMAT'
                self.d[keys[1]] = '{"state": "running", "started": "' + argv[1] + '", ' + raw[len(prefix):]
                return self.d[keys[1]]
            if script == j._ENQUEUE:
                if argv[2] == '1' and self.d.get(keys[2]) != argv[3]: return 'FENCED'
                if keys[0] in self.d: return 'DUP'
                self.d[keys[0]] = '1'; self.d[keys[1]] = argv[0]; return 'NEW'
            return 'OK' if self.d.get(keys[0]) == argv[0] else 'NO'
        raise AssertionError('unexpected redis command ' + op)


class Base(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = __import__('pathlib').Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode='off', leader=True); j._seen_updates.clear(); j.conversations.clear()
        j._tg_stats.update(recovered=0, interrupted=0, stale=0)

    def tg(self, text, update_id=1, chat_type='private', user=123):
        return {'update_id': update_id, 'message': {'chat': {'id': 123, 'type': chat_type}, 'from': {'id': user}, 'text': text}}


class Startup(Base):
    def test_app_boots_with_lifespan_and_reports_version(self):
        from fastapi.testclient import TestClient
        with TestClient(j.app) as c:
            h = c.get('/').json()
        self.assertEqual(h['version'], j.VERSION); self.assertFalse(h['ai']['configured'])
        self.assertEqual(h['instance']['write_fencing'], 'off'); self.assertFalse(h['paper_trading']['real_money'])
        self.assertFalse(h['coinbase']['trading'])

    def test_modules_installed_and_versions_agree(self):
        self.assertEqual(e.system_configuration()['version'], j.VERSION)
        self.assertEqual(j._growth.growth_status()['version'], j.VERSION)
        self.assertIn('/diagnostico', j.HELP_TEXT)
        self.assertEqual(set(j.RESTORE_KEYS) >= {'extensions', 'growth', 'gate', 'books', 'clients'}, True)

    def test_default_model_is_documented_id(self):
        self.assertEqual(j.MODEL, 'claude-sonnet-5-5'); self.assertTrue(j.MODEL_FORMAT_OK)


class Auth(Base):
    def test_master_key_required(self):
        from fastapi.testclient import TestClient
        c = TestClient(j.app)
        self.assertEqual(c.post('/chat', json={'message': 'hola'}, headers={'x-api-key': 'bad'}).status_code, 401)
        self.assertEqual(c.get('/backup', headers={'x-api-key': 'bad'}).status_code, 401)
        self.assertEqual(c.post('/restore', json={'backup': {}}, headers={'x-api-key': 'bad'}).status_code, 401)

    def test_stranger_and_group_cannot_run_owner_commands(self):
        from fastapi.testclient import TestClient
        j.TG_SECRET = 'sec'; c = TestClient(j.app); h = {'x-telegram-bot-api-secret-token': 'sec'}
        with patch.object(j, '_tg_send', new=AsyncMock()) as send:
            c.post('/telegram', headers=h, json=self.tg('/ejecutar 1', 1, user=999))
            send.assert_not_called()
            c.post('/telegram', headers=h, json=self.tg('/ejecutar 1', 2, chat_type='group'))
            self.assertIn('privado', send.await_args.args[1])


class AIOff(Base):
    def test_no_paid_call_without_key(self):
        self.assertFalse(j.AI_READY)
        with patch.object(j, '_ai_call', new=AsyncMock()) as call:
            reply = asyncio.run(j.run('s', 'hola'))
        call.assert_not_called(); self.assertIn('no hice ninguna llamada de pago', reply)

    def test_guarded_client_raises_not_configured(self):
        with self.assertRaises(j.AINotConfigured):
            asyncio.run(j.client.messages.create(model=j.MODEL, max_tokens=1, messages=[]))

    def test_receipt_photo_without_ai_explains(self):
        with patch.object(j, '_tg_file', new=AsyncMock(return_value=b'\xff\xd8\xffX')), \
             patch.object(j, '_tg_send', new=AsyncMock()) as send:
            asyncio.run(e.receipt_photo('123', 'f'))
        self.assertIn('IA no configurada', send.await_args.args[1])

    def test_commands_still_work_without_ai(self):
        with patch.object(j, '_tg_send', new=AsyncMock()) as send:
            self.assertEqual(j._tg_enqueue(5, self.tg('/hoy', 5)['message']), 'new')
            asyncio.run(j._tg_process(5))
        self.assertIn('Resumen de hoy', send.await_args.args[1])


class WithAI(Base):
    def setUp(self):
        super().setUp(); self.p = patch.object(j, 'AI_READY', True); self.p.start()
    def tearDown(self): self.p.stop()


class Secrets(WithAI):
    def test_secret_never_reaches_ai_or_history(self):
        seen = []
        async def fake(history): seen.append(copy.deepcopy(history)); return ai_text('ok')
        key = 'sk-ant-api03-' + 'A' * 40
        with patch.object(j, '_ai_call', new=fake):
            reply = asyncio.run(j.run('s', f'anota gasto 20 y mi clave es {key}'))
        self.assertNotIn(key, json.dumps(seen)); self.assertNotIn(key, json.dumps(j.conversations['s'], default=str))
        self.assertIn('🔒', reply)

    def test_server_secret_values_and_cards_masked(self):
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'tok-value-1234567'}):
            clean, found = j._redact_secrets('token tok-value-1234567 y tarjeta 4111 1111 1111 1111, ref 12345678')
        self.assertNotIn('tok-value', clean); self.assertNotIn('4111 1111', clean); self.assertIn('••1111', clean)
        self.assertIn('12345678', clean)   # not a valid card number: left alone
        self.assertEqual(set(found), {'credencial del servidor', 'número de tarjeta'})

    def test_tool_results_masked_before_ai(self):
        e.save_note('acceso', 'password: hunter22secret')
        self.assertNotIn('hunter22secret', json.dumps(e.load()['notes']))   # masked at rest
        out = j._redact_any({'notes': [{'body': 'clave sk-ant-api03-' + 'B' * 30}]})
        self.assertNotIn('BBBB', json.dumps(out))

    def test_outgoing_telegram_and_logs_masked(self):
        sent = []
        class R:
            status_code = 200
            def json(self): return {'ok': True}
        class C:
            async def __aenter__(s): return s
            async def __aexit__(s, *a): pass
            async def post(s, url, json): sent.append(json['text']); return R()
        with patch.object(j.httpx, 'AsyncClient', new=lambda **k: C()):
            asyncio.run(j._tg_send('1', 'mira sk-ant-api03-' + 'C' * 30))
        self.assertNotIn('CCCC', sent[0])
        buf = io.StringIO(); h = logging.StreamHandler(buf); h.addFilter(j._RedactingFilter()); j.logger.addHandler(h)
        try: j.logger.warning('fallo con sk-ant-api03-%s', 'D' * 30)
        finally: j.logger.removeHandler(h)
        self.assertNotIn('DDDD', buf.getvalue())

    def test_voice_transcript_and_incoming_masked(self):
        class R:
            def raise_for_status(self): pass
            def json(self): return {'text': 'mi pin: 99887766 apunta 20 de gasolina'}
        class C:
            async def __aenter__(s): return s
            async def __aexit__(s, *a): pass
            async def post(s, *a, **k): return R()
        with patch.dict(os.environ, {'STT_AGENT_URL': 'https://stt.example.com'}), \
             patch.object(j, '_tg_file', new=AsyncMock(return_value=b'ogg')), \
             patch.object(j.httpx, 'AsyncClient', new=lambda **k: C()), patch.object(j, '_tg_send', new=AsyncMock()):
            asyncio.run(e.voice_message('123', {'file_id': 'v'}))
        self.assertNotIn('99887766', json.dumps(e.load()['voices']))


class History(WithAI):
    def test_history_error_repairs_and_retries_once(self):
        j.conversations['s'] = [{'role': 'user', 'content': 'viejo'}, {'role': 'assistant', 'content': 'x'}]
        calls = []
        async def fake(history):
            calls.append(len(history))
            if len(calls) == 1: raise bad_request('messages.1: `tool_use` ids were found without `tool_result` blocks')
            return ai_text('listo')
        with patch.object(j, '_ai_call', new=fake):
            reply = asyncio.run(j.run('s', 'nuevo'))
        self.assertEqual(calls, [3, 1]); self.assertIn('listo', reply); self.assertIn('Reinicié el historial', reply)

    def test_model_error_keeps_history_and_reports_cause(self):
        old = [{'role': 'user', 'content': 'viejo'}, {'role': 'assistant', 'content': 'x'}]
        j.conversations['s'] = list(old)
        async def fake(history): raise bad_request('model: claude-nope is not a valid model')
        with patch.object(j, '_ai_call', new=fake):
            with self.assertRaises(j.AIModelError) as ctx: asyncio.run(j.run('s', 'nuevo'))
        self.assertEqual(j.conversations['s'], old); self.assertIn('claude-nope', str(ctx.exception))
        self.assertIn('configuración', j._fail_text(ctx.exception))

    def test_tool_schema_error_is_not_history(self):
        self.assertFalse(j._is_history_error(bad_request('tools.3.input_schema: invalid')))
        self.assertTrue(j._is_history_error(bad_request('messages: roles must alternate between "user" and "assistant"')))


class Delegation(Base):
    def test_ai_tool_only_drafts(self):
        with patch.dict(j.AGENTS, {'message': 'https://sms.example.com'}), patch.object(j, 'EXTERNAL_AGENT_KEY', 'ext'), \
             patch.object(j.httpx, 'AsyncClient') as hc:
            a = asyncio.run(j.run_tool('delegate', {'agent': 'message', 'instruction': 'Envía SMS al 787'}))
        hc.assert_not_called(); self.assertEqual(a['status'], 'pending')

    def test_core_delegate_refuses_without_approval(self):
        with patch.dict(j.AGENTS, {'call': 'https://call.example.com'}), patch.object(j, 'EXTERNAL_AGENT_KEY', 'ext'):
            self.assertIn('error', asyncio.run(j.delegate('call', 'x')))

    def test_coinbase_and_amazon_never_delegated(self):
        for agent in ('coinbase', 'amazon'):
            with patch.dict(j.AGENTS, {agent: 'https://x.example.com'}), patch.object(j, 'EXTERNAL_AGENT_KEY', 'ext'):
                self.assertIn('nunca', asyncio.run(j.delegate(agent, 'buy', approved_action_id=1))['error'])

    def test_master_key_never_sent_and_https_required(self):
        captured = []
        class R:
            def raise_for_status(self): pass
            def json(self): return {'ok': True}
        class C:
            async def __aenter__(s): return s
            async def __aexit__(s, *a): pass
            async def post(s, url, headers, json=None): captured.append(headers); return R()
        with patch.object(j.httpx, 'AsyncClient', new=lambda **k: C()):
            with patch.dict(j.AGENTS, {'call': 'http://call.example.com'}), patch.object(j, 'EXTERNAL_AGENT_KEY', 'ext'):
                self.assertIn('https', asyncio.run(j.delegate('call', 'x', approved_action_id=1))['error'])
            with patch.dict(j.AGENTS, {'call': 'https://10.0.0.5'}), patch.object(j, 'EXTERNAL_AGENT_KEY', 'ext'):
                self.assertIn('error', asyncio.run(j.delegate('call', 'x', approved_action_id=1)))
            with patch.dict(j.AGENTS, {'call': 'https://call.example.com'}), patch.object(j, 'EXTERNAL_AGENT_KEY', ''):
                self.assertIn('EXTERNAL_AGENT_KEY', asyncio.run(j.delegate('call', 'x', approved_action_id=1))['error'])
            with patch.dict(j.AGENTS, {'call': 'https://call.example.com'}), patch.object(j, 'EXTERNAL_AGENT_KEY', j.API_KEY):
                self.assertIn('error', asyncio.run(j.delegate('call', 'x', approved_action_id=1)))
            with patch.dict(j.AGENTS, {'call': 'https://call.example.com'}), patch.object(j, 'EXTERNAL_AGENT_KEY', 'ext'):
                self.assertEqual(asyncio.run(j.delegate('call', 'x', approved_action_id=7)), {'ok': True})
        self.assertEqual(len(captured), 1); self.assertEqual(captured[0]['x-api-key'], 'ext')
        self.assertNotIn(j.API_KEY, json.dumps(captured))

    def test_host_allowlist(self):
        with patch.object(j, 'EXTERNAL_AGENT_HOSTS', {'ok.example.com'}):
            self.assertIn('EXTERNAL_AGENT_HOSTS', j._agent_url_problem('https://evil.example.net/a'))
            self.assertEqual(j._agent_url_problem('https://ok.example.com/a'), '')

    def test_failed_local_change_not_stuck(self):
        a = j.add_income(10)
        act = asyncio.run(j.run_tool('edit_entry', {'kind': 'income', 'id': a['id'], 'changes': {'amount': -5}}))
        with self.assertRaises(Exception): asyncio.run(e.execute_action(act['id']))
        self.assertEqual(next(x for x in e.load()['actions'] if x['id'] == act['id'])['status'], 'failed')


class Bank(Base):
    def imp(self, raw, name='a.csv'): return j.import_statement(name, raw, 'negocio')['accounts'][0]

    def test_same_day_same_amount_different_merchant_kept(self):
        self.imp(b"Date,Description,Amount\n10/05/2026,HOME DEPOT #123,-50.00\n")
        r = self.imp(b"Date,Description,Amount\n10/05/2026,LOWES #555,-50.00\n")
        self.assertEqual((r['new'], r['duplicates']), (1, 0)); self.assertEqual(len(j._kload()['tx']), 2)

    def test_csv_then_qfx_same_movement_deduped(self):
        self.imp(b"Date,Description,Amount\n10/05/2026,HOME DEPOT #123 SAN JUAN,-50.00\n")
        ofx = (b"OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><ACCTID>000123</BANKACCTFROM>"
               b"<BANKTRANLIST><STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261005<TRNAMT>-50.00<FITID>F1<NAME>THE HOME DEPOT"
               b"</STMTTRN></BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")
        r = self.imp(ofx, 'a.qfx')
        self.assertEqual((r['new'], r['duplicates']), (0, 1)); self.assertTrue(r['matched_other_format'])

    def test_reimport_same_csv_is_all_duplicates(self):
        raw = b"Date,Description,Amount\n10/05/2026,CAFE,-3.00\n10/05/2026,CAFE,-3.00\n"
        self.imp(raw); r = self.imp(raw)
        self.assertEqual((r['new'], r['duplicates']), (0, 2)); self.assertEqual(len(j._kload()['tx']), 2)

    def test_equal_coffees_in_two_files_kept_by_running_balance(self):
        self.imp(b"Date,Description,Amount,Balance\n10/05/2026,CAFE,-3.00,97.00\n")
        r = self.imp(b"Date,Description,Amount,Balance\n10/05/2026,CAFE,-3.00,94.00\n")
        self.assertEqual(r['new'], 1); self.assertEqual(len(j._kload()['tx']), 2)
        r = self.imp(b"Date,Description,Amount,Balance\n10/05/2026,CAFE,-3.00,97.00\n10/05/2026,CAFE,-3.00,94.00\n")
        self.assertEqual((r['new'], r['duplicates']), (0, 2))

    def test_different_fitids_are_different(self):
        def ofx(fid):
            return (b"OFXHEADER:100\n<OFX><STMTRS><BANKACCTFROM><ACCTID>000123</BANKACCTFROM><BANKTRANLIST><STMTTRN>"
                    b"<DTPOSTED>20261005<TRNAMT>-20.00<FITID>" + fid + b"<NAME>SHELL</STMTTRN></BANKTRANLIST></STMTRS></OFX>")
        self.imp(ofx(b'A1'), 'a.qfx'); r = self.imp(ofx(b'A2'), 'b.qfx'); self.imp(ofx(b'A2'), 'c.qfx')
        self.assertEqual(r['new'], 1); self.assertEqual(len(j._kload()['tx']), 2)


class JobPayments(Base):
    def test_payment_recorded_once_and_balance(self):
        c = j.add_client('Cliente'); job = j.add_job(c['id'], 'Gabinete', price=500, advance=100)
        j.record_job_payment(job['id'], 150)
        jobs = j._cload()['jobs']; self.assertEqual(jobs[0]['balance'], 250)
        self.assertEqual(sum(x['amount'] for x in j._bload()['income']), 150)


class BackupRestore(Base):
    def seed(self):
        j.add_income(100); c = j.add_client('Ana'); j.add_job(c['id'], 'Pintura', price=300)
        with j._data_lock:
            g = j._gload(); j.gate_add_spent(g, 80); j.gate_issue_code(g, 'cb#1'); j.gate_audit(g, 'aprobar', 'cb#1', 'x'); j._gsave(g)
            x = j._xload(); x['orders'].append({'id': 1, 'status': 'pending', 'created': j._now().isoformat()}); j._xsave(x)
        e.prepare_external_action if False else None
        d = e.load(); d['actions'].append({'id': 9, 'status': 'pending', 'created': j._now().isoformat()}); e.save(d)

    def test_backup_has_full_gate_without_codes_and_modules(self):
        self.seed(); s = j.snapshot()
        self.assertEqual(s['gate']['spent'][j._today().isoformat()], 80); self.assertEqual(s['gate']['codes'], {})
        for k in ('extensions', 'growth', 'money_audit', 'books'): self.assertIn(k, s)

    def test_dry_run_changes_nothing(self):
        self.seed(); snap = j.snapshot(); j.add_income(5)
        r = j.restore_snapshot(snap); self.assertTrue(r['dry_run']); self.assertEqual(len(j._bload()['income']), 2)

    def test_restore_keeps_limits_audit_and_voids_authorizations(self):
        self.seed(); snap = json.loads(json.dumps(j.snapshot()))
        j.add_income(5)                                        # newer data that the restore will roll back
        with j._data_lock:
            g = j._gload(); j.gate_add_spent(g, 50); j.gate_audit(g, 'confirmar', 'cb#2', 'después'); j._gsave(g)
        snap['gate']['spent'][j._today().isoformat()] = 0      # an edited copy must not reset today's spend
        r = j.restore_snapshot(snap, dry_run=False)
        self.assertFalse(r['dry_run']); self.assertEqual(len(j._bload()['income']), 1)
        g = j._gload()
        self.assertEqual(g['spent'][j._today().isoformat()], 130); self.assertEqual(g['codes'], {})
        actions = [a['action'] for a in g['audit']]; self.assertIn('restaurar', actions)
        self.assertTrue(any(a['ref'] == 'cb#2' for a in g['audit']))
        self.assertEqual(j._xload()['orders'][0]['status'], 'expired')
        self.assertEqual(next(a for a in e.load()['actions'] if a['id'] == 9)['status'], 'expired')
        self.assertTrue((j.DATA_DIR / (r['pre_restore_copy'].replace(':', '_') + '.json')).exists())

    def test_old_400_backup_keeps_current_gate(self):
        self.seed(); snap = j.snapshot(); snap.pop('gate'); snap['version'] = '4.0.0'
        r = j.restore_snapshot(snap, dry_run=False)
        self.assertIn('se conservó', r['sections']['gate']['note']); self.assertEqual(j.gate_spent_today(j._gload()), 80)

    def test_rejects_garbage(self):
        for bad in ({}, {'taken_at': 'x'}, {'taken_at': 'x', 'books': []}, {'taken_at': 'x', 'books': {'income': 'no'}}):
            with self.assertRaises(ValueError): j.restore_snapshot(bad)

    def test_restore_endpoint_dry_run(self):
        from fastapi.testclient import TestClient
        self.seed(); c = TestClient(j.app); h = {'x-api-key': j.API_KEY}
        snap = c.get('/backup', headers=h).json()
        r = c.post('/restore', headers=h, json={'backup': snap}).json(); self.assertTrue(r['dry_run'])
        r = c.post('/restore', headers=h, json={'backup': snap, 'confirm': 'RESTAURAR'}).json(); self.assertFalse(r['dry_run'])


class TelegramQueue(Base):
    def test_duplicate_update_ignored(self):
        m = self.tg('/hoy', 10)['message']
        self.assertEqual(j._tg_enqueue(10, m), 'new'); self.assertEqual(j._tg_enqueue(10, m), 'dup')

    def test_webhook_queues_before_answering_and_runs_once(self):
        from fastapi.testclient import TestClient
        j.TG_SECRET = 'sec'; c = TestClient(j.app); h = {'x-telegram-bot-api-secret-token': 'sec'}
        with patch.object(j, '_tg_send', new=AsyncMock()) as send:
            c.post('/telegram', headers=h, json=self.tg('/ayuda', 11)); c.post('/telegram', headers=h, json=self.tg('/ayuda', 11))
        self.assertEqual(send.await_count, 1); self.assertEqual(j._tg_pending_ids(), [])

    def test_crash_before_processing_is_recovered(self):
        j._tg_enqueue(12, self.tg('/ayuda', 12)['message'])     # process died before background task ran
        with patch.object(j, '_tg_send', new=AsyncMock()) as send:
            asyncio.run(j._tg_recover_pass(final=False))
        self.assertIn('Atajos', send.await_args.args[1]); self.assertEqual(j._tg_stats['recovered'], 1)
        self.assertEqual(j._tg_pending_ids(), [])

    def test_crash_while_running_is_reported_not_repeated(self):
        j.TG_TOKEN = 'x'
        j._tg_enqueue(13, self.tg('cobré 200 a Ana', 13)['message']); j._tg_claim(13)
        with patch.object(j, '_handle_tg', new=AsyncMock()) as ai, patch.object(j, '_tg_send', new=AsyncMock()) as send:
            asyncio.run(j._tg_recover_pass(final=False))     # too recent: an old instance may still finish it
            send.assert_not_called()
            asyncio.run(j._tg_recover_pass(final=True))
        ai.assert_not_called(); self.assertIn('Puede haberse hecho en parte', send.await_args.args[1])
        self.assertEqual(j._tg_pending_ids(), [])

    def test_stale_queue_not_executed(self):
        j.TG_TOKEN = 'x'
        j._tg_enqueue(14, self.tg('/ayuda', 14)['message'])
        inbox = j.kv_get(j.TG_INBOX_KEY, {}); inbox['14']['at'] = '2020-01-01T00:00:00-04:00'; j.kv_set(j.TG_INBOX_KEY, inbox)
        with patch.object(j, '_tg_send', new=AsyncMock()) as send:
            asyncio.run(j._tg_recover_pass(final=False))
        self.assertIn('más de 6 horas', send.await_args.args[1])


class Fencing(Base):
    def setUp(self):
        super().setUp(); self.r = FakeRedis(); self.p = patch.object(j, '_redis', new=self.r); self.p.start(); j.USE_REDIS = True
    def tearDown(self): self.p.stop(); j.USE_REDIS = False; j._fence.update(mode='off', leader=True)

    def test_old_instance_cannot_overwrite_new(self):
        j.fence_take_leadership(); self.assertEqual(j._fence['mode'], 'on')
        j.kv_set('jarvis:books', {'income': [1]})
        self.r.d[j.LEADER_KEY] = 'new-instance'                   # a newer deploy booted
        with self.assertRaises(j.StaleInstance): j.kv_set('jarvis:books', {'income': []})
        self.assertEqual(json.loads(self.r.d['jarvis:books']), {'income': [1]})
        with self.assertRaises(j.StaleInstance): j._tg_enqueue(20, {'chat': {'id': 1}})
        self.assertNotIn('jarvis:tg:upd:20', self.r.d)              # Telegram will retry against the new one

    def test_queue_on_redis_and_atomic_multi_write(self):
        j.fence_take_leadership()
        self.assertEqual(j._tg_enqueue(21, {'chat': {'id': 1}}), 'new'); self.assertEqual(j._tg_enqueue(21, {}), 'dup')
        self.assertEqual(j._tg_pending_ids(), [21]); self.assertIsNotNone(j._tg_claim(21)); self.assertIsNone(j._tg_claim(21))
        j._tg_job_finish(21); self.assertEqual(j._tg_pending_ids(), [])
        j.kv_set_many({'a': 1, 'b': 2}); self.assertEqual((self.r.d['a'], self.r.d['b']), ('1', '2'))

    def test_claim_without_cjson_keeps_message_and_runs_once(self):
        j.fence_take_leadership()
        tricky = 'cobré "200" ñ 😀 \\ {"state": "queued", "x": 1}\nfin'
        self.assertEqual(j._tg_enqueue(30, {'chat': {'id': 1}, 'text': tricky}), 'new')
        self.assertTrue(self.r.d[j.TG_JOB + '30'].startswith(j._TG_QUEUED_PREFIX))
        job = j._tg_claim(30)
        self.assertEqual((job['state'], job['msg']['text'], job['id']), ('running', tricky, 30))
        self.assertIsNone(j._tg_claim(30))
        self.assertEqual(j._tg_enqueue(30, {'chat': {'id': 1}, 'text': tricky}), 'dup')
        self.assertNotIn('cjson', j._CLAIM_JOB)

    def test_claim_refuses_unknown_format(self):
        j.fence_take_leadership()
        self.r.d[j.TG_JOB + '31'] = json.dumps({'id': 31, 'msg': {}, 'state': 'queued', 'at': 'x'})
        self.assertIsNone(j._tg_claim(31)); self.assertIn('"state": "queued"', self.r.d[j.TG_JOB + '31'])

    def test_without_eval_refuses_unprotected_writes(self):
        def no_eval(cmd):
            if cmd[0] == 'EVAL': raise RuntimeError('EVAL unavailable')
            return self.r(cmd)
        with patch.object(j, '_redis', new=no_eval):
            with self.assertRaises(RuntimeError): j.fence_take_leadership()
            self.assertEqual(j._fence['mode'], 'unavailable')
            with self.assertRaises(j.StaleInstance): j.kv_set('k', {'v': 1})
            with self.assertRaises(j.StaleInstance): j._tg_enqueue(22, {})
        self.assertNotIn('k', self.r.d)


class PracticeVsReal(Base):
    def test_real_trading_off_and_confirm_refuses(self):
        self.assertFalse(j.CB_TRADING)
        with j._data_lock:
            x = j._xload(); x['orders'].append({'id': 3, 'status': 'pending', 'created': j._now().isoformat(),
                                                'usd_estimate': 10, 'product': 'BTC-USD', 'side': 'BUY', 'uuid': 'u',
                                                'config': {'market_market_ioc': {'quote_size': '10'}}}); j._xsave(x)
        # 4.0.3: a real proposal while Jarvis is in practice mode is annulled, never approved
        msg = j.cb_approve_text('3'); self.assertIn('no se hizo nada', msg); self.assertNotRegex(msg, r'/confirmar 3 \d{6}')
        with patch.object(j, '_cb', new=AsyncMock()) as cb:
            asyncio.run(j.cb_confirm_text('3 123456'))
        cb.assert_not_called()

    def test_hard_limits_cannot_be_raised(self):
        with patch.dict(os.environ, {'MONEY_MAX_ORDER_USD': '5000'}):
            self.assertEqual(j._lower_only(('MONEY_MAX_ORDER_USD',), j.HARD_MAX_ORDER_USD), 100.0)
        self.assertEqual((j.MONEY_MAX_ORDER, j.MONEY_MAX_DAY), (100.0, 300.0))

    def test_practice_approval_moves_nothing(self):
        with patch.object(j, '_cb', new=AsyncMock()) as cb:
            text = j.cb_approve_text('0'); code = text.split('/confirmar 0 ')[1][:6]
            self.assertIn('no se movió nada', asyncio.run(j.cb_confirm_text('0 ' + code)))
        cb.assert_not_called()


class Diagnostics(Base):
    def test_diagnostics_without_ai_or_telegram(self):
        j.TG_TOKEN = ''
        text = asyncio.run(j.diagnostics_text())
        self.assertIn(j.VERSION, text); self.assertIn('no se hacen llamadas de pago', text); self.assertIn('apagadas', text)

    def test_diagnostics_reports_unknown_model(self):
        from anthropic import NotFoundError
        req = httpx.Request('GET', 'https://api.anthropic.com/v1/models/x')
        err = NotFoundError('nf', response=httpx.Response(404, request=req), body=None)
        with patch.object(j, 'AI_READY', True), patch.object(j.client.models, 'retrieve', new=AsyncMock(side_effect=err)):
            self.assertIn('no existe', asyncio.run(j.diagnostics_text()))


if __name__ == '__main__':
    unittest.main(verbosity=1)
