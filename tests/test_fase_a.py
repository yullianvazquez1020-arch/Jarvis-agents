"""Jarvis 4.1.0 Fase A, revisada: tránsito HTTPS, sellado, atajos, historial y techo del perfil.
No network, no real money. Each class says which correction it covers."""
import asyncio
import base64
import json
import math
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_jarvis as base
j = base.j
import jarvis_seal
import jarvis_transit


def new_key():
    return base64.b64encode(os.urandom(32)).decode()


class Base(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True); j._seen_updates.clear(); j._rate_hits.clear(); j.conversations.clear()
        self.env = patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": new_key()}); self.env.start()
        self.addCleanup(self.env.stop)


class Transit(Base):
    """A1: the health check and the test client are not blocked; public HTTP is."""
    def test_rules(self):
        d = jarvis_transit.decide
        self.assertEqual(d("GET", "/health", "jarvis-agents.onrender.com", ""), "")             # Render health check
        self.assertEqual(d("POST", "/telegram", "jarvis-agents.onrender.com", "https"), "")
        self.assertEqual(d("POST", "/telegram", "jarvis-agents.onrender.com", "http"), "HTTPS obligatorio")
        self.assertEqual(d("POST", "/chat", "x.onrender.com", "http, https"), "HTTPS obligatorio")
        self.assertEqual(d("GET", "/", "127.0.0.1:8000", "http"), "")                          # local
        h = "jarvis-agents.onrender.com"
        self.assertEqual(d("POST", "/telegram", "evil.example", "https", public_host=h), "host no permitido")
        self.assertEqual(d("GET", "/health", "mi-dominio.com", "", public_host=h), "")         # health exempt
        self.assertEqual(d("HEAD", "/", "otro", "", public_host=h), "")
        self.assertEqual(d("POST", "/health", "otro", "https", public_host=h), "host no permitido")
        self.assertEqual(d("POST", "/telegram", h + ":443", "https", public_host=h), "")

    def test_installed_as_pure_asgi_and_headers(self):
        from fastapi.testclient import TestClient
        c = TestClient(j.app)
        self.assertEqual(c.get("/health").status_code, 200)                       # what Render's check sees
        r = c.get("/health", headers={"x-forwarded-proto": "https", "host": "jarvis-agents.onrender.com"})
        self.assertEqual(r.headers.get("strict-transport-security"), "max-age=31536000; includeSubDomains")
        r = c.post("/telegram", json={}, headers={"x-forwarded-proto": "http", "host": "jarvis-agents.onrender.com"})
        self.assertEqual((r.status_code, r.json()), (400, {"error": "HTTPS obligatorio"}))
        names = [getattr(m, "cls", None) for m in j.app.user_middleware]
        self.assertIn(jarvis_transit.TransitMiddleware, names)

    def test_webhook_background_work_still_runs(self):
        from fastapi.testclient import TestClient
        j.TG_SECRET = "sec"; sent = []
        async def fake(chat, text): sent.append(text)
        with patch.object(j, "_tg_send", new=fake):
            r = TestClient(j.app).post("/telegram", headers={"x-telegram-bot-api-secret-token": "sec",
                                       "x-forwarded-proto": "https"},
                                       json={"update_id": 5001, "message": {"chat": {"id": 123, "type": "private"},
                                             "from": {"id": 123}, "text": "/ayuda"}})
        self.assertEqual(r.status_code, 200); self.assertTrue(any("Atajos" in s for s in sent))


