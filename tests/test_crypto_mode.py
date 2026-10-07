"""Jarvis 4.0.3: practice/real crypto mode chosen from Telegram.

No real money, no network: every Coinbase call is a mock and the network client is replaced by one that fails
the test if anything tries to connect. Real-mode tests patch the module's variables in memory only.
"""
import asyncio
import datetime
import json
import re
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_jarvis as base
j = base.j

CODE = re.compile(r"\b(\d{6})\b")


class NoNetwork:
    def __init__(self, *a, **k):
        raise AssertionError("a test tried to open a network connection")


class ModeBase(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True); j._seen_updates.clear(); j._rate_hits.clear()
        j._mode_mem["block_real"] = False
        self.stack = ExitStack()
        self.stack.enter_context(patch.object(j.httpx, "AsyncClient", NoNetwork))
        self.price = 100.0
        async def public(path, params=None):
            if path.endswith("/ticker"):
                return {"price": str(self.price), "time": j._now().isoformat()}
            raise AssertionError("unexpected public call " + path)
        self.stack.enter_context(patch.object(j, "_cb_public", new=public))
        self.calls = []
        async def cb(method, path, params=None, body=None):
            self.calls.append((method, path, body))
            if path.endswith("/preview"):
                return {"order_total": str((body or {}).get("order_configuration", {}).get("market_market_ioc", {})
                                           .get("quote_size", "20")), "commission_total": "0.2"}
            if path == j.CB_ORDER_PATH:
                return {"success": True, "success_response": {"order_id": "mock-order"}}
            return {"price": "100"}
        self.cb = cb
        self.addCleanup(self.stack.close)

    # --- helpers -------------------------------------------------------------
    def allow_real(self):
        """Variables that ALLOW real mode (in memory only). They must not select it."""
        return patch.multiple(j, CRYPTO_PRACTICE_ONLY=False, CB_KEY_NAME="organizations/x/apiKeys/y",
                              CB_SECRET="-----BEGIN EC PRIVATE KEY-----test", CB_TRADING_ENV=True,
                              CB_ON=True, CB_TRADING=True)

    def mock_cb(self):
        return patch.object(j, "_cb", side_effect=self.cb)

    def go_real(self):
        msg = j.crypto_mode_real_request_text(); code = CODE.search(msg).group(1)
        out = asyncio.run(j.cb_confirm_text(f"modo {code}"))
        self.assertIn("Modo REAL activo", out)
        return out

    def prep(self, side="BUY", usd=20, qty=None, product="BTC"):
        return asyncio.run(j.coinbase_prepare_order(product, side, usd_amount=usd if side == "BUY" else None,
                                                    crypto_amount=qty))

    def approve_confirm(self, oid):
        msg = j.cb_approve_text(str(oid)); m = CODE.search(msg)
        self.assertIsNotNone(m, msg)
        return msg, asyncio.run(j.cb_confirm_text(f"{oid} {m.group(1)}"))

    def order(self, oid):
        return next(o for o in j._xload()["orders"] if o["id"] == oid)

    def real_posts(self):
        return [c for c in self.calls if c[0] == "POST" and c[1] == j.CB_ORDER_PATH]


