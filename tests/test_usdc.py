"""Pruebas de jarvis_usdc con datos ficticios. Sin red."""
import datetime as dt, hashlib, hmac, json, os, sys, unittest
from unittest.mock import patch
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import jarvis_usdc as u

BODY = json.dumps({"id": "evt_ficticio_1", "type": "charge:confirmed"}).encode()
ENV = {"COINBASE_COMMERCE_WEBHOOK_SECRET": "secreto-ficticio", "STRIPE_WEBHOOK_SECRET": "whsec_ficticio"}


@patch.dict(os.environ, ENV)
class Webhooks(unittest.TestCase):
    def test_coinbase_ok_y_mala(self):
        sig = hmac.new(b"secreto-ficticio", BODY, hashlib.sha256).hexdigest()
        ev = u.verify_coinbase(BODY, sig)
        self.assertTrue(u.payment_summary("coinbase", ev)["confirmed"])
        with self.assertRaises(u.VerificationError):
            u.verify_coinbase(BODY, "0" * 64)

    def test_stripe_ok_vencido(self):
        body = json.dumps({"id": "evt_f2", "type": "payment_intent.succeeded"}).encode()
        sig = hmac.new(b"whsec_ficticio", b"1000." + body, hashlib.sha256).hexdigest()
        self.assertEqual(u.verify_stripe(body, f"t=1000,v1={sig}", now=1100)["id"], "evt_f2")
        with self.assertRaises(u.VerificationError):
            u.verify_stripe(body, f"t=1000,v1={sig}", now=99999)

    def test_falta_secreto(self):
        with patch.dict(os.environ, {"COINBASE_COMMERCE_WEBHOOK_SECRET": ""}):
            with self.assertRaises(u.VerificationError):
                u.verify_coinbase(BODY, "x")


class Credits(unittest.TestCase):
    def test_flujo(self):
        d = dt.date(2026, 10, 13)
        l = u.CreditLedger(expiry_days=30)
        self.assertTrue(l.grant("cliente-ficticio", 100, "evt1", d))
        self.assertFalse(l.grant("cliente-ficticio", 100, "evt1", d))
        self.assertEqual(l.consume("cliente-ficticio", 40, d), 60)
        self.assertEqual(l.balance("cliente-ficticio", d + dt.timedelta(days=31)), 0)
        with self.assertRaises(PermissionError):
            l.transfer("a", "b", 1)
        with self.assertRaises(PermissionError):
            l.cash_out("a")
        with self.assertRaises(ValueError):
            l.consume("cliente-ficticio", 999, d)

    def test_resumen_solo_aviso(self):
        self.assertEqual(u.payment_summary("stripe", {"type": "x"})["action"], "solo_aviso")


if __name__ == "__main__":
    unittest.main()