class Sealing(Base):
    """A2: sealing never blocks other writes; no key -> clear (owner's decision); sealed data never overwritten."""
    def stored(self, key):
        return j._kv_raw(key, None)

    def test_with_key_history_is_sealed_and_readable(self):
        j.phase_a_remember("tg:1", "user", "hola jarvis")
        raw = self.stored("jarvis:history")
        self.assertTrue(jarvis_seal.is_sealed(raw)); self.assertNotIn("hola", raw)
        self.assertEqual(j.kv_get("jarvis:history", [])[-1]["text"], "hola jarvis")
        j.add_income(10)                                                     # other keys stay plain
        self.assertIsInstance(self.stored(j.B_KEY), dict)

    def test_without_key_history_saved_in_clear(self):
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": ""}):
            j.phase_a_remember("tg:1", "user", "hola")
            self.assertEqual(self.stored("jarvis:history")[-1]["text"], "hola")
            self.assertIn("en claro", j._seal_status())

    def test_missing_module_never_blocks_other_writes(self):
        with patch.dict(sys.modules, {"jarvis_seal": None}):
            j.add_income(10)
            with j._data_lock:
                g = j._gload(); j.gate_add_spent(g, 5); j._gsave(g)          # money gate still writes
            self.assertEqual(j.gate_spent_today(j._gload()), 5)
            self.assertIn("módulo ausente", j._seal_status())

    def test_sealed_data_never_overwritten_in_clear(self):
        j.phase_a_remember("tg:1", "user", "secreto")
        sealed = self.stored("jarvis:history")
        for ctx in (patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": ""}), patch.dict(sys.modules, {"jarvis_seal": None})):
            with ctx:
                self.assertEqual(j.kv_get("jarvis:history", []), [])           # unreadable -> default, not the blob
                j.phase_a_remember("tg:1", "user", "nuevo")                    # fails quietly
                with self.assertRaises(RuntimeError):
                    j.kv_set("jarvis:history", [])
            self.assertEqual(self.stored("jarvis:history"), sealed)

    def test_invalid_key_refuses_instead_of_clear(self):
        for bad in ("no-es-base64!!", base64.b64encode(b"corta").decode()):
            with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": bad}):
                with self.assertRaises(jarvis_seal.SealError):
                    j.kv_set("jarvis:profile", {"techo_usd": 50})
                self.assertIn("inválida", j._seal_status())
                j.add_income(1)                                               # unrelated writes fine
        self.assertIsNone(self.stored("jarvis:profile"))

    def test_wrong_key_or_tampered_value_reads_default(self):
        j.kv_set("jarvis:profile", {"techo_usd": 50})
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": new_key()}):
            self.assertEqual(j.kv_get("jarvis:profile", {"d": 1}), {"d": 1})
        raw = self.stored("jarvis:profile")
        j.kv_set.__globals__["_atomic_file"](j.DATA_DIR / "jarvis_profile.json", json.dumps(raw[:-4] + "AAAA"))
        self.assertEqual(j.kv_get("jarvis:profile", {}), {})

    def test_kv_set_many_also_seals(self):
        j.kv_set_many({"jarvis:profile": {"techo_usd": 60}, j.B_KEY: {"income": [], "expenses": []}})
        self.assertTrue(jarvis_seal.is_sealed(self.stored("jarvis:profile")))
        self.assertEqual(j.kv_get("jarvis:profile", {}), {"techo_usd": 60})

    def test_gate_and_queue_keys_are_never_sealed(self):
        for k in (j.G_KEY, j.X_KEY, j.TG_INBOX_KEY, j.LEADER_KEY, j.M_KEY):
            self.assertNotIn(k, jarvis_seal.SEALED_KEYS)


class Shortcuts(Base):
    """A3: local shortcuts answer only when the WHOLE message is that question."""
    def test_hijack_fixed(self):
        for t in ("anota 50 de cash para gasolina", "cuál fue mi flujo de clientes este mes",
                  "llamar a Ana mañana: recuérdamelo", "recuérdame llamar a Pedro", "perfil de cliente de Ana"):
            self.assertIsNone(j.phase_a_local(t), t)
        for t in ("perfil", "/perfil", "Jarvis, ¿cuál es mi perfil?", "cash flow", "¿Cómo va mi flujo de caja?",
                  "llamar a Ana", "/llamar Pedro"):
            self.assertTrue(j.phase_a_local(t), t)

    def test_expense_with_cash_reaches_the_ai_and_is_recorded(self):
        from unittest.mock import MagicMock
        blk = MagicMock(type="tool_use", input={"amount": 50, "category": "fuel"}, id="t1"); blk.name = "add_expense"
        seq = [MagicMock(content=[blk], stop_reason="tool_use"),
               MagicMock(content=[MagicMock(type="text", text="Anotado.")], stop_reason="end_turn")]
        with patch.object(j, "AI_READY", True), patch.object(j, "_ai_call", new=AsyncMock(side_effect=seq)):
            out = asyncio.run(j.run("tg:1", "anota 50 de cash para gasolina"))
        self.assertEqual(out, "Anotado."); self.assertEqual(j._bload()["expenses"][0]["amount"], 50)

    def test_shortcut_needs_no_ai_and_is_not_for_restricted_channels(self):
        with patch.object(j, "AI_READY", False):
            self.assertIn("Cash flow", asyncio.run(j.run("tg:1", "cash flow")))
        with patch.object(j, "AI_READY", False):
            out = asyncio.run(j.run("desk:1", "cash flow", allowed_tools={"upcoming"}, read_only="escritorio"))
        self.assertNotIn("Cash flow", out)


class HistoryOffLoop(Base):
    """A4: history writes run in a worker thread and a failing save never breaks the chat."""
    def test_saved_in_worker_thread(self):
        import threading
        seen = []
        real = j.phase_a_remember
        def spy(*a):
            seen.append(threading.current_thread() is threading.main_thread()); return real(*a)
        with patch.object(j, "phase_a_remember", new=spy), patch.object(j, "AI_READY", False):
            asyncio.run(j.run("tg:1", "perfil"))
        self.assertEqual(seen, [False, False])
        self.assertEqual([h["role"] for h in j.kv_get("jarvis:history", [])], ["user", "assistant"])

    def test_failing_save_does_not_break_chat(self):
        def boom(*a): raise RuntimeError("Upstash down")
        with patch.object(j, "phase_a_remember", new=boom), patch.object(j, "AI_READY", True), \
             patch.object(j, "_ai_call", new=AsyncMock(return_value=__import__("unittest.mock").mock.MagicMock(
                 content=[__import__("unittest.mock").mock.MagicMock(type="text", text="hola")], stop_reason="end_turn"))):
            self.assertEqual(asyncio.run(j.run("tg:1", "hola jarvis, ¿qué tal?")), "hola")

    def test_history_is_bounded_and_redacted(self):
        key = "sk-ant-api03-" + "Q" * 40
        for i in range(45):
            j.phase_a_remember("tg:1", "user", f"m{i} {key}")
        h = j.kv_get("jarvis:history", [])
        self.assertEqual(len(h), 40); self.assertNotIn(key, json.dumps(h))


class ProfileCeiling(Base):
    """A5: the profile ceiling can only lower the $100/$300 limits; bad values fail closed without exceptions."""
    def order(self, usd, oid=7, mode="practice"):
        with j._data_lock:
            x = j._xload()
            x["orders"].append({"id": oid, "status": "pending", "mode": mode, "epoch": j.crypto_mode_state()["epoch"],
                                "created": j._now().isoformat(), "usd_estimate": usd, "product": "BTC-USD", "side": "BUY",
                                "uuid": f"u{oid}", "config": {"market_market_ioc": {"quote_size": str(usd)}}})
            j._xsave(x)

    def approve(self, techo, usd=50):
        if techo is not None:
            j.kv_set("jarvis:profile", {"techo_usd": techo})
        self.order(usd)
        return j.cb_approve_text("7")

    def test_values(self):
        cases = [(None, 50, True), (40, 50, False), (60, 50, True), (0, 50, False), ("abc", 50, False),
                 (float("nan"), 50, False), (-5, 50, False), (True, 50, False), ("75", 50, True), (500, 99, True)]
        for techo, usd, ok in cases:
            with self.subTest(techo=techo):
                self.setUp()
                out = self.approve(techo, usd)
                self.assertEqual("/confirmar 7" in out, ok, out)

    def test_never_raises_the_hard_limits(self):
        self.assertEqual(j._profile_ceiling(), (100.0, ""))
        j.kv_set("jarvis:profile", {"techo_usd": 10_000})
        self.assertEqual(j._profile_ceiling()[0], 100.0)
        out = self.approve(10_000, usd=150)
        self.assertIn("No la apruebo", out)
        self.assertEqual((j.MONEY_MAX_ORDER, j.MONEY_MAX_DAY, j.HARD_MAX_ORDER_USD, j.HARD_MAX_DAY_USD),
                         (100.0, 300.0, 100.0, 300.0))

    def test_ceiling_lowered_between_aprobar_and_confirmar(self):
        msg = self.approve(None, usd=50)
        code = __import__("re").search(r"/confirmar 7 (\d{6})", msg).group(1)
        j.kv_set("jarvis:profile", {"techo_usd": 20})
        with patch.object(j, "_cb", new=AsyncMock()) as cb:
            out = asyncio.run(j.cb_confirm_text(f"7 {code}"))
        self.assertIn("techo del perfil", out); cb.assert_not_called()
        self.assertEqual(next(o for o in j._xload()["orders"] if o["id"] == 7)["status"], "pending")

    def test_unreadable_profile_falls_back_to_hard_limit(self):
        j.kv_set("jarvis:profile", {"techo_usd": 20})
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": new_key()}):      # another key: profile unreadable
            self.assertEqual(j._profile_ceiling(), (100.0, ""))


class GateUntouched(Base):
    """The gate rules the owner listed stay exactly as they were."""
    def test_confirm_not_queued_and_ai_has_no_money_tools(self):
        with self.assertRaises(ValueError):
            j._tg_enqueue(9100, {"chat": {"id": 123, "type": "private"}, "from": {"id": 123}, "text": "/confirmar 1 123456"})
        names = {t["name"] for t in j.TOOLS}
        for bad in ("aprobar", "confirm", "approve", "send_order", "execute"):
            self.assertFalse([n for n in names if bad in n.lower()], bad)

    def test_no_new_external_clients(self):
        import pathlib
        root = pathlib.Path(j.__file__).parent
        for f in ("main.py", "jarvis_phase_a.py", "jarvis_seal.py", "jarvis_transit.py"):
            text = (root / f).read_text(encoding="utf-8")
            self.assertNotIn("XAI_API_KEY", text); self.assertNotIn("api.x.ai", text)
        self.assertNotIn("twilio.com", (root / "jarvis_phase_a.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