class Defaults(ModeBase):
    def test_practice_is_the_default(self):
        ms = j.crypto_mode_state()
        self.assertEqual((ms["selected"], ms["effective"]), ("practice", "practice"))
        self.assertIn("PRÁCTICA", j.crypto_mode_text())

    def test_practice_only_variable_blocks_real_request(self):
        self.assertTrue(j.CRYPTO_PRACTICE_ONLY)
        out = j.crypto_mode_real_request_text()
        self.assertIn("CRYPTO_PRACTICE_ONLY", out); self.assertIsNone(CODE.search(out))
        self.assertNotIn(j.MODE_REAL_REF, j._gload()["codes"])

    def test_missing_credentials_block_real(self):
        with self.allow_real(), patch.multiple(j, CB_KEY_NAME="", CB_SECRET=""):
            out = j.crypto_mode_real_request_text()
        self.assertIn("COINBASE_API_KEY_NAME", out); self.assertIsNone(CODE.search(out))

    def test_trading_flag_off_blocks_real(self):
        with self.allow_real(), patch.object(j, "CB_TRADING_ENV", False):
            out = j.crypto_mode_real_request_text()
        self.assertIn("COINBASE_TRADING_ENABLED", out); self.assertIsNone(CODE.search(out))

    def test_enabling_variables_does_not_select_real(self):
        with self.allow_real():
            ms = j.crypto_mode_state()
            self.assertEqual(ms["effective"], "practice"); self.assertEqual(j.real_blockers(), [])
            self.assertIn("disponible: ✅", j.crypto_mode_text())
            o = self.prep()
        self.assertIn("PRÁCTICA", o["mode"]); self.assertFalse(o["real_orders_possible"])

    def test_practice_only_overrides_stored_real(self):
        j.kv_set(j.M_KEY, {"mode": "real", "epoch": 3, "since": None, "by": "x", "history": []})
        with self.allow_real(), patch.object(j, "CRYPTO_PRACTICE_ONLY", True):
            ms = j.crypto_mode_state()
        self.assertEqual((ms["selected"], ms["effective"]), ("real", "practice"))

    def test_boot_turns_real_off_when_variables_no_longer_allow_it(self):
        with self.allow_real():
            self.go_real()
        note = j.crypto_mode_boot_check()                    # restart with default (blocking) variables
        self.assertIn("desactivado", note)
        with self.allow_real():                              # variables enabled again later
            self.assertEqual(j.crypto_mode_state()["effective"], "practice")

    def test_lifespan_boot_does_not_select_real(self):
        from fastapi.testclient import TestClient
        with self.allow_real(), TestClient(j.app) as c:
            self.assertEqual(c.get("/").status_code, 200)
            self.assertEqual(j.crypto_mode_state()["effective"], "practice")


class Authorization(ModeBase):
    def tg(self, text, uid, chat_type="private", user=123):
        return {"update_id": uid, "message": {"chat": {"id": 123, "type": chat_type}, "from": {"id": user}, "text": text}}

    def test_only_owner_private_chat_can_change_mode(self):
        from fastapi.testclient import TestClient
        j.TG_SECRET = "sec"; c = TestClient(j.app); h = {"x-telegram-bot-api-secret-token": "sec"}
        with self.allow_real(), patch.object(j, "_tg_send", new=AsyncMock()) as send:
            c.post("/telegram", headers=h, json=self.tg("/cripto modo real", 501, user=999))   # stranger
            send.assert_not_called()
            c.post("/telegram", headers=h, json=self.tg("/cripto modo real", 502, chat_type="group"))
            self.assertIn("chat privado", send.await_args.args[1])
            self.assertNotIn(j.MODE_REAL_REF, j._gload()["codes"])
            c.post("/telegram", headers=h, json=self.tg("/cripto modo real", 503))           # owner, private
            code = CODE.search(send.await_args.args[1]).group(1)
            c.post("/telegram", headers=h, json=self.tg(f"/confirmar modo {code}", 504, chat_type="group"))
            self.assertEqual(j.crypto_mode_state()["selected"], "practice")              # group confirm ignored
            c.post("/telegram", headers=h, json=self.tg(f"/confirmar modo {code}", 505))
            self.assertEqual(j.crypto_mode_state()["effective"], "real")
        self.assertTrue(any(a["action"] == "modo" and a["result"] == "rechazado" for a in j._gload()["audit"]))

    def test_confirmation_code_never_enters_the_queue(self):
        with self.assertRaises(ValueError):
            j._tg_enqueue(600, {"chat": {"id": 123, "type": "private"}, "from": {"id": 123},
                                "text": "/confirmar modo 123456"})

    def test_ai_has_no_tool_to_change_mode_approve_or_send(self):
        names = {t["name"] for t in j.TOOLS} | set(j.HANDLERS) | set(j.ASYNC_TOOLS)
        for bad in ("mode", "modo", "approve", "aprobar", "confirm", "send_order", "execute_order"):
            self.assertFalse([n for n in names if bad in n.lower()], bad)
        with self.allow_real(), self.mock_cb():
            asyncio.run(j.run_tool("coinbase_prepare_order", {"product_id": "BTC", "side": "BUY", "usd_amount": 10}))
        self.assertEqual(j.crypto_mode_state()["effective"], "practice"); self.assertEqual(self.real_posts(), [])


