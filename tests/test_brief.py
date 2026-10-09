"""Jarvis 4.2.1 /brief comercial. Servicios simulados, sin red y sin Redis de producción.
Solo lectura: no envía, no publica, no aprueba ni crea ingresos. Los topes $100/$300 no cambian."""
import asyncio
import datetime as dt
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_jarvis as base
import jarvis_brief as brief

j = base.j
TODAY = dt.date(2026, 10, 8)          # jueves; la semana empieza el lunes 2026-10-05
SECTIONS = ("1) CAJA", "2) SOLICITUDES Y SEGUIMIENTOS VENCIDOS", "3) BORRADORES DE RESPUESTA",
            "4) BORRADOR DE RED — no publicado", "5) POR COBRAR")


def snapshot_storage():
    """Todo lo guardado en disco, para comprobar que una operación no escribe."""
    return {p.name: p.read_text() for p in sorted(Path(j.DATA_DIR).glob("*.json"))
            if not p.name.startswith("jarvis_tg_")}          # la cola durable de Telegram sí escribe


class BriefBase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": "", "BUSINESS_REQUESTS_ENABLED": "false"})
        env.start(); self.addCleanup(env.stop)
        j.DATA_DIR = Path(self.temp.name)
        j.USE_REDIS = False
        j._fence.update(mode="off", leader=True)
        j._seal_paused["on"] = False
        j._seen_updates.clear(); j._rate_hits.clear()
        for p in (patch.object(j, "_today", return_value=TODAY),
                  patch.object(j, "_now", return_value=dt.datetime(2026, 10, 8, 8, 0, tzinfo=j.TZ)),
                  patch.object(j, "BUSINESS_NAME", "ISLAFIX PRO LLC")):
            p.start(); self.addCleanup(p.stop)

    def bank(self, amount=500, date="2026-10-08", key="checking", type="CHECKING"):
        d = j._kload()
        d["accounts"][key] = {"balance": amount, "balance_date": date, "type": type, "name": "Banco"}
        j.kv_set(j.K_KEY, d)

    def client(self, name="Ana"):
        return j.add_client(name, phone="17875551234")

    def tg(self, text, uid, chat_type="private", user=123):
        return {"update_id": uid, "message": {"message_id": uid, "chat": {"id": 123, "type": chat_type},
                                              "from": {"id": user, "is_bot": False}, "text": text}}

    def post(self, text, uid, chat_type="private"):
        from fastapi.testclient import TestClient
        with patch.object(j, "TG_SECRET", "sec"), patch.object(j, "_tg_send", new=AsyncMock()) as send:
            r = TestClient(j.app).post("/telegram", headers={"x-telegram-bot-api-secret-token": "sec"},
                                       json=self.tg(text, uid, chat_type))
            self.assertEqual(r.status_code, 200)
        return [c.args[1] for c in send.await_args_list]


class OwnerBrief(BriefBase):
    def test_owner_private_gets_five_sections_and_marker_in_order(self):
        self.bank(500)
        c = self.client()
        job = j.add_job(c["id"], "Pintura terraza", price=300, status="confirmed", due_date="2026-10-01")
        j.add_job(c["id"], "Sellado techo", price=0, status="quote")
        before = snapshot_storage()
        replies = self.post("/brief", 7001)
        self.assertEqual(len(replies), 1)
        text = replies[0]
        positions = [text.index(s) for s in SECTIONS]
        self.assertEqual(positions, sorted(positions))
        self.assertGreater(text.index("Cobrado esta semana:"), positions[-1])
        self.assertIn(f"Trabajo #{job['id']}", text)
        self.assertIn("Saldo observado: $500.00 al 2026-10-08", text)
        self.assertEqual(snapshot_storage(), before)          # solo lectura

    def test_phrase_routes_to_same_function_only_when_whole_message(self):
        for uid, phrase in enumerate(("brief", "Brief de hoy", "Oye Jarvis, caja y cobros?"), start=7100):
            with self.subTest(phrase=phrase):
                replies = self.post(phrase, uid)
                self.assertIn("1) CAJA", replies[0])
        with patch.object(j, "_handle_tg", new=AsyncMock()) as ai:
            self.post("brief del cliente nuevo para mañana", 7200)
        ai.assert_awaited_once()                               # no secuestra pedidos normales

    def test_other_chat_cannot_run_command_or_phrase_and_nothing_is_written(self):
        self.bank(500)
        before = snapshot_storage()
        for uid, text in ((7301, "/brief"), (7302, "brief de hoy")):
            with self.subTest(text=text), patch.object(brief, "commercial_brief") as fn:
                replies = self.post(text, uid, chat_type="group")
                fn.assert_not_called()
                self.assertEqual(replies, ["Este comando requiere tu chat privado."])
        self.assertEqual(snapshot_storage(), before)

    def test_business_mismatch_stops(self):
        with patch.object(j, "BUSINESS_NAME", "Otra Empresa"):
            text = brief.commercial_brief()
        self.assertIn("no coincide con ISLAFIX PRO LLC", text)
        self.assertNotIn("1) CAJA", text)

    def test_brief_cannot_write_even_if_a_reader_tried(self):
        with patch.object(j._business_workflows, "cash_flow_report",
                          side_effect=lambda account="": j.kv_set("jarvis:probe", {"x": 1})):
            with self.assertRaises(j.ReadOnlyViolation):
                brief.commercial_brief()
        self.assertIsNone(j.kv_get("jarvis:probe", None))
        self.assertIsNone(j._WRITE_BLOCK.get())                # el bloqueo se libera


