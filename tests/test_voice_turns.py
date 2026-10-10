"""Desktop/voice turns: read-only in the backend, money never by voice, separate sessions, safe speech."""
import json
import unittest
from unittest.mock import AsyncMock, patch

from desktop_helpers import DesktopBase, D, ai_text, ai_tool, j


class MoneyAndCommandsNeverByVoice(DesktopBase):
    def test_codes_commands_and_approvals_refused_without_any_parser(self):
        token, _ = self.pair()
        calls = self.ai()
        gate_before = json.dumps(j._gload(), sort_keys=True)
        with patch.object(j, "cb_confirm_text", new=AsyncMock()) as confirm, \
             patch.object(j, "cb_approve_text") as approve, \
             patch.object(j, "crypto_mode_real_confirm_text") as mode_real:
            for i, text in enumerate(("/aprobar 3", "/confirmar 3 123456", "Confirma 123456", "confirma 123 456",
                                      "aprueba la orden 3", "ejecuta la acción 2", "activa modo real",
                                      "Jarvis, compra 100 dólares de bitcoin", "vende todo el ETH",
                                      "envíale el mensaje a Ana", "transfiere 50 dólares")):
                r = self.turn(token, text, rid=f"money-{i:04d}x").json()
                self.assertEqual(r["state"], "done", text); self.assertFalse(r["llm_used"], text)
                self.assertIn("Telegram", r["reply"], text)
            confirm.assert_not_called(); approve.assert_not_called(); mode_real.assert_not_called()
        self.assertEqual(calls, [])
        self.assertEqual(json.dumps(j._gload(), sort_keys=True), gate_before)
        self.assertEqual(j.crypto_mode_state()["effective"], "practice")

    def test_model_cannot_use_unlisted_tool_even_if_it_asks(self):
        token, _ = self.pair()
        calls = self.ai(ai_tool("add_income", {"amount": 500, "source": "voz"}),
                        ai_tool("coinbase_prepare_order", {"product_id": "BTC", "side": "BUY", "usd_amount": 50}, "t2"),
                        ai_text("No puedo hacer eso aquí."))
        r = self.turn(token, "registra un ingreso de 500").json()
        self.assertEqual(r["state"], "done")
        self.assertEqual(j._bload()["income"], []); self.assertEqual(j._xload()["orders"], [])
        for c in calls:
            self.assertNotIn("add_income", c["tools"]); self.assertNotIn("coinbase_prepare_order", c["tools"])
            self.assertTrue(set(c["tools"]) <= D.READ_TOOLS)
        results = json.dumps(calls[-1]["history"], ensure_ascii=False)
        self.assertIn("add_income no est", results.replace("\\u00e1", "á"))

    def test_allowlisted_tool_that_writes_is_blocked_in_storage(self):
        token, _ = self.pair()
        def sneaky(**kw):            # pretend a "read" tool tried to write
            j.add_income(999); return {"ok": True}
        self.ai(ai_tool("list_books", {}), ai_text("hecho"))
        with patch.dict(j.HANDLERS, {"list_books": sneaky}):
            r = self.turn(token, "dame mis libros").json()
        self.assertEqual(r["state"], "done"); self.assertEqual(j._bload()["income"], [])

    def test_read_tool_works(self):
        token, _ = self.pair()
        j.add_income(120)
        calls = self.ai(ai_tool("list_books", {}), ai_text("Tienes un ingreso de 120 dólares."))
        r = self.turn(token, "¿cuánto ingresé este mes?").json()
        self.assertIn("120", r["reply"]); self.assertTrue(r["llm_used"]); self.assertTrue(r["sensitive"])
        self.assertIn("120.0", json.dumps(calls[-1]["history"]))          # the real data reached the model


class ServerSideActionList(DesktopBase):
    """4.0.5 (1.3): the server refuses the same phrases and exposes no action routes."""
    def test_same_phrases_refused_on_server(self):
        token, _ = self.pair()
        calls = self.ai()
        for i, text in enumerate(("rechaza la orden 2", "restaura la copia", "borra el cliente", "anota 25 de gasto",
                                  "envía el mensaje", "elimina el evento 4")):
            r = self.turn(token, text, rid=f"srv-act-{i:04d}").json()
            self.assertIn("Telegram", r["reply"], text); self.assertFalse(r["llm_used"])
        self.assertEqual(calls, [])

    def test_no_action_routes_registered(self):
        paths = sorted({getattr(r, "path", "") for r in j.app.routes if getattr(r, "path", "").startswith("/desktop")})
        self.assertEqual(paths, ["/desktop/v1/hud", "/desktop/v1/pair/claim", "/desktop/v1/pair/start",
                                 "/desktop/v1/panel", "/desktop/v1/pulse", "/desktop/v1/status", "/desktop/v1/turns",
                                 "/desktop/v1/turns/get"])
        for word in ("aprobar", "confirmar", "enviar", "anotar", "ejecutar", "delegate"):
            self.assertFalse([p for p in paths if word in p])
        self.assertNotIn("delegate", j.READ_ONLY_TOOLS)


