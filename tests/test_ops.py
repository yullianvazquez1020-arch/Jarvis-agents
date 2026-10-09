"""Jarvis 4.2.3 ruta, huecos y piso. Servicios simulados, sin red y sin Redis de producción.
El piso no es un ingreso y no sube los topes. /ruta y /huecos no envían ni cobran."""
import asyncio
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_brief as tb
import jarvis_ops as ops
import jarvis_v420 as v
import jarvis_learn as learn

j = tb.j


class OpsBase(tb.BriefBase):
    def books_income(self):
        return [dict(x) for x in j._bload()["income"]]


class Floor(OpsBase):
    def test_words_are_rejected_and_books_stay(self):
        before = self.books_income()
        self.assertTrue(ops.floor_command("poderoso").startswith("⚠️"))
        self.assertIsNone(ops.ticket_floor())
        self.assertEqual(self.books_income(), before)
        self.assertEqual(v.HARD_ORDER, 100.0)
        self.assertEqual(v.HARD_DAY, 300.0)

    def test_floor_is_not_income(self):
        j.kv_set(j.B_KEY, {"income": [{"id": 1, "amount": 40, "currency": "USD", "date": "2026-10-06"}], "expenses": []})
        before = v.cashflow_snapshot(j)["income"]
        self.assertIn("Piso guardado", ops.floor_command("38500"))
        self.assertEqual(ops.ticket_floor(), Decimal("38500.00"))
        self.assertEqual(v.cashflow_snapshot(j)["income"], before)
        self.assertNotIn("ticket_min_usd", json.dumps(j._bload()))
        self.assertIn("Piso de ticket borrado", ops.floor_command("borrar"))
        self.assertIsNone(ops.ticket_floor())


class Route(OpsBase):
    def test_gap_uses_floor_without_calling_money(self):
        j.kv_set("jarvis:profile", {**j.DEFAULT_PROFILE, "meta_semanal_usd": 1000, "ticket_min_usd": 400})
        j.kv_set(j.B_KEY, {"income": [], "expenses": []})
        with patch.object(j, "send_message_text", new=AsyncMock()), \
             patch.object(j, "cb_approve_text", side_effect=AssertionError("aprobar")), \
             patch.object(j.client.messages, "create", new=AsyncMock(side_effect=AssertionError("modelo"))):
            text = ops.route_command()
        self.assertIn("Falta esta semana: $1,000.00", text)
        self.assertIn("3 cobro(s)", text)
        self.assertIn("no ejecutada", text.lower())
        self.assertNotIn("1000000", text)

    def test_group_cannot_run_route(self):
        self.assertEqual(self.post("/ruta", 9101, chat_type="group"), ["Este comando requiere tu chat privado."])

    def test_voice_route_does_not_write(self):
        before = {p: p.read_text() for p in Path(j.DATA_DIR).glob("*.json")
                  if not p.name.startswith("jarvis_tg_")}
        with patch.object(j, "_tg_send", new=AsyncMock()):
            reply = asyncio.run(j._handle_tg(j.TG_OWNER, "ruta de hoy", read_only=True))
        self.assertIn("RUTA", reply)
        after = {p: p.read_text() for p in Path(j.DATA_DIR).glob("*.json")
                 if not p.name.startswith("jarvis_tg_")}
        self.assertEqual(after, before)


class Holes(OpsBase):
    def test_missing_price_is_listed_and_finished_job_is_not(self):
        c = self.client("Carmen")
        open_job = j.add_job(c["id"], "Sin precio", price=0, status="confirmed", due_date="2026-10-20")
        done = j.add_job(c["id"], "Terminado", price=500, status="confirmed", due_date="2026-10-01")
        j.record_job_payment(done["id"], 500, date="2026-10-06")
        self.assertIn("finalización confirmada", learn.complete_command(str(done["id"])))
        text = ops.holes_command()
        self.assertIn(f"#{open_job['id']}", text)
        self.assertIn("precio", text)
        self.assertNotIn(f"#{done['id']}", text)
        self.assertIn(ops.NOT_DONE, text)