class Switching(ModeBase):
    def test_wrong_expired_and_reused_codes(self):
        with self.allow_real():
            code = CODE.search(j.crypto_mode_real_request_text()).group(1)
            wrong = "000000" if code != "000000" else "111111"
            self.assertIn("incorrecto", asyncio.run(j.cb_confirm_text(f"modo {wrong}")))
            self.assertEqual(j.crypto_mode_state()["effective"], "practice")
            with j._data_lock:                                  # make the code expire
                g = j._gload(); g["codes"][j.MODE_REAL_REF]["until"] = "2000-01-01T00:00:00-04:00"; j._gsave(g)
            self.assertIn("venció", asyncio.run(j.cb_confirm_text(f"modo {code}")))
            self.assertEqual(j.crypto_mode_state()["effective"], "practice")
            self.go_real()
            j.crypto_mode_to_practice()
            code2 = CODE.search(j.crypto_mode_real_request_text()).group(1)
            asyncio.run(j.cb_confirm_text(f"modo {code2}"))
            reuse = asyncio.run(j.cb_confirm_text(f"modo {code2}"))      # one use only
            self.assertIn("no hay código", reuse.lower()); self.assertIn("REAL", reuse)

    def test_variables_rechecked_after_code(self):
        with self.allow_real():
            code = CODE.search(j.crypto_mode_real_request_text()).group(1)
        out = asyncio.run(j.cb_confirm_text(f"modo {code}"))   # variables now block real
        self.assertIn("no activo el modo REAL", out); self.assertEqual(j.crypto_mode_state()["selected"], "practice")

    def test_real_activation_bumps_epoch_and_kills_practice_proposals(self):
        with self.allow_real(), self.mock_cb():
            p = self.prep()                                  # practice proposal
            j.cb_approve_text(str(p["order"]))               # practice code issued
            before = j.crypto_mode_state()["epoch"]
            out = self.go_real()
            self.assertGreater(j.crypto_mode_state()["epoch"], before)
            self.assertIn("Anulé 1", out)
            self.assertEqual(self.order(p["order"])["status"], "expired")
            self.assertFalse([r for r in j._gload()["codes"] if r.startswith(("sim#", "cb#", "mode#"))])
            self.assertIn("ya está vencida", j.cb_approve_text(str(p["order"])))

    def test_back_to_practice_is_immediate_and_keeps_tracking(self):
        with self.allow_real(), self.mock_cb():
            self.go_real()
            pending = self.prep()["order"]; j.cb_approve_text(str(pending))
            with j._data_lock:                               # orders already in flight / done
                d = j._xload()
                for oid, st in ((90, "sending"), (91, "unknown"), (92, "placed")):
                    d["orders"].append({"id": oid, "status": st, "mode": "real", "epoch": 1, "product": "BTC-USD",
                                        "side": "BUY", "usd_estimate": 5, "created": j._now().isoformat(),
                                        "config": {"market_market_ioc": {"quote_size": "5"}}, "uuid": f"u{oid}"})
                j._xsave(d)
            out = j.crypto_mode_practice_text()
            self.assertIn("PRÁCTICA activo desde ya", out)
            self.assertEqual(j.crypto_mode_state()["effective"], "practice")
            self.assertEqual(self.order(pending)["status"], "expired")
            self.assertEqual([self.order(i)["status"] for i in (90, 91, 92)], ["sending", "unknown", "placed"])
            self.assertFalse([r for r in j._gload()["codes"] if r.startswith("cb#")])
            self.assertEqual(self.real_posts(), [])

    def test_practice_switch_storage_failure_blocks_real_anyway(self):
        with self.allow_real(), self.mock_cb():
            self.go_real()
            with patch.object(j, "kv_set_many", side_effect=RuntimeError("down")), \
                 patch.object(j, "kv_set", side_effect=RuntimeError("down")):
                out = j.crypto_mode_practice_text()
            self.assertIn("BLOQUEADAS", out)
            self.assertTrue(j._mode_mem["block_real"])
            self.assertEqual(j.crypto_mode_state()["effective"], "practice")   # stored says real, brake wins
            self.assertIsNone(CODE.search(j.crypto_mode_real_request_text()))