class Robustness(BriefBase):
    def test_damaged_section_does_not_hide_the_rest(self):
        self.bank(500)
        with patch.object(j._business_workflows, "cash_flow_report", side_effect=ValueError("dañado")):
            text = brief.commercial_brief()
        self.assertIn("1) CAJA\nSección no disponible (ValueError)", text)
        for s in SECTIONS[1:]:
            self.assertIn(s, text)
        self.assertIn("Cobrado esta semana:", text)
        self.assertNotIn("$500.00", text.split("2) SOLICITUDES")[0])     # no rellena la caja

    def test_truncated_lists_say_how_many_more(self):
        c = self.client()
        for n in range(brief.MAX_ITEMS + 3):
            j.add_job(c["id"], f"Trabajo {n}", price=100, status="delivered", due_date="2026-10-01")
        text = brief.commercial_brief()
        self.assertIn("… y 3 más (ver /cobros).", text)
        self.assertEqual(text.count("BORRADOR — no enviado"), brief.MAX_ITEMS)

    def test_credit_account_flagged(self):
        self.bank(-250, type="CREDITCARD")
        text = brief.commercial_brief()
        self.assertIn("cuenta de crédito: no es caja", text)
        self.assertIn("bloqueada; no estimo", text)

    def test_diagnostics_reports_status(self):
        with patch.object(j, "_tg_send", new=AsyncMock()):
            text = asyncio.run(j.diagnostics_text())
        self.assertIn("Brief 4.2.1: activo", text)
        self.assertIn("negocio ISLAFIX PRO LLC", text)


class Cash(BriefBase):
    def test_no_observed_balance_never_fabricates_a_number(self):
        text = brief.commercial_brief()
        self.assertIn("sin saldo observado", text)
        self.assertIn("Proyección a 7 días: bloqueada; no estimo", text)
        caja = text.split("2) SOLICITUDES")[0]
        self.assertNotIn("Saldo observado: $", caja)

    def test_stale_import_blocks_projection(self):
        self.bank(900, date="2026-09-20")
        c = self.client()
        j.add_job(c["id"], "Reparación", price=200, status="confirmed", due_date="2026-10-10")
        text = brief.commercial_brief()
        self.assertIn("SALDO VIEJO", text)
        self.assertIn("bloqueada; no estimo", text)
        self.assertNotIn("Proyección condicional", text)

    def test_future_items_separated_and_projection_conditional(self):
        self.bank(400)
        c = self.client()
        j.add_job(c["id"], "Reparación", price=150, status="confirmed", due_date="2026-10-12")
        j.add_bill("Luz", 11, 80)                                # vence el día 11 de cada mes
        text = brief.commercial_brief()
        self.assertIn("Futuro, no disponible todavía", text)
        self.assertIn("cobros por vencer trabajo #", text)
        self.assertIn("pagos por vencer cuenta #", text)
        self.assertIn("Proyección condicional a 7 días (2026-10-15): $400.00 + cobros futuros $150.00 − pagos futuros $80.00 = $470.00", text)

    def test_multiple_accounts_are_not_summed(self):
        self.bank(100, key="a"); self.bank(200, key="b")
        text = brief.commercial_brief()
        self.assertIn("no las sumo", text)
        self.assertNotIn("$300.00", text)


