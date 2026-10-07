"""Jarvis 4.0.5 corrections (Part 1, items 1.4 to 1.8). No network, no real Telegram, no real money."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_jarvis as base
j = base.j


class Base(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True); j._seen_updates.clear(); j._rate_hits.clear(); j.conversations.clear()


def csv_rows(n, start_day=1):
    rows = ["Date,Description,Amount"]
    for i in range(n):
        rows.append(f"10/{start_day + i:02d}/2026,TIENDA {i},-{i + 1}.00")
    return "\n".join(rows).encode()


class BankCeiling(Base):
    """1.4: reaching the movement ceiling is announced in the import, /banco and the brief."""
    def test_drop_is_announced_everywhere(self):
        with patch.object(j, "BANK_MAX_TX", 5), patch.object(j, "BANK_WARN_AT", 4):
            r = j.import_statement("a.csv", csv_rows(7), "negocio")
            self.assertEqual(r["dropped_oldest"], 2)
            msg = j.import_text(r)
            self.assertIn("tope", msg); self.assertIn("/exportar movimientos", msg)
            self.assertIn("borré 2", j.bank_text()); self.assertIn("2026-10-01", j.bank_text())
            self.assertTrue(any("tope" in line for line in j.bank_brief_lines()))
            self.assertEqual(len(j._kload()["tx"]), 5)

    def test_near_ceiling_warns_before_losing_anything(self):
        with patch.object(j, "BANK_MAX_TX", 10), patch.object(j, "BANK_WARN_AT", 9):
            j.import_statement("a.csv", csv_rows(9), "negocio")
            self.assertIn("9 de 10", j.bank_text())
            self.assertEqual(j._kload().get("dropped_log", []), [])

    def test_no_warning_far_from_ceiling(self):
        j.import_statement("a.csv", csv_rows(3), "negocio")
        self.assertEqual(j.bank_capacity_note(), ""); self.assertNotIn("⚠️ Banco", j.bank_text())

    def test_diagnostics_measures_stored_size(self):
        j.TG_TOKEN = ""
        j.import_statement("a.csv", csv_rows(3), "negocio")
        text = asyncio.run(j.diagnostics_text())
        self.assertIn("Banco guardado: 3 de 3,000", text); self.assertIn("KB", text)


class ChatContextNotice(Base):
    """1.5: /diagnostico says the chat context does not survive a deploy (data does)."""
    def test_diagnostics_says_it(self):
        j.TG_TOKEN = ""
        j.conversations["tg:1"] = [{"role": "user", "content": "hola"}]
        text = asyncio.run(j.diagnostics_text())
        self.assertIn("Contexto de charla: 1 conversación", text); self.assertIn("No sobrevive un deploy", text)


class SendingRecovery(Base):
    """1.6: an order left "sending" by a crash becomes "unknown" (real) or "failed" (practice); never resent."""
    def add_order(self, oid, mode, minutes_ago, status="sending"):
        at = (j._now() - j.datetime.timedelta(minutes=minutes_ago)).isoformat(timespec="seconds")
        with j._data_lock:
            d = j._xload()
            d["orders"].append({"id": oid, "status": status, "mode": mode, "epoch": 1, "product": "BTC-USD",
                                "side": "BUY", "usd_estimate": 20, "created": at, "sent_at": at, "uuid": f"u{oid}",
                                "config": {"market_market_ioc": {"quote_size": "20"}}})
            j._xsave(d)

    def status(self, oid):
        return next(o for o in j._xload()["orders"] if o["id"] == oid)

    def test_sweep_marks_and_explains(self):
        self.add_order(1, "real", 10); self.add_order(2, "practice", 10); self.add_order(3, "real", 1)
        self.add_order(4, "real", 10, status="placed")
        with j._data_lock:
            g = j._gload(); j.gate_add_spent(g, 20); j._gsave(g)
        with patch.object(j, "_cb", new=AsyncMock()) as cb:
            changed = j.crypto_sending_sweep()
        cb.assert_not_called()                                          # nothing is resent
        self.assertEqual(self.status(1)["status"], "unknown"); self.assertEqual(self.status(2)["status"], "failed")
        self.assertEqual(self.status(3)["status"], "sending")           # still inside the window: an old instance may finish
        self.assertEqual(self.status(4)["status"], "placed")
        self.assertEqual(j.gate_spent_today(j._gload()), 20)            # uncertain: the limit is not given back
        text = j.crypto_sending_text(changed)
        self.assertIn("Revisa la app de Coinbase ANTES de repetirla", text); self.assertIn("No la repetí", text)
        self.assertIn("sin confirmar", j.cb_approve_text("1"))           # and it cannot be approved again

    def test_order_being_sent_by_this_process_is_not_swept(self):
        self.add_order(5, "real", 10)
        j._REAL_SENDING_HERE.add(5)
        try:
            j.crypto_sending_sweep()
        finally:
            j._REAL_SENDING_HERE.discard(5)
        self.assertEqual(self.status(5)["status"], "sending")

    def test_confirm_code_never_enters_queue(self):
        with self.assertRaises(ValueError):
            j._tg_enqueue(9001, {"chat": {"id": 123, "type": "private"}, "from": {"id": 123}, "text": "/confirmar 1 123456"})
        self.assertEqual(j.kv_get(j.TG_INBOX_KEY, {}), {})


class SeenUpdatesLocal(Base):
    """1.7: without Redis, recent update ids are evicted one by one and survive a restart."""
    def msg(self, uid):
        return {"chat": {"id": 123, "type": "private"}, "from": {"id": 123}, "text": f"/hoy {uid}"}

    def test_no_mass_forgetting_at_the_limit(self):
        with patch.object(j, "TG_SEEN_MAX", 5):
            for uid in range(1, 8):
                self.assertTrue(j._first_time(uid))
            self.assertFalse(j._first_time(7)); self.assertFalse(j._first_time(3))   # recent ones still known
            self.assertTrue(j._first_time(1))                                         # only the oldest left

    def test_survives_restart(self):
        self.assertEqual(j._tg_enqueue(41, self.msg(41)), "new")
        j._tg_job_finish(41)                                       # processed: the inbox no longer has it
        j._seen_updates.clear(); j._rate_hits.clear(); j._seen_order.clear(); j._seen_state["dir"] = None   # simulate a restart
        self.assertEqual(j._tg_enqueue(41, self.msg(41)), "dup")
        self.assertFalse(j._first_time(41))


class AtomicTakeOver(Base):
    """1.8: two processes booting together: the last one leads, the first gets StaleInstance on write."""
    def test_two_boots_only_last_writes(self):
        from test_hardening import FakeRedis
        r = FakeRedis()
        with patch.object(j, "_redis", new=r), patch.object(j, "USE_REDIS", True):
            with patch.object(j, "INSTANCE_ID", "proc-a"):
                j.fence_take_leadership()
            with patch.object(j, "INSTANCE_ID", "proc-b"):
                j.fence_take_leadership()
                j.kv_set("jarvis:test", {"by": "b"})
            with patch.object(j, "INSTANCE_ID", "proc-a"):
                with self.assertRaises(j.StaleInstance):
                    j.kv_set("jarvis:test", {"by": "a"})
        self.assertEqual(json.loads(r.d["jarvis:test"]), {"by": "b"})
        j._fence.update(mode="off", leader=True)

    def test_take_over_is_a_single_script(self):
        self.assertIn("SET", j._TAKE_LEADER); self.assertIn("GET", j._TAKE_LEADER)
        self.assertNotIn("NX", j._TAKE_LEADER)       # a new deploy must be able to displace the old process


class RateLimit(Base):
    """2.1: 30 messages per minute per key (/chat) or per chat (webhook) -> 429, nothing queued."""
    def tg(self, uid, chat=123):
        return {"update_id": uid, "message": {"chat": {"id": chat, "type": "private"}, "from": {"id": 123}, "text": "/ayuda"}}

    def test_webhook_429_after_limit_and_nothing_queued(self):
        from fastapi.testclient import TestClient
        j.TG_SECRET = "sec"; c = TestClient(j.app); h = {"x-telegram-bot-api-secret-token": "sec"}
        with patch.object(j, "_tg_send", new=AsyncMock()), patch.object(j, "RATE_PER_MIN", 3):
            codes = [c.post("/telegram", headers=h, json=self.tg(100 + i)).status_code for i in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])
        self.assertFalse(j._seen_has(103))                    # the refused update was not marked seen: Telegram retries it

    def test_chat_429_per_key(self):
        from fastapi.testclient import TestClient
        c = TestClient(j.app); h = {"x-api-key": j.API_KEY}
        with patch.object(j, "RATE_PER_MIN", 2), patch.object(j, "run", new=AsyncMock(return_value="ok")):
            codes = [c.post("/chat", headers=h, json={"message": "hola"}).status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])

    def test_window_slides(self):
        with patch.object(j, "RATE_PER_MIN", 2):
            self.assertTrue(j._rate_ok("b", now=0)); self.assertTrue(j._rate_ok("b", now=1))
            self.assertFalse(j._rate_ok("b", now=2)); self.assertTrue(j._rate_ok("b", now=61))
            self.assertTrue(j._rate_ok("other", now=2))


class DelegationLimits(Base):
    """2.4: max 3 delegations in flight; 3 failures in a row mark the agent down (no retry on every message)."""
    def setUp(self):
        super().setUp(); j._deleg["active"] = 0; j._deleg["agents"].clear()

    def client(self, fail=False, delay=0.0, counter=None):
        class R:
            def raise_for_status(self):
                if fail: raise RuntimeError("500")
            def json(self): return {"ok": True}
        class C:
            def __init__(s, **k): pass
            async def __aenter__(s): return s
            async def __aexit__(s, *a): pass
            async def post(s, *a, **k):
                if counter is not None: counter.append(1)
                await asyncio.sleep(delay); return R()
        return C

    def test_breaker_after_three_failures(self):
        calls = []
        with patch.dict(j.AGENTS, {"call": "https://call.example.com"}), patch.object(j, "EXTERNAL_AGENT_KEY", "ext"), \
             patch.object(j.httpx, "AsyncClient", self.client(fail=True, counter=calls)):
            for _ in range(3):
                self.assertIn("error", asyncio.run(j.delegate("call", "x", approved_action_id=1)))
            r = asyncio.run(j.delegate("call", "x", approved_action_id=1))
        self.assertIn("caído", r["error"]); self.assertEqual(len(calls), 3)          # 4th never sent
        self.assertTrue(j.external_agents_status()["call"]["down"])

    def test_success_resets_failures(self):
        with patch.dict(j.AGENTS, {"call": "https://call.example.com"}), patch.object(j, "EXTERNAL_AGENT_KEY", "ext"):
            with patch.object(j.httpx, "AsyncClient", self.client(fail=True)):
                asyncio.run(j.delegate("call", "x", approved_action_id=1)); asyncio.run(j.delegate("call", "x", approved_action_id=1))
            with patch.object(j.httpx, "AsyncClient", self.client()):
                self.assertEqual(asyncio.run(j.delegate("call", "x", approved_action_id=1)), {"ok": True})
        self.assertEqual(j._deleg["agents"]["call"]["fails"], 0)

    def test_max_three_in_flight(self):
        async def go():
            return await asyncio.gather(*[j.delegate("call", f"x{i}", approved_action_id=i) for i in range(4)])
        with patch.dict(j.AGENTS, {"call": "https://call.example.com"}), patch.object(j, "EXTERNAL_AGENT_KEY", "ext"), \
             patch.object(j.httpx, "AsyncClient", self.client(delay=0.2)):
            out = asyncio.run(go())
        self.assertEqual(sum(1 for o in out if o == {"ok": True}), 3)
        self.assertIn("3 delegaciones en curso", [o for o in out if "error" in o][0]["error"])
        self.assertEqual(j._deleg["active"], 0)


class Export(Base):
    """4.1: /exportar movimientos|libros|trabajos -> CSV, last 4 digits only, formula-safe, private chat only."""
    def test_csv_contents_and_safety(self):
        import csv, io
        j.import_statement("a.csv", b"Date,Description,Amount\n10/05/2026,=HYPERLINK(evil),-5.00\n10/06/2026,CAFE,-3.00\n",
                           "negocio")
        name, raw, n = j.export_csv("movimientos")
        rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        self.assertTrue(name.endswith(".csv")); self.assertEqual(n, 2)
        self.assertEqual(rows[0][:4], ["fecha", "cuenta", "descripcion", "monto"])
        self.assertTrue(rows[1][2].startswith("'="))                      # formula neutralized
        self.assertEqual(rows[1][3], "-5.0")                                # numbers stay numbers
        j.add_income(100, "Cliente"); j.add_expense(40, "materials", "pintura")
        rows = list(csv.reader(io.StringIO(j.export_csv("libros")[1].decode("utf-8-sig"))))
        self.assertEqual(sorted(r[0] for r in rows[1:]), ["gasto", "ingreso"]); self.assertEqual({r[4] for r in rows[1:]}, {"USD"})
        c = j.add_client("Ana"); j.add_job(c["id"], "Cocina", price=900, advance=100, status="confirmed")
        rows = list(csv.reader(io.StringIO(j.export_csv("trabajos")[1].decode("utf-8-sig"))))
        self.assertEqual(rows[1][1:3], ["Ana", "Cocina"])
        with self.assertRaises(ValueError):
            j.export_csv("contraseñas")

    def test_no_full_account_numbers(self):
        ofx = (b"OFXHEADER:100\n<OFX><BANKMSGSRSV1><STMTTRNRS><STMTRS><BANKACCTFROM><ACCTID>0001234567890</BANKACCTFROM>"
               b"<BANKTRANLIST><STMTTRN><TRNTYPE>DEBIT<DTPOSTED>20261005<TRNAMT>-50.00<FITID>F1<NAME>HOME DEPOT"
               b"</STMTTRN></BANKTRANLIST></STMTRS></STMTTRNRS></BANKMSGSRSV1></OFX>")
        j.import_statement("a.qfx", ofx, "negocio")
        raw = j.export_csv("movimientos")[1].decode("utf-8-sig")
        self.assertNotIn("0001234567890", raw); self.assertIn("••7890", raw)

    def test_only_private_chat(self):
        from fastapi.testclient import TestClient
        j.TG_SECRET = "sec"; c = TestClient(j.app); h = {"x-telegram-bot-api-secret-token": "sec"}
        sent, docs = [], []
        async def fake_send(chat, text): sent.append(text)
        async def fake_doc(chat, name, raw, caption="", mime="text/csv"): docs.append(name)
        with patch.object(j, "_tg_send", new=fake_send), patch.object(j, "_tg_send_document", new=fake_doc):
            for i, (cmd, typ) in enumerate((("/exportar libros", "group"), ("/export libros", "group"),
                                            ("/exportar libros", "private"))):
                c.post("/telegram", headers=h, json={"update_id": 700 + i, "message": {"chat": {"id": 123, "type": typ},
                       "from": {"id": 123}, "text": cmd}})
        self.assertEqual(len(docs), 1); self.assertEqual(sum("privado" in t for t in sent), 2)


class BankSearch(Base):
    """4.2: normalized descriptions; search by words, accents and spacing do not matter."""
    def test_search_variants(self):
        j.import_statement("a.csv", "Date,Description,Amount\n10/05/2026,POS HOME DEPOT #123 SAN JUAN,-50.00\n"
                           "10/06/2026,Panadería La Española,-8.00\n10/07/2026,LOWES #555,-20.00\n".encode(), "negocio")
        self.assertEqual(j._kload()["tx"][0]["norm"], "pos home depot 123 san juan")
        find = lambda q: [m["desc"] for m in j.bank_transactions(query=q, start="2026-01-01", end="2026-12-31")["movements"]]
        self.assertEqual(find("home depot"), ["POS HOME DEPOT #123 SAN JUAN"])
        self.assertEqual(find("Home-Depot"), ["POS HOME DEPOT #123 SAN JUAN"])
        self.assertEqual(find("homedepot"), ["POS HOME DEPOT #123 SAN JUAN"])
        self.assertEqual(find("panaderia espanola"), ["Panadería La Española"])
        self.assertEqual(find("depot lowes"), [])
        self.assertEqual(len(find("")), 3)

    def test_old_rows_without_norm_still_found(self):
        j.import_statement("a.csv", b"Date,Description,Amount\n10/05/2026,CAFE LA ESQUINA,-3.00\n", "negocio")
        with j._data_lock:
            d = j._kload(); d["tx"][0].pop("norm"); j._ksave(d)
        self.assertEqual(j.bank_transactions(query="esquina", start="2026-01-01", end="2026-12-31")["count"], 1)


class Currency(Base):
    """4.3: optional currency, USD by default, never converted; totals are USD only."""
    def test_default_usd_stored_as_before(self):
        e = j.add_income(100, "Cliente")
        self.assertNotIn("currency", e); self.assertNotIn("currency", j._bload()["income"][0])

    def test_other_currency_kept_apart(self):
        j.add_income(100, "Cliente PR"); j.add_income(50, "Cliente España", currency="eur")
        j.add_expense(30, "materials"); j.add_expense(10, "materials", currency="EUR")
        s = j.finances_summary()
        self.assertEqual((s["total_income"], s["total_expenses"], s["net_profit"]), (100, 30, 70))
        self.assertEqual(s["other_currencies"], {"EUR": {"income": 50.0, "expenses": 10.0}})
        self.assertIn("no convierte", s["note"])
        self.assertEqual(j.tax_estimate(10)["suggested_tax_reserve"], 7.0)      # USD net only
        r = j._extensions.business_report(j._today().strftime("%Y-%m"))
        self.assertEqual((r["income"], r["expenses"]), (100, 30)); self.assertIn("EUR", r["note"])

    def test_invalid_currency_and_tool_schema(self):
        for bad in ("dólares", "US", "1234", "U$D"):
            with self.assertRaises(ValueError):
                j.add_income(5, currency=bad)
        schema = next(t for t in j.TOOLS if t["name"] == "add_expense")["input_schema"]["properties"]
        self.assertIn("currency", schema)
        self.assertEqual(asyncio.run(j.run_tool("add_income", {"amount": 5, "currency": "mxn"}))["currency"], "MXN")


if __name__ == "__main__":
    unittest.main()