class StorageProblems(ModeBase):
    def test_corrupt_state_blocks_real(self):
        for bad in ("garbage", {"mode": "REAL"}, {"mode": "real", "epoch": "1"}, {"mode": "real", "epoch": True},
                    {"mode": "real", "epoch": -5}, ["real"]):
            j.kv_set(j.M_KEY, bad)
            with self.allow_real():
                ms = j.crypto_mode_state()
                self.assertEqual(ms["effective"], "practice", bad); self.assertTrue(ms["problem"], bad)
                self.assertIsNone(CODE.search(j.crypto_mode_real_request_text()), bad)

    def test_unreadable_storage_blocks_real_and_pending_real_order(self):
        with self.allow_real(), self.mock_cb():
            self.go_real()
            oid = self.prep()["order"]
            real_get = j.kv_get
            def flaky(key, default):
                if key == j.M_KEY: raise RuntimeError("Upstash down")
                return real_get(key, default)
            with patch.object(j, "kv_get", side_effect=flaky):
                ms = j.crypto_mode_state()
                self.assertEqual(ms["effective"], "practice"); self.assertIn("no pude leer", ms["problem"])
                msg = j.cb_approve_text(str(oid))
            self.assertIsNone(CODE.search(msg)); self.assertEqual(self.real_posts(), [])


