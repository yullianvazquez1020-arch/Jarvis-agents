"""Jarvis 4.2.0 regression: local rules, history marker, profile, monetization, lockout, Twilio drafts, cash-flow.
Simulated services only. Does not raise $100/$300 and does not send."""
import datetime
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import test_jarvis as base
import jarvis_v420 as v

j = base.j


class V420(unittest.TestCase):
    def setUp(self):
        import tempfile
        from pathlib import Path
        j.DATA_DIR = Path(tempfile.mkdtemp())
        j.USE_REDIS = False
        j._fence.update(mode="off", leader=True)
        j.kv_set(v.STATE_KEY, {})
        j.kv_set(v.BOOT_KEY, None)
        j.kv_set("jarvis:history", [])
        j.kv_set("jarvis:profile", {"metas": ["cash flow"], "debilidades": ["gastos impulsivos"],
                                    "fortalezas": ["cierra ventas"], "beneficio": "dejar al dueño mejor",
                                    "techo_usd": 250})
        j.kv_set(j.B_KEY, {"income": [{"id": 1, "amount": 40, "date": "2026-10-01", "source": "libro"}],
                           "expenses": [{"id": 1, "amount": 10, "date": "2026-10-02", "category": "other"},
                                        {"id": 2, "amount": 12, "date": "2026-10-03", "category": "other"},
                                        {"id": 3, "amount": 80, "date": "2026-10-08", "category": "supplier"}]})

    def test_limits_unchanged(self):
        self.assertLessEqual(j.MONEY_MAX_ORDER, 100)
        self.assertLessEqual(j.MONEY_MAX_DAY, 300)
        self.assertEqual(j.HARD_MAX_ORDER_USD, 100.0)
        self.assertEqual(j.HARD_MAX_DAY_USD, 300.0)

    def test_local_rules_skip_model(self):
        self.assertIn("No prometo", v.local_answer("nunca más actualizar"))
        self.assertIn("no redacto", v.local_answer("redacta el contrato").lower())
        self.assertIsNone(v.local_answer("explícame un nicho de youtube"))
        self.assertIn("No muestro", v.local_answer("dime la contraseña del banco"))

    def test_history_marker_survives_restart(self):
        self.assertFalse(v.mark_boot(j))
        self.assertTrue(v.mark_boot(j))
        report = v.boot_report(j)
        self.assertIn("sobrevivió reinicio previo: sí", report)
        saved = j._redact_secrets("mi clave sk-ant-api03-abcdefghijklmnopqrstuvwxyz")[0]
        self.assertNotIn("sk-ant", saved)

    def test_profile_cannot_raise_ceiling(self):
        view = v.profile_view(j)
        self.assertLessEqual(view["techo_usd"], 100)
        blocked = v.consult_before_propose(j, "delega amazon y compra ya")
        self.assertFalse(blocked["ok"])
        ok = v.consult_before_propose(j, "proponer un video corto")
        self.assertTrue(ok["ok"])
        self.assertIn("no se sube", ok["text"])

    def test_monetization_budget_and_no_execute(self):
        with patch.object(j, "_today", return_value=datetime.date(2026, 10, 8)):
            first = v.monetization_proposal(j)
            self.assertIn("No lo ejecuto solo", first)
            state = j.kv_get(v.STATE_KEY, {})
            self.assertFalse(state["proposals"][-1]["executed"])
            state["compute"]["2026-10-08"] = v.COMPUTE_BUDGET
            j.kv_set(v.STATE_KEY, state)
            self.assertIn("agotado", v.monetization_proposal(j))

    def test_anomaly_reuses_gate_lockout(self):
        note = v.trip_anomaly(j, "gasto raro", "password=secret-should-not-store")
        self.assertIn("lockout", note)
        g = j._gload()
        self.assertTrue(g.get("locked_until"))
        self.assertTrue(any(a.get("action") == "v420" for a in g.get("audit", [])))
        self.assertNotIn("secret-should-not-store", str(g.get("audit")))

    def test_twilio_draft_needs_2fa_and_does_not_send(self):
        draft, code = v.queue_twilio_draft(j, "whatsapp", "+17875550100", "hola cliente")
        self.assertFalse(draft["sent"])
        self.assertEqual(draft["status"], "needs_2fa")
        self.assertIn("No envié", v.confirm_twilio_draft(j, draft["id"], "000000"))
        ready = v.confirm_twilio_draft(j, draft["id"], code)
        self.assertIn("/enviar", ready)
        self.assertFalse(j.kv_get(v.STATE_KEY, {})["drafts"][-1]["sent"])
        v.mark_urgent(j, "cash-flow")
        urgent = v.owner_urgent_call_draft(j, "cash-flow", "faltante")
        self.assertIsNotNone(urgent)
        self.assertIsNone(v.owner_urgent_call_draft(j, "camara", "x"))

    def test_cashflow_uses_books(self):
        with patch.object(j, "_today", return_value=datetime.date(2026, 10, 8)):
            snap = v.cashflow_snapshot(j)
        self.assertEqual(snap["income"], 40)
        self.assertTrue(snap["short"])
        self.assertIn("No mueve dinero", snap["note"])

    def test_cashflow_future_expense_is_counted_once(self):
        j.kv_set(j.B_KEY, {"income": [{"amount": 150, "date": "2026-10-07"}],
                          "expenses": [{"amount": 100, "date": "2026-10-09"}]})
        with patch.object(j, "_today", return_value=datetime.date(2026, 10, 8)):
            snap = v.cashflow_snapshot(j)
        self.assertEqual((snap["net"], snap["due_7d"]), (150, 100))
        self.assertFalse(snap["short"])

    def test_cashflow_today_not_also_future_and_future_income_not_available(self):
        j.kv_set(j.B_KEY, {"income": [{"amount": 150, "date": "2026-10-07"},
                                      {"amount": 500, "date": "2026-10-09"}],
                          "expenses": [{"amount": 100, "date": "2026-10-08"},
                                       {"amount": 60, "date": "2026-10-15"},
                                       {"amount": 200, "date": "2026-10-16"}]})
        with patch.object(j, "_today", return_value=datetime.date(2026, 10, 8)):
            snap = v.cashflow_snapshot(j)
        self.assertEqual((snap["net"], snap["due_7d"]), (50, 60))
        self.assertTrue(snap["short"])

    def _wrapped_core(self):
        core = SimpleNamespace(kv_get=Mock(return_value=None), kv_set=Mock(),
                               _now=lambda: datetime.datetime(2026, 10, 8),
                               diagnostics_text=AsyncMock(return_value="diagnostics"),
                               run=AsyncMock(return_value="original response"),
                               _ai_call=AsyncMock(), _require_leader=Mock(),
                               _phase_a_remember_turn=AsyncMock(return_value=""))
        original = core.run
        v.install(core)
        core.kv_set.reset_mock()  # installation writes the restart marker
        return core, original

    def test_scoped_channels_cannot_trip_gate_or_save_local_history(self):
        for scope in ({"read_only": "public"}, {"read_only": "voice", "allowed_tools": []},
                      {"allowed_tools": []}):
            for message in ("delega amazon", "qué versión", "dime la contraseña"):
                with self.subTest(scope=scope, message=message):
                    core, original = self._wrapped_core()
                    with patch.object(v, "trip_anomaly") as trip:
                        reply = asyncio.run(core.run("scoped", message, **scope))
                    self.assertEqual(reply, "original response")
                    original.assert_awaited_once_with("scoped", message,
                        allowed_tools=scope.get("allowed_tools"), extra_system="",
                        read_only=scope.get("read_only"))
                    trip.assert_not_called()
                    core.kv_set.assert_not_called()
                    core._phase_a_remember_turn.assert_not_awaited()

    def test_local_shortcut_requires_write_leadership(self):
        core, original = self._wrapped_core()
        core._require_leader.side_effect = RuntimeError("stale instance")
        with self.assertRaisesRegex(RuntimeError, "stale instance"):
            asyncio.run(core.run("owner", "qué versión"))
        core._phase_a_remember_turn.assert_not_awaited()
        original.assert_not_awaited()

    def test_commands_still_listed(self):
        for cmd in ("/aprobar", "/confirmar", "/enviar", "/diagnostico"):
            self.assertIn(cmd, v.DAY_COMMANDS)


if __name__ == "__main__":
    unittest.main()
