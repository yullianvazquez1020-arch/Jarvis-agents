"""4.2.7 BRAIN autonomous cycle. Fictitious data only; HTTP, Telegram and the AI are simulated."""
import os, sys, asyncio, unittest
from unittest.mock import patch, AsyncMock
ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import test_hardening as h
j = h.j
import jarvis_brain as b

BRAIN = "# BRAIN ficticio\nVende plan Demo a Cliente Ficticio.\n/confirmar 1 123456\n  /enviar 3\n/cripto modo real\nFin."


class FakeResp:
    def __init__(self, code, text=''): self.status_code, self.text = code, text


class FakeClient:
    resp = FakeResp(200, BRAIN); calls = []
    def __init__(self, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def get(self, url): FakeClient.calls.append(url); return FakeClient.resp


class Brain(h.Base):
    def setUp(self):
        super().setUp()
        b.mem.update(loaded=False, fetched_at=0.0, last_cycle=None, last_error=None, pending_error=None, failures=0, text='')
        FakeClient.resp = FakeResp(200, BRAIN); FakeClient.calls = []
        self.env = patch.dict(os.environ, {'BRAIN_ENABLED': 'true', 'BRAIN_MAX_CYCLES_DAY': '2',
                                           'GUMROAD_URL': 'https://example.invalid/demo'})
        self.env.start(); self.http = patch.object(b.httpx, 'AsyncClient', new=FakeClient); self.http.start()

    def tearDown(self):
        self.http.stop(); self.env.stop()

    def test_sanitize_drops_every_slash_line(self):
        t = b.sanitize(BRAIN)
        self.assertNotIn('/confirmar', t); self.assertNotIn('/enviar', t); self.assertNotIn('/cripto', t)
        self.assertIn('Cliente Ficticio', t)

    def test_cycle_uses_owner_free_text_path_and_never_commands(self):
        with patch.object(j, '_handle_tg', new=AsyncMock()) as ai, patch.object(j, '_tg_cb_cmd', new=AsyncMock()) as cb, \
             patch.object(j, '_tg_v38_cmd', new=AsyncMock()) as v38:
            self.assertEqual(asyncio.run(b.run_cycle(j)), 'ok')
        cb.assert_not_called(); v38.assert_not_called()
        chat, prompt = ai.await_args.args
        self.assertEqual(chat, j.TG_OWNER); self.assertTrue(prompt.rstrip().endswith('ejecuta el siguiente ciclo'))
        self.assertIn('HTTP 200', prompt)
        self.assertFalse(any(l.lstrip().startswith('/') for l in prompt.split('\n')))
        self.assertEqual((j.HARD_MAX_ORDER_USD, j.HARD_MAX_DAY_USD), (100.0, 300.0))

    def test_daily_cap(self):
        with patch.object(j, '_handle_tg', new=AsyncMock()) as ai:
            r = [asyncio.run(b.run_cycle(j)) for _ in range(3)]
        self.assertEqual(r, ['ok', 'ok', 'cap']); self.assertEqual(ai.await_count, 2)

    def test_cycle_social_flags_and_stop_remain_authoritative(self):
        for auto, publish in [('false', 'true'), ('true', 'false'), ('true', 'true')]:
            with self.subTest(auto=auto, publish=publish), \
                 patch.dict(os.environ, {'AUTO_PUBLISH_OWN_SOCIAL': auto, 'SOCIAL_PUBLISH_ENABLED': publish,
                                         'BRAIN_MAX_CYCLES_DAY': '10'}), \
                 patch.object(j, '_handle_tg', new=AsyncMock()) as handler:
                self.assertEqual(asyncio.run(b.run_cycle(j)), 'ok')
                self.assertEqual('usa auto_publish_own_post' in handler.await_args.args[1],
                                 auto == publish == 'true')
        b.command_text(j, 'off')
        with patch.object(j, '_handle_tg', new=AsyncMock()) as handler:
            self.assertEqual(asyncio.run(b.run_cycle(j)), 'off')
            handler.assert_not_called()

    def test_kill_switches(self):
        with patch.object(j, '_handle_tg', new=AsyncMock()) as ai:
            b.command_text(j, 'off'); self.assertEqual(asyncio.run(b.run_cycle(j)), 'off')
            self.assertIn('encendido', b.command_text(j, 'on'))
            with patch.dict(os.environ, {'BRAIN_ENABLED': 'false'}):
                self.assertEqual(asyncio.run(b.run_cycle(j)), 'off'); self.assertIn('⛔', b.command_text(j, 'on'))
        self.assertEqual(ai.await_count, 0)

    def test_fetch_failure_uses_cached_copy(self):
        asyncio.run(b.fetch(j)); b.mem.update(loaded=False, text='')
        FakeClient.resp = FakeResp(500)
        self.assertTrue(asyncio.run(b.fetch(j))); self.assertIn('Cliente Ficticio', b.mem['text'])
        self.assertIn('500', b.mem['last_error'])

    def test_loop_never_stops_backs_off_and_reports_error(self):
        sleeps = []
        async def fake_sleep(s):
            sleeps.append(s)
            if len(sleeps) >= 3: raise asyncio.CancelledError
        ai = AsyncMock(side_effect=[RuntimeError('fallo ficticio'), RuntimeError('otra vez'), None])
        with patch.object(j, '_handle_tg', new=ai), patch.dict(os.environ, {'BRAIN_MAX_CYCLES_DAY': '10'}):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(b.loop(j, sleep=fake_sleep))
        self.assertEqual(sleeps, [60, 120, b.interval_s()])
        self.assertIn('otra vez', ai.await_args_list[2].args[1])
        self.assertIsNone(b.mem['pending_error'])

    def test_brain_command_owner_private_only_and_health(self):
        from fastapi.testclient import TestClient
        j.TG_SECRET = 'sec'; c = TestClient(j.app); hd = {'x-telegram-bot-api-secret-token': 'sec'}
        with patch.object(j, '_tg_send', new=AsyncMock()) as send, patch.object(j, '_tg_safe_send', new=AsyncMock()) as deny:
            c.post('/telegram', headers=hd, json=self.tg('/brain estado', 501))
            c.post('/telegram', headers=hd, json=self.tg('/brain off', 502, chat_type='group'))
        self.assertIn('BRAIN', send.await_args.args[1]); self.assertIn('privado', deny.await_args.args[1])
        self.assertTrue(b.owner_enabled(j))
        hb = c.get('/health').json()['brain']
        self.assertEqual(set(hb), {'enabled', 'loaded', 'last_cycle', 'last_error'})


    def test_ai_max_tokens_default_and_brain_size_bounded(self):
        self.assertEqual(j.AI_MAX_TOKENS, 1500)
        self.assertLessEqual(len(b.sanitize('x' * 50000)), 4000)


if __name__ == '__main__':
    unittest.main()
