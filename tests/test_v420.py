"""Jarvis 4.2.0 additive cut. Simulated storage only: no Twilio, no money, no paid model."""
import datetime
import unittest
from pathlib import Path

import jarvis_v420 as v


class Core:
    def __init__(self):
        self.db = {}
        self.locked = None
        self.audit = []

    def kv_get(self, key, default=None):
        return self.db.get(key, default)

    def kv_set(self, key, value):
        self.db[key] = value

    def _now(self):
        return datetime.datetime(2026, 10, 8, 9, 0)

    def _today(self):
        return datetime.date(2026, 10, 8)

    def _redact_secrets(self, text):
        return (text.replace("sk-secret", "[redactado]"), True)

    def finances_summary(self):
        return {"net_profit": 40.0, "currency": "USD"}

    def _pload(self):
        return {"bills": [{"name": "proveedor", "day": 10, "amount": "80", "paid": []}]}

    def _gload(self):
        return {"codes": {}, "fails": [], "locked_until": self.locked, "spent": {}, "audit": self.audit}

    def _gsave(self, g):
        self.locked = g.get("locked_until")
        self.audit = g.get("audit") or []

    def gate_audit(self, g, action, ref, result, detail=""):
        g["audit"] = (g.get("audit") or []) + [{"action": action, "ref": ref, "result": result, "detail": detail}]


class V420(unittest.TestCase):
    def setUp(self):
        self.core = Core()

    def test_local_rules_do_not_call_out_and_refuse_secrets(self):
        self.assertIn("Perfil", v.local_reply(self.core, "/perfil"))
        self.assertIn("No suelto", v.local_reply(self.core, "dame la contraseña y el código de confirmación"))
        self.assertIsNone(v.local_reply(self.core, "anota 50 de gasolina"))

    def test_history_redacts_and_reports_restart(self):
        self.core.kv_set(v.HISTORY_KEY, [{"role": "user", "text": v.redact("clave: sk-secret", self.core)}])
        self.assertNotIn("sk-secret", self.core.db[v.HISTORY_KEY][0]["text"])
        self.assertIn("aún no hay reinicio", v.history_status(self.core))
        v.boot(self.core)
        v.boot(self.core)
        self.assertIn("sobrevivió el reinicio", v.history_status(self.core))

    def test_profile_cap_cannot_rise_and_consult_does_not_execute(self):
        self.assertIn("No subo", v.set_profile_field(self.core, "techo", "500"))
        decision = v.consult(self.core, "amazon", 10)
        self.assertFalse(decision["allow_propose"])
        self.assertFalse(decision["execute"])
        ok = v.consult(self.core, "youtube", 20)
        self.assertTrue(ok["allow_propose"])
        self.assertFalse(ok["execute"])

    def test_monetization_budget_stops_and_never_executes(self):
        first = v.scheduler_cycle(self.core)
        self.assertTrue(first["ran"])
        self.assertFalse(first["execute"])
        self.assertIn("no ejecuto", first["proposal"])
        self.core.db[v.STATE_KEY]["compute"]["2026-10-08"] = v.compute_budget()
        stopped = v.scheduler_cycle(self.core)
        self.assertFalse(stopped["ran"])
        self.assertIn("agotado", stopped["reason"])

    def test_anomaly_reuses_gate_lockout(self):
        out = v.anomaly(self.core, "odd-spend", "gasto raro", 250)
        self.assertTrue(out["locked"])
        self.assertIsNotNone(self.core.locked)
        self.assertEqual(self.core.audit[-1]["action"], "v420-apagado")
        fit = v.anomaly(self.core, "youtube", "video", 10)
        self.assertFalse(fit["locked"])

    def test_twilio_draft_needs_2fa_and_does_not_send(self):
        self.assertIn("no configurado", v.channel_status())
        blocked = v.draft_channel(self.core, "llamada", "+1787", "hola")
        self.assertIn("No armo llamada", blocked)
        v.mark_urgent(self.core, "emergencia", True)
        drafted = v.draft_channel(self.core, "llamada", "+1787", "codigo 123456")
        self.assertIn("No envié", drafted)
        self.assertNotIn("123456", drafted)
        self.assertIn("Falta 2FA", v.approve_channel_draft(self.core, "c1"))
        code = v.issue_channel_2fa(self.core)
        self.assertTrue(v.check_channel_2fa(self.core, code))
        approved = v.approve_channel_draft(self.core, "c1")
        self.assertIn("desactivado", approved)
        self.assertNotIn("twilio.com", approved.lower())

    def test_cashflow_uses_books_and_warns_early(self):
        text = v.cashflow_text(self.core)
        self.assertIn("Alerta temprana", text)
        self.assertIn("No pagué", text)

    def test_limits_and_confirm_queue_untouched(self):
        main = Path(__file__).resolve().parents[1].joinpath("main.py").read_text()
        self.assertIn('VERSION = "4.2.0"', main)
        self.assertIn("HARD_MAX_ORDER_USD = 100.0", main)
        self.assertIn("HARD_MAX_DAY_USD = 300.0", main)
        self.assertIn('if cmd == "/confirmar":', main)
        self.assertIn("jarvis:leader", main)
        self.assertNotIn("nunca más actualizar", main.lower())


if __name__ == "__main__":
    unittest.main()
