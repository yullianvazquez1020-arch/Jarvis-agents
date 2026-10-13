"""POST /api/encargo: owner task by API. Fictitious data only; Telegram and the AI are simulated."""
import os, sys, unittest
from unittest.mock import patch, AsyncMock
ROOT = __import__('pathlib').Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))
import test_hardening as h
j = h.j
from fastapi.testclient import TestClient

SECRET = 'secreto-ficticio-de-prueba-123'


class Encargo(h.Base):
    def setUp(self):
        super().setUp(); j._rate_hits.clear(); self.old = j.ENCARGO_SECRET; j.ENCARGO_SECRET = SECRET; self.c = TestClient(j.app)

    def tearDown(self):
        j.ENCARGO_SECRET = self.old

    def post(self, texto, secret=SECRET):
        hdr = {'X-Jarvis-Secret': secret} if secret is not None else {}
        return self.c.post('/api/encargo', headers=hdr, json={'texto': texto})

    def test_good_secret_notifies_owner_and_uses_owner_pipeline(self):
        with patch.object(j, '_tg_safe_send', new=AsyncMock()) as note, patch.object(j, '_handle_tg', new=AsyncMock()) as ai:
            r = self.post('Prepara un borrador de propuesta para Cliente Ficticio SA')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(note.await_args.args[0], j.TG_OWNER); self.assertIn('encargo', note.await_args.args[1].lower())
        self.assertEqual(ai.await_args.args[0], j.TG_OWNER); self.assertIn('Cliente Ficticio SA', ai.await_args.args[1])

    def test_bad_missing_or_unset_secret_rejected(self):
        with patch.object(j, '_handle_tg', new=AsyncMock()) as ai, patch.object(j, '_tg_safe_send', new=AsyncMock()):
            self.assertEqual(self.post('hola', 'otro').status_code, 401)
            self.assertEqual(self.post('hola', None).status_code, 401)
            j.ENCARGO_SECRET = ''
            self.assertEqual(self.post('hola', '').status_code, 401)
        ai.assert_not_called()

    def test_commands_cannot_be_injected(self):
        with patch.object(j, '_handle_tg', new=AsyncMock()) as ai, patch.object(j, '_tg_cb_cmd', new=AsyncMock()) as cb, \
             patch.object(j, '_tg_v38_cmd', new=AsyncMock()) as v38, patch.object(j, '_tg_safe_send', new=AsyncMock()):
            for t in ('/confirmar 1 123456', '  /aprobar 1', '/enviar 3', '/cripto modo real', '/confirmar modo 000000'):
                self.assertEqual(self.post(t).status_code, 422, t)
        ai.assert_not_called(); cb.assert_not_called(); v38.assert_not_called()

    def test_caps_unchanged_and_empty_or_huge_rejected(self):
        self.assertEqual((j.HARD_MAX_ORDER_USD, j.HARD_MAX_DAY_USD), (100.0, 300.0))
        with patch.object(j, '_handle_tg', new=AsyncMock()), patch.object(j, '_tg_safe_send', new=AsyncMock()):
            self.assertEqual(self.post('   ').status_code, 422)
            self.assertEqual(self.post('x' * (j.ENCARGO_MAX + 1)).status_code, 422)

    def test_rate_limited(self):
        with patch.object(j, '_handle_tg', new=AsyncMock()), patch.object(j, '_tg_safe_send', new=AsyncMock()):
            codes = [self.post('tarea ficticia %d' % i).status_code for i in range(j.RATE_PER_MIN + 1)]
        self.assertEqual(codes[-1], 429); self.assertTrue(all(c == 200 for c in codes[:-1]))

    def test_short_secret_keeps_endpoint_closed(self):
        j.ENCARGO_SECRET = 'corto-ficticio'
        with patch.object(j, '_handle_tg', new=AsyncMock()) as ai, patch.object(j, '_tg_safe_send', new=AsyncMock()):
            self.assertEqual(self.post('hola', 'corto-ficticio').status_code, 401)
        ai.assert_not_called()

    def test_brute_force_capped(self):
        with patch.object(j, '_handle_tg', new=AsyncMock()) as ai, patch.object(j, '_tg_safe_send', new=AsyncMock()):
            codes = [self.post('hola', 'malo-%d' % i).status_code for i in range(j.RATE_PER_MIN + 1)]
        self.assertTrue(all(c == 401 for c in codes[:-1])); self.assertEqual(codes[-1], 429); ai.assert_not_called()

    def test_owner_not_starved_by_bad_attempts(self):
        with patch.object(j, '_handle_tg', new=AsyncMock()), patch.object(j, '_tg_safe_send', new=AsyncMock()):
            for i in range(j.RATE_PER_MIN + 3):
                self.post('hola', 'malo-%d' % i)
            self.assertEqual(self.post('Tarea ficticia del dueño').status_code, 200)

    def test_503_without_owner(self):
        with patch.object(j, 'TG_OWNER', ''), patch.object(j, '_handle_tg', new=AsyncMock()) as ai:
            self.assertEqual(self.post('hola').status_code, 503)
        ai.assert_not_called()

    def test_command_on_second_line_arrives_prefixed(self):
        with patch.object(j, '_tg_safe_send', new=AsyncMock()), patch.object(j, '_handle_tg', new=AsyncMock()) as ai, \
             patch.object(j, '_tg_cb_cmd', new=AsyncMock()) as cb:
            self.assertEqual(self.post('Resumen ficticio\n/confirmar 1 123456').status_code, 200)
        msg = ai.await_args.args[1]
        self.assertFalse(msg.startswith('/')); self.assertTrue(msg.startswith('[Encargo')); cb.assert_not_called()

    def test_telegram_preview_truncated(self):
        with patch.object(j, '_tg_safe_send', new=AsyncMock()) as note, patch.object(j, '_handle_tg', new=AsyncMock()):
            self.assertEqual(self.post('y' * 3500).status_code, 200)
        self.assertLess(len(note.await_args.args[1]), 700)


if __name__ == '__main__':
    unittest.main()