class FollowUps(BriefBase):
    def test_overdue_followup_gets_draft_and_nothing_is_sent(self):
        c = self.client("Luis")
        job = j.add_job(c["id"], "Impermeabilizar", price=250, status="delivered", due_date="2026-10-02")
        outbox_before = json.dumps(j._oload(), sort_keys=True)
        with patch.object(j, "send_message_text", new=AsyncMock()) as send_client, \
                patch.object(j, "_tg_send", new=AsyncMock()) as tg:
            text = brief.commercial_brief()
        send_client.assert_not_called()
        tg.assert_not_called()
        self.assertIn(f"[cobro #{job['id']}] BORRADOR — no enviado", text)
        self.assertIn("saldo registrado de $250.00", text)
        self.assertEqual(json.dumps(j._oload(), sort_keys=True), outbox_before)

    def test_job_without_due_date_is_not_overdue(self):
        c = self.client()
        job = j.add_job(c["id"], "Sin fecha", price=120, status="confirmed")
        text = brief.commercial_brief()
        self.assertNotIn("venció ,", text)
        self.assertNotIn(f"[cobro #{job['id']}]", text)
        report = j._business_workflows.cash_flow_report()
        self.assertNotIn(job["id"], report["overdue_jobs"])     # /caja tampoco lo marca vencido
        self.assertIn("fecha", text.split("5) POR COBRAR")[1])  # falta fecha del siguiente

    def test_requests_only_for_islafix_and_drafts_have_no_price(self):
        d = j._business_workflows.load()
        d["requests"] = [
            {"id": 1, "business": "ISLAFIX PRO LLC", "name": "Marta", "phone": "17875550000",
             "message": "techo", "created": "2026-10-07T10:00:00", "status": "pending"},
            {"id": 2, "business": "Otra Empresa", "name": "Pedro", "phone": "17875550001",
             "message": "x", "created": "2026-10-07T10:00:00", "status": "pending"}]
        j.kv_set(j._business_workflows.KEY, d)
        text = brief.commercial_brief()
        self.assertIn("Solicitud #1 de Marta", text)
        self.assertNotIn("Pedro", text)
        draft = text.split("[solicitud #1] BORRADOR — no enviado")[1].split("\n\n")[0]
        self.assertNotRegex(draft, r"\$\d")
        self.assertIn("Receptor de solicitudes públicas: apagado", text)

    def test_stale_quote_followup_uses_only_stored_price(self):
        c = self.client()
        with patch.object(j, "_now", return_value=dt.datetime(2026, 9, 20, 8, 0, tzinfo=j.TZ)):
            q = j.add_job(c["id"], "Cotización baño", price=0, status="quote")
        text = brief.commercial_brief()
        self.assertIn(f"[cotizacion #{q['id']}] BORRADOR — no enviado", text)
        draft = text.split(f"[cotizacion #{q['id']}] BORRADOR — no enviado")[1].split("\n\n")[0]
        self.assertNotRegex(draft, r"\$\d")

    def test_none_when_empty(self):
        text = brief.commercial_brief()
        self.assertIn("2) SOLICITUDES Y SEGUIMIENTOS VENCIDOS\nninguna", text)
        self.assertIn("Siguiente: no hay trabajo abierto.", text)


class Social(BriefBase):
    def test_social_draft_not_published_and_no_code(self):
        conn_key = getattr(j._connections, "KEY", None)
        before = j.kv_get(conn_key, None) if conn_key else None
        with patch.object(j._connections, "command", new=AsyncMock()) as conn:
            text = brief.commercial_brief()
        conn.assert_not_called()
        social = text.split("4) BORRADOR DE RED — no publicado")[1].split("5) POR COBRAR")[0]
        self.assertIn("BORRADOR — no publicado", social)
        self.assertNotRegex(social, r"\b\d{6}\b")                # sin código de confirmación
        self.assertNotRegex(social, r"\$\d|%|\+?1?787\d")        # sin precio, métrica ni teléfono
        if conn_key:
            self.assertEqual(j.kv_get(conn_key, None), before)