class Separation(ModeBase):
    def test_practice_orders_use_only_the_simulated_account(self):
        paper_before = json.dumps(j._paperload(), sort_keys=True, default=str)
        with self.mock_cb() as api:
            o = self.prep(usd=50)
            self.assertIn("PRÁCTICA", o["mode"])
            msg, out = self.approve_confirm(o["order"])
            self.assertIn("SIMULADA", msg); self.assertIn("SIMULADO", out); self.assertIn("Nada se envió", out)
            s = j._simload()
            self.assertAlmostEqual(s["cash"], 950.0, places=6); self.assertIn("BTC-USD", s["positions"])
            qty = s["positions"]["BTC-USD"]["qty"]
            o2 = self.prep(side="SELL", qty=round(qty / 2, 8))
            self.approve_confirm(o2["order"])
            api.assert_not_called()                                   # practice never touches private API
        self.assertEqual(self.order(o["order"])["status"], "simulated")
        self.assertEqual(j._xload()["log"], [])                       # real log untouched
        self.assertEqual(j.gate_spent_today(j._gload()), 0)           # real daily limit untouched
        self.assertGreater(j.sim_spent_today(j._simload()), 50)
        self.assertEqual(json.dumps(j._paperload(), sort_keys=True, default=str), paper_before)

    def test_practice_cannot_sell_what_it_does_not_have(self):
        o = self.prep(side="SELL", qty=1)
        _, out = self.approve_confirm(o["order"])
        self.assertIn("No pude ejecutar", out); self.assertEqual(self.order(o["order"])["status"], "failed")
        self.assertEqual(j._simload()["cash"], j.PAPER_START)

    def test_damaged_practice_account_is_never_overwritten(self):
        good = self.prep(usd=10)                                   # prepared before the damage
        j.kv_set(j.SIM_KEY, "damaged")
        with self.assertRaises(ValueError):
            self.prep(usd=10)                                      # refused, no proposal saved
        self.assertEqual(len(j._xload()["orders"]), 1)
        self.assertIsNone(CODE.search(j.cb_approve_text(str(good["order"]))))
        self.assertEqual(j.kv_get(j.SIM_KEY, None), "damaged")

    def test_real_orders_use_only_the_real_account(self):
        with self.allow_real(), self.mock_cb():
            self.go_real()
            o = self.prep(usd=20)
            self.assertIn("REAL", o["mode"]); self.assertTrue(o["real_orders_possible"])
            msg, out = self.approve_confirm(o["order"])
            self.assertIn("REAL", msg); self.assertIn("Orden enviada", out); self.assertIn("REAL", out)
        posts = self.real_posts()
        self.assertEqual(len(posts), 1); self.assertEqual(posts[0][2]["client_order_id"], self.order(o["order"])["uuid"])
        self.assertEqual(j.gate_spent_today(j._gload()), 20)
        self.assertEqual(j._simload()["trades"], [])

    def test_order_post_refused_outside_the_confirm_path(self):
        with self.allow_real():
            with self.assertRaises(ValueError) as ctx:
                asyncio.run(j._cb("POST", j.CB_ORDER_PATH, body={"client_order_id": "x", "product_id": "BTC-USD"}))
        self.assertIn("envío real bloqueado", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:                     # practice-only: blocked even earlier
            asyncio.run(j._cb("POST", j.CB_ORDER_PATH, body={"client_order_id": "x"}))
        self.assertIn("Solo práctica", str(ctx.exception))

    def test_backup_restore_returns_to_practice(self):
        with self.allow_real(), self.mock_cb():
            snap = json.loads(json.dumps(j.snapshot()))
            self.go_real()
            j.restore_snapshot(snap, dry_run=False)
            self.assertEqual(j.crypto_mode_state()["effective"], "practice")
        self.assertIn("crypto_practice", snap)


class Limits(ModeBase):
    def test_per_order_limit_both_modes(self):
        o = self.prep(usd=150)
        self.assertIn("límite", o.get("limit_warning", ""))
        self.assertIn("No la apruebo", j.cb_approve_text(str(o["order"])))
        with self.allow_real(), self.mock_cb():
            self.go_real()
            o = self.prep(usd=150)
            self.assertIn("No la apruebo", j.cb_approve_text(str(o["order"])))
        self.assertEqual(self.real_posts(), [])

    def test_daily_limit_is_separate_per_account(self):
        with self.allow_real(), self.mock_cb():
            self.go_real()
            with j._data_lock:
                g = j._gload(); j.gate_add_spent(g, 250); j._gsave(g)
            o = self.prep(usd=60)
            self.assertIn("límite del día", j.cb_approve_text(str(o["order"])))
            j.crypto_mode_practice_text()
            p = self.prep(usd=60)                                       # practice counts its own day
            _, out = self.approve_confirm(p["order"])
            self.assertIn("SIMULADO", out)
        self.assertEqual(self.real_posts(), [])


class Duplicates(ModeBase):
    def test_real_confirm_twice_posts_once(self):
        with self.allow_real(), self.mock_cb():
            self.go_real()
            o = self.prep()
            msg = j.cb_approve_text(str(o["order"])); code = CODE.search(msg).group(1)
            first = asyncio.run(j.cb_confirm_text(f"{o['order']} {code}"))
            again = asyncio.run(j.cb_confirm_text(f"{o['order']} {code}"))
        self.assertIn("Orden enviada", first); self.assertIn("ya está enviada", again)
        self.assertEqual(len(self.real_posts()), 1)

    def test_uncertain_result_is_never_resent(self):
        async def boom(method, path, params=None, body=None):
            if path == j.CB_ORDER_PATH:
                self.calls.append((method, path, body)); raise TimeoutError
            return await self.cb(method, path, params=params, body=body)
        with self.allow_real(), self.mock_cb():
            self.go_real()
            o = self.prep()
            with patch.object(j, "_cb", side_effect=boom):
                _, out = self.approve_confirm(o["order"])
                self.assertIn("No la reenvío sola", out)
                self.assertIn("sin confirmar", j.cb_approve_text(str(o["order"])))
        self.assertEqual(self.order(o["order"])["status"], "unknown"); self.assertEqual(len(self.real_posts()), 1)
        self.assertEqual(j.gate_spent_today(j._gload()), 20)           # limit is NOT given back when uncertain

    def test_mode_change_between_confirm_and_send_cancels(self):
        with self.allow_real(), self.mock_cb():
            self.go_real()
            o = self.prep()
            original = j._real_execute
            async def switch_then_send(order):
                j.crypto_mode_to_practice()                             # owner hits practice at the last moment
                return await original(order)
            with patch.object(j, "_real_execute", new=switch_then_send):
                _, out = self.approve_confirm(o["order"])
        self.assertIn("No envié", out); self.assertEqual(self.real_posts(), [])
        self.assertEqual(self.order(o["order"])["status"], "cancelled")
        self.assertEqual(j.gate_spent_today(j._gload()), 0)             # limit given back: nothing was sent

    def test_proposal_from_old_epoch_cannot_run(self):
        with self.allow_real(), self.mock_cb():
            self.go_real()
            o = self.prep()
            msg = j.cb_approve_text(str(o["order"])); code = CODE.search(msg).group(1)
            j.crypto_mode_to_practice(); self.go_real()                 # practice and back to real
            out = asyncio.run(j.cb_confirm_text(f"{o['order']} {code}"))
        self.assertNotIn("Orden enviada", out); self.assertEqual(self.real_posts(), [])


class Labels(ModeBase):
    def test_mode_shown_everywhere(self):
        o = self.prep()
        self.assertIn("PRÁCTICA", o["mode"])
        msg, out = self.approve_confirm(o["order"])
        self.assertIn("PRÁCTICA", msg); self.assertIn("PRÁCTICA", out)
        self.assertIn("PRÁCTICA", asyncio.run(j.crypto_overview_text("")))
        self.assertIn("Modo cripto", j.security_text())
        self.assertIn("/cripto modo", j.HELP_TEXT)
        self.assertIn("PRACTICE", j.system_prompt())


if __name__ == "__main__":
    unittest.main(verbosity=1)