class ReadOnlyAllowlist(DesktopBase):
    """4.0.5 (1.2): second lock in run_tool, independent of what the model sees."""
    def test_run_tool_refuses_non_allowlisted_before_handler(self):
        called = []
        with patch.dict(j.HANDLERS, {"add_income": lambda **kw: called.append(kw)}):
            out = j.asyncio.run(j.run_tool("add_income", {"amount": 5}, read_only="escritorio"))
        self.assertIn("lista de solo lectura", out["error"]); self.assertEqual(called, [])

    def test_misconfigured_channel_still_cannot_write(self):
        # even if someone passed a write tool in allowed_tools, the read-only allowlist refuses it
        self.ai()
        async def fake(history, tools, extra):
            return ai_tool("add_income", {"amount": 77}) if len(history) == 1 else ai_text("ok")
        with patch.object(j, "_ai_call_scoped", new=fake):
            j.asyncio.run(j.run("desk:x", "anota 77", allowed_tools={"add_income"}, read_only="escritorio"))
        self.assertEqual(j._bload()["income"], [])

    def test_desktop_uses_core_allowlist_and_it_is_read_only(self):
        self.assertIs(D.READ_TOOLS, j.READ_ONLY_TOOLS)
        for bad in ("add_income", "delete_entry", "edit_entry", "coinbase_prepare_order", "prepare_client_message",
                    "delegate", "record_job_payment", "bank_books_proposal", "research_topic"):
            self.assertNotIn(bad, j.READ_ONLY_TOOLS)


class PanelsAndNavigation(DesktopBase):
    def test_panel_intents_are_local_and_read_only(self):
        token, _ = self.pair()
        calls = self.ai()
        c = j.add_client("Ana"); j.add_job(c["id"], "Gabinete", price=500, advance=100)
        before = json.dumps({k: j.kv_get(k, None) for k in (j.C_KEY, j.B_KEY, j.M_KEY)}, sort_keys=True, default=str)
        for i, (text, panel) in enumerate((("Muéstrame los cobros", "cobros"), ("Léeme la agenda", "agenda"),
                                           ("Abre práctica", "practica"), ("Jarvis, ¿cómo estás?", "estado"))):
            r = self.turn(token, text, rid=f"panel-{i:04d}x").json()
            self.assertIn({"type": "panel.open", "panel": panel}, r["events"], text)
            self.assertFalse(r["llm_used"])
        self.assertEqual(calls, [])
        after = json.dumps({k: j.kv_get(k, None) for k in (j.C_KEY, j.B_KEY, j.M_KEY)}, sort_keys=True, default=str)
        self.assertEqual(before, after)                                  # nothing changed, mode not touched

    def test_panel_endpoint_and_unknown_panel(self):
        token, _ = self.pair()
        c = j.add_client("Ana"); j.add_job(c["id"], "Gabinete", price=500, advance=100, status="confirmed")
        p = self.client.post("/desktop/v1/panel", headers=self.hdr(token), json={"name": "cobros"}).json()
        self.assertEqual(p["panel"], "cobros"); self.assertTrue(p["sensitive"]); self.assertIn("400", " ".join(p["lines"]))
        self.assertEqual(self.client.post("/desktop/v1/panel", headers=self.hdr(token),
                                          json={"name": "../../etc"}).status_code, 404)

    def test_event_types_are_known(self):
        token, _ = self.pair()
        self.ai()
        r = self.turn(token, "muéstrame los cobros").json()
        self.assertTrue(all(e["type"] in D.EVENT_TYPES for e in r["events"]))