class Marker(BriefBase):
    def test_missing_goal_is_not_replaced_by_a_million(self):
        text = brief.commercial_brief()
        self.assertIn("Cobrado esta semana: $0.00 de sin meta", text)
        for bad in ("1,000,000", "1000000", "167,000", "167000"):
            self.assertNotIn(bad, text)

    def test_goal_shown_only_when_owner_saved_a_number(self):
        j.kv_set("jarvis:profile", {**j.DEFAULT_PROFILE, "meta_semanal_usd": 2500})
        self.assertIn("de $2,500.00", brief.marker_line())
        for bad in ("2500", "poderoso", True, -5, 0):
            with self.subTest(bad=bad):
                j.kv_set("jarvis:profile", {**j.DEFAULT_PROFILE, "meta_semanal_usd": bad})
                self.assertIn("sin meta", brief.marker_line())

    def test_future_undated_and_foreign_income_not_counted(self):
        j.kv_set(j.B_KEY, {"income": [
            {"id": 1, "amount": 100, "date": "2026-10-05"},          # lunes: cuenta
            {"id": 2, "amount": 50, "date": "2026-10-08"},           # hoy: cuenta
            {"id": 3, "amount": 900, "date": "2026-10-09"},          # futuro
            {"id": 4, "amount": 70, "date": "2026-10-04"},           # semana pasada
            {"id": 5, "amount": 40},                                 # sin fecha
            {"id": 6, "amount": 60, "date": "2026-10-06", "currency": "EUR"}], "expenses": []})
        self.assertEqual(brief.marker_line(), "Cobrado esta semana: $150.00 de sin meta")


class Voice(BriefBase):
    def test_voice_phrase_is_answered_read_only(self):
        import jarvis_chat_voice as cv
        self.assertTrue(cv.is_voice_query("caja y cobros"))
        self.assertTrue(cv.is_voice_query("qué hora es"))           # el comportamiento previo sigue
        before = snapshot_storage()
        with patch.object(j, "_tg_send", new=AsyncMock()) as send, patch.object(j, "run", new=AsyncMock()) as ai:
            reply = asyncio.run(j._handle_tg(j.TG_OWNER, "brief de hoy", read_only=True))
        ai.assert_not_awaited()
        self.assertIn("1) CAJA", reply)
        send.assert_awaited_once()
        self.assertEqual(snapshot_storage(), before)

    def test_other_text_still_goes_to_original_handler(self):
        with patch.object(j, "run", new=AsyncMock(return_value="ok")):
            with patch.object(j, "_tg_send", new=AsyncMock()):
                self.assertEqual(asyncio.run(j._handle_tg(j.TG_OWNER, "explícame un nicho")), "ok")


class Failures(BriefBase):
    def test_stale_instance_propagates_for_queue_retry(self):
        with patch.object(brief, "commercial_brief", side_effect=j.StaleInstance("x")):
            with patch.object(j, "_tg_send", new=AsyncMock()):
                with self.assertRaises(j.StaleInstance):
                    asyncio.run(j._extensions.command(j.TG_OWNER, "/brief", ""))

    def test_other_errors_reply_with_type_only(self):
        with patch.object(brief, "commercial_brief", side_effect=RuntimeError("token=abc secreto")):
            with patch.object(j, "_tg_send", new=AsyncMock()) as send:
                asyncio.run(j._extensions.command(j.TG_OWNER, "/brief", ""))
        msg = send.await_args.args[1]
        self.assertIn("RuntimeError", msg)
        self.assertNotIn("secreto", msg)


class Guards(BriefBase):
    def test_limits_unchanged(self):
        self.assertEqual(j.HARD_MAX_ORDER_USD, 100.0)
        self.assertEqual(j.HARD_MAX_DAY_USD, 300.0)
        self.assertLessEqual(j.MONEY_MAX_ORDER, 100)
        self.assertLessEqual(j.MONEY_MAX_DAY, 300)

    def test_confirmar_still_outside_queue(self):
        from fastapi.testclient import TestClient
        with patch.object(j, "TG_SECRET", "sec"), patch.object(j, "_tg_cb_cmd", new=AsyncMock()) as cb, \
                patch.object(j, "_tg_enqueue", side_effect=AssertionError("code queued")):
            r = TestClient(j.app).post("/telegram", headers={"x-telegram-bot-api-secret-token": "sec"},
                                       json=self.tg("/confirmar 1 123456", 7900))
        self.assertEqual(r.status_code, 200)
        cb.assert_awaited_once()

    def test_brief_registered_as_private_command_and_no_money_tool(self):
        self.assertIn("/brief", j._extensions.COMMANDS)
        names = {t["name"] for t in j.TOOLS} | set(j.HANDLERS)
        self.assertFalse(names & {"brief", "commercial_brief", "weekly_goal"})   # sin herramienta nueva para la IA
        self.assertIn("/brief", j.HELP_TEXT)


if __name__ == "__main__":
    unittest.main()
