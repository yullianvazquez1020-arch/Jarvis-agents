"""Paired voice consultations reuse business reports, without models or Telegram sends."""
from types import SimpleNamespace
from unittest.mock import patch
from desktop_helpers import DesktopBase, D, j


class BusinessVoice(DesktopBase):
    def test_brief_reuses_report_and_remains_read_only(self):
        token, _ = self.pair()
        calls = []
        def brief():
            self.assertTrue(j._WRITE_BLOCK.get())
            calls.append('brief')
            return 'Caja observada: $500.00\nNo es ganancia.'
        with patch.object(j, '_brief', SimpleNamespace(commercial_brief=brief), create=True):
            turn = self.turn(token, 'dame resumen comercial').json()
            panel = self.client.post('/desktop/v1/panel', headers=self.hdr(token), json={'name':'brief'}).json()
        self.assertEqual(turn['kind'], 'panel')
        self.assertFalse(turn['llm_used'])
        self.assertIn('$500.00', '\n'.join(panel['lines']))
        self.assertEqual(calls, ['brief', 'brief'])
        self.assertFalse(self.sent)

    def test_cash_reuses_report_without_ai(self):
        token, _ = self.pair()
        def cash():
            self.assertTrue(j._WRITE_BLOCK.get())
            return 'Sin proyección: falta saldo observado.'
        with patch.object(j, '_business_workflows', SimpleNamespace(cash_text=cash)):
            turn = self.turn(token, 'muéstrame la caja').json()
            panel = self.client.post('/desktop/v1/panel', headers=self.hdr(token), json={'name':'caja'}).json()
        self.assertEqual(turn['kind'], 'panel')
        self.assertFalse(turn['llm_used'])
        self.assertIn('falta saldo', '\n'.join(panel['lines']))
        self.assertFalse(self.sent)

    def test_new_panels_still_require_pairing(self):
        for name in ('brief', 'caja'):
            response = self.client.post('/desktop/v1/panel', json={'name':name})
            self.assertEqual(response.status_code, 401)

    def test_approvals_still_stay_in_private_telegram(self):
        self.assertEqual(D.classify('aprueba el pago')[0], 'refuse')
        self.assertEqual(D.classify('/confirmar 123456')[0], 'refuse')