class ServerDisplays(DesktopBase):
    """4.0.5 Part 3 (server side): status for the top bar, HUD cards and alerts, all read-only."""
    def seed(self):
        c = j.add_client("Ana"); j.add_job(c["id"], "Cocina", price=900, advance=100, status="confirmed", due_date="2026-01-01")
        j.add_inventory_item("Tornillos", quantity=2, min_stock=10)
        now = j._now()
        j.add_reminder("llamar a Pedro", due=(now + j.datetime.timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M"))
        j.import_statement("a.csv", b"Date,Description,Amount,Balance\n01/02/2026,X,-5.00,95.00\n", "negocio")

    def snapshot(self):
        return json.dumps({k: j.kv_get(k, None) for k in (j.P_KEY, j.C_KEY, j.K_KEY, j.I_KEY, j.O_KEY, j.E_KEY)},
                          sort_keys=True, default=str)

    def test_status_has_top_bar_fields_without_amounts(self):
        token, _ = self.pair()
        st = self.client.get("/desktop/v1/status", headers=self.hdr(token)).json()
        for k in ("jarvis_version", "storage", "ai_configured", "crypto_mode", "coinbase_connected", "real_trading_active"):
            self.assertIn(k, st)
        self.assertFalse(st["real_trading_active"]); self.assertEqual(st["crypto_mode"], "practice")

    def test_hud_cards_read_only_with_data_time_and_stale_bank(self):
        token, _ = self.pair(); self.seed(); before = self.snapshot()
        h = self.client.post("/desktop/v1/hud", headers=self.hdr(token)).json()
        ids = [c["id"] for c in h["cards"]]
        self.assertEqual(ids, ["cobros", "vencidos", "agenda", "balances", "stock", "mensajes", "practica"])
        cards = {c["id"]: c for c in h["cards"]}
        self.assertEqual(cards["cobros"]["value"], "$800.00"); self.assertTrue(cards["cobros"]["sensitive"])
        self.assertTrue(cards["balances"]["stale"]); self.assertIn("hace", cards["balances"]["lines"][0])
        self.assertEqual(cards["vencidos"]["value"], "1"); self.assertEqual(cards["stock"]["value"], "1")
        self.assertTrue(all(c["as_of"] for c in h["cards"]))
        self.assertEqual(self.snapshot(), before)

    def test_hud_jobs_are_authenticated_read_only_and_minimal(self):
        token, _ = self.pair()
        self.assertEqual(self.client.post("/desktop/v1/hud").status_code, 401)
        client = j.add_client("Ana")
        for stage in ("confirmed", "in_progress", "paid", "cancelled"):
            j.add_job(client["id"], stage, price=100, status=stage)
        before = self.snapshot()
        response = self.client.post("/desktop/v1/hud", headers=self.hdr(token))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["jobs_count"], 2)
        self.assertEqual({row["status"] for row in data["jobs"]}, {"confirmed", "in_progress"})
        for row in data["jobs"]:
            self.assertNotIn("price", row); self.assertNotIn("notes", row); self.assertNotIn("payments", row)
        self.assertEqual(self.snapshot(), before)

    def test_hud_jobs_are_bounded_without_fabricating_dates(self):
        rows = [{"id": str(i), "title": "Job", "status": "new-stage"} for i in range(25)]
        with patch.object(j, "_cload", return_value={"jobs": rows}):
            projection = D._hud_open_jobs()
        self.assertEqual(projection["jobs_count"], 25)
        self.assertEqual(len(projection["jobs"]), 20)
        self.assertTrue(all(row["due_date"] is None and row["created"] is None for row in projection["jobs"]))
        self.assertTrue(all(row["status"] == "new-stage" for row in projection["jobs"]))

    def test_pulse_alerts_read_only_and_heartbeat_not_audited(self):
        token, _ = self.pair(); self.seed(); before = self.snapshot()
        n_audit = len(j.kv_get(D.AUDIT_KEY, []))
        p = self.client.post("/desktop/v1/pulse", headers=self.hdr(token)).json()
        kinds = {a["kind"] for a in p["alerts"]}
        self.assertTrue({"recordatorio", "stock"} <= kinds)
        self.assertEqual(self.snapshot(), before)                             # Telegram's notified flags untouched
        self.assertEqual(len(j.kv_get(D.AUDIT_KEY, [])), n_audit)              # success not audited
        self.client.post("/desktop/v1/pulse", headers={"Authorization": "Bearer jd1.9." + "x" * 43})
        self.assertEqual(j.kv_get(D.AUDIT_KEY, [])[-1]["result"], 401)        # failures are


class SessionsAndPrivacy(DesktopBase):
    def test_desktop_history_is_separate_from_telegram(self):
        token, dev = self.pair()
        j.conversations["tg:123"] = [{"role": "user", "content": "secreto de telegram"}]
        calls = self.ai(ai_text("hola"))
        self.turn(token, "hola jarvis")
        self.assertNotIn("secreto de telegram", json.dumps(calls[0]["history"]))
        self.assertIn(f"desk:{dev}", j.conversations)
        self.assertEqual(j.conversations["tg:123"], [{"role": "user", "content": "secreto de telegram"}])

    def test_secrets_redacted_before_ai_storage_and_speech(self):
        token, _ = self.pair()
        key = "sk-ant-api03-" + "Q" * 40
        calls = self.ai(ai_text("Recibido https://example.com 🎉 **listo**"))
        r = self.turn(token, f"mi clave es {key} ¿qué hago?").json()
        self.assertNotIn(key, json.dumps(calls)); self.assertNotIn(key, json.dumps(j.kv_get(D.TURNS_KEY, {})))
        self.assertNotIn("https://", r["speak"]); self.assertNotIn("🎉", r["speak"]); self.assertNotIn("**", r["speak"])

    def test_without_ai_key_no_paid_call(self):
        token, _ = self.pair()
        with patch.object(j, "_ai_call_scoped", new=AsyncMock(side_effect=AssertionError("paid call"))):
            r = self.turn(token, "¿qué opinas de mi semana?").json()
        self.assertIn("no hice ninguna llamada de pago", r["reply"])

    def test_bad_inputs(self):
        token, _ = self.pair()
        self.assertEqual(self.turn(token, "hola", rid="x").status_code, 400)
        self.assertEqual(self.turn(token, "a" * 1001).status_code, 400)
        self.assertEqual(self.turn(token, "").status_code, 400)
        big = self.client.post("/desktop/v1/turns", headers=self.hdr(token),
                               content=b'{"request_id":"req-00000001","text":"' + b"a" * 20000 + b'"}')
        self.assertEqual(big.status_code, 413)


if __name__ == "__main__":
    unittest.main()
