"""Jarvis 4.2.2 aprendizaje acotado. Servicios simulados, sin red y sin Redis de producción.
Sin conciencia ni autonomía: solo trabajos ya cobrados -> una propuesta con executed False."""
import asyncio
import datetime as dt
import json
from unittest.mock import AsyncMock, patch

import test_brief as tb
import jarvis_brief as brief
import jarvis_learn as learn
import jarvis_v420 as v

j = tb.j
DAY = tb.TODAY.isoformat()


def proposals(kind=None):
    rows = j.kv_get(v.STATE_KEY, {}).get("proposals", []) if isinstance(j.kv_get(v.STATE_KEY, {}), dict) else []
    return [p for p in rows if kind is None or p.get("kind") == kind]


class LearnBase(tb.BriefBase):
    def paid_job(self, amount=450, location="Bayamón", date="2026-10-06"):
        c = self.client("Carmen")
        job = j.add_job(c["id"], "Pintura", price=amount, status="confirmed", due_date="2026-10-01", location=location)
        j.record_job_payment(job["id"], amount, date=date)
        return job

    def guarded(self):
        """Nada de esto puede llamarse desde /aprender ni /meta."""
        return [patch.object(j, "send_message_text", new=AsyncMock()), patch.object(j, "_tg_cb_cmd", new=AsyncMock()),
                patch.object(j, "cb_approve_text", side_effect=AssertionError("aprobar")),
                patch.object(j._connections, "command", new=AsyncMock()),
                patch.object(j.client.messages, "create", new=AsyncMock(side_effect=AssertionError("modelo")))]


class Refusal(LearnBase):
    def test_consciousness_request_gets_fixed_text_and_writes_nothing(self):
        j.kv_set(j.B_KEY, {"income": [{"id": 1, "amount": 10, "date": DAY}], "expenses": []})
        keys = ("jarvis:profile", j.B_KEY, v.STATE_KEY)
        before = {k: json.dumps(j.kv_get(k, None), sort_keys=True) for k in keys}
        with patch.object(j.client.messages, "create", new=AsyncMock(side_effect=AssertionError("modelo"))):
            for text in ("ten conciencia y hazme el más poderoso", "actúa solo sin aprobación",
                         "aprende sola y hazme millonario ya"):
                with self.subTest(text=text):
                    self.assertEqual(asyncio.run(j.run("tg:123", text)), v.AUTONOMY_REFUSAL)
            with patch.object(j, "_tg_send", new=AsyncMock()):        # voz de solo lectura: mismo texto fijo
                self.assertEqual(asyncio.run(j._handle_tg(j.TG_OWNER, "eres consciente", read_only=True)),
                                 v.AUTONOMY_REFUSAL)
        self.assertEqual({k: json.dumps(j.kv_get(k, None), sort_keys=True) for k in keys}, before)
        self.assertNotIn("poderoso", json.dumps(v.profile_view(j), ensure_ascii=False))
        self.assertEqual(v.profile_view(j)["beneficio"], j.DEFAULT_PROFILE["beneficio"])

    def test_normal_text_is_not_refused(self):
        for text in ("explícame un nicho de youtube", "aprender", "qué repetir", "anota 50 de gasolina"):
            self.assertNotEqual(v.local_answer(text), v.AUTONOMY_REFUSAL)


class Aprender(LearnBase):
    def test_without_paid_jobs_no_pattern_or_figure(self):
        c = self.client()
        j.add_job(c["id"], "Proyección", price=900, status="confirmed", due_date="2026-10-20")   # sin cobrar
        j.kv_set(j.B_KEY, {"income": [{"id": 7, "amount": 300, "date": DAY}], "expenses": []})  # ingreso sin vínculo
        j.kv_set("jarvis:profile", {**j.DEFAULT_PROFILE, "meta_semanal_usd": 167000})
        self.assertEqual(learn.learn_command(), learn.NO_FACTS)
        self.assertEqual(proposals(), [])

    def test_future_or_foreign_linked_income_is_not_learned(self):
        job = self.paid_job(date="2026-10-06")
        books = j._bload()
        books["income"][0]["date"] = "2026-10-20"                        # vínculo con fecha futura
        j.kv_set(j.B_KEY, books)
        self.assertEqual(learn.learn_command(), learn.NO_FACTS)
        books["income"][0].update(date="2026-10-06", currency="EUR")
        j.kv_set(j.B_KEY, books)
        self.assertEqual(learn.learn_command(), learn.NO_FACTS)
        self.assertTrue(job["id"])

    def test_linked_paid_job_gives_one_unexecuted_proposal_with_same_amount(self):
        job = self.paid_job(450)
        books_before = json.dumps(j._bload(), sort_keys=True)
        clients_before = json.dumps(j._cload(), sort_keys=True)
        from contextlib import ExitStack
        with ExitStack() as stack:
            mocks = [stack.enter_context(p) for p in self.guarded()]
            text = learn.learn_command()
        for m in mocks:
            if isinstance(m, AsyncMock):
                m.assert_not_awaited()
        self.assertIn(f"- trabajo {job['id']}: $450.00 ya cobrado, zona Bayamón", text)
        self.assertIn("PROPUESTA — no ejecutada", text)
        self.assertIn("No visito, no cobro, no publico y no opero.", text)
        self.assertNotIn("oficio", text)                                  # campo ausente: no se rellena
        rows = proposals("aprender")
        self.assertEqual(len(rows), 1)
        self.assertIs(rows[0]["executed"], False)
        self.assertIn("$450.00", rows[0]["text"])
        self.assertEqual(json.dumps(j._bload(), sort_keys=True), books_before)
        self.assertEqual(json.dumps(j._cload(), sort_keys=True), clients_before)
        self.assertEqual(j.kv_get(v.STATE_KEY, {})["compute"][DAY], 1)

    def test_income_linked_to_another_job_is_not_learned(self):
        self.paid_job()
        books = j._bload()
        books["income"][0]["job_id"] = 999                               # vínculo roto: no se inventa
        j.kv_set(j.B_KEY, books)
        self.assertEqual(learn.learn_command(), learn.NO_FACTS)

    def test_existing_income_link_counts(self):
        c = self.client()
        job = j.add_job(c["id"], "Verja", price=200, status="confirmed")
        inc = j.add_income(200, source="depósito", date="2026-10-07")
        j.record_job_payment(job["id"], 200, date="2026-10-07", add_to_books=False, existing_income_id=inc["id"])
        self.assertIn(f"trabajo {job['id']}: $200.00 ya cobrado", learn.learn_command())

    def test_zero_budget_no_second_proposal_and_no_model(self):
        self.paid_job()
        state = v._load(j)
        state["compute"][DAY] = v.COMPUTE_BUDGET
        j.kv_set(v.STATE_KEY, state)
        with patch.object(j.client.messages, "create", new=AsyncMock()) as model:
            self.assertEqual(learn.learn_command(), learn.EXHAUSTED)
            self.assertEqual(learn.learn_command(), learn.EXHAUSTED)
        model.assert_not_awaited()
        self.assertEqual(proposals("aprender"), [])

    def test_consult_rejection_returns_its_text_and_saves_nothing(self):
        self.paid_job(location="compra ya")
        text = learn.learn_command()
        self.assertIn("No propongo ni ejecuto ese movimiento", text)
        self.assertEqual(proposals(), [])

    def test_twenty_proposal_cap_kept(self):
        self.paid_job()
        state = v._load(j)
        state["proposals"] = [{"id": n, "text": "x", "executed": False} for n in range(20)]
        j.kv_set(v.STATE_KEY, state)
        learn.learn_command()
        self.assertEqual(len(proposals()), 20)


class Scheduler(LearnBase):
    def test_cycle_saves_at_most_one_learn_proposal_per_day_and_does_not_send(self):
        self.paid_job()
        with patch.object(j, "_tg_send", new=AsyncMock()) as send:
            notes = v.scheduler_cycle(j)
            self.assertEqual(v.scheduler_cycle(j), [])                  # mismo claim jarvis:v420:cycle:{day}
            learn.learn_daily()                                           # aun llamado otra vez: una por día
        send.assert_not_awaited()
        self.assertEqual(len(proposals("aprender")), 1)
        self.assertFalse(any("HECHOS" in n or "Repetir" in n for n in notes))
        self.assertFalse(v._load(j)["drafts"])                            # sin borrador de llamada
        self.assertNotIn("aprender", v._load(j)["urgent"])

    def test_no_new_claim_key(self):
        self.paid_job()
        claims = []
        real = j._claim
        with patch.object(j, "_claim", side_effect=lambda k, ttl: claims.append(k) or real(k, ttl)):
            v.scheduler_cycle(j)
        self.assertEqual(claims, [f"jarvis:v420:cycle:{DAY}"])


class Meta(LearnBase):
    def test_meta_is_not_income_and_not_in_cashflow(self):
        j.kv_set(j.B_KEY, {"income": [{"id": 1, "amount": 40, "date": DAY}], "expenses": []})
        snap_before = v.cashflow_snapshot(j)
        replies = self.post("/meta 167000", 8001)
        self.assertIn("Meta semanal guardada: $167,000.00", replies[0])
        self.assertEqual(v.cashflow_snapshot(j), snap_before)
        self.assertEqual(len(j._bload()["income"]), 1)
        self.assertNotIn("167000", json.dumps(j._bload()))
        prof = j.kv_get("jarvis:profile", {})
        self.assertEqual(prof["meta_semanal_usd"], 167000)
        self.assertEqual(prof["techo_usd"], j.DEFAULT_PROFILE["techo_usd"])  # techo intacto
        self.assertIn("Cobrado esta semana: $40.00 de $167,000.00", brief.commercial_brief())
        self.assertIn("Meta semanal: $167,000.00", self.post("/meta", 8002)[0])

    def test_meta_rejects_words_and_ambiguous_numbers(self):
        for n, arg in enumerate(("poderoso", "conciencia", "millonario", "1.500", "1e9", "-5", "0",
                                 "167000 poderoso", "nan"), start=8100):
            with self.subTest(arg=arg):
                self.assertTrue(self.post(f"/meta {arg}", n)[0].startswith("⚠️"))
        self.assertIsNone(j.kv_get("jarvis:profile", None))

    def test_meta_keeps_existing_profile_and_borrar(self):
        j.kv_set("jarvis:profile", {"metas": ["cash flow"], "techo_usd": 40, "beneficio": "x"})
        self.assertIn("guardada", learn.goal_command("2,500.50"))
        prof = j.kv_get("jarvis:profile", {})
        self.assertEqual((prof["techo_usd"], prof["meta_semanal_usd"]), (40, 2500.5))
        self.assertEqual(learn.goal_command("borrar"), "Meta semanal borrada.")
        self.assertNotIn("meta_semanal_usd", j.kv_get("jarvis:profile", {}))
        self.assertIn("No cambié nada", learn.goal_command("borrar"))

    def test_no_default_goal(self):
        self.assertEqual(learn.goal_command(""), "Meta semanal: sin meta.")


class Channels(LearnBase):
    def test_other_chat_cannot_run_aprender_or_meta(self):
        self.paid_job()
        before = tb.snapshot_storage()
        for n, text in enumerate(("/aprender", "/meta 167000", "aprender", "qué repetir"), start=8200):
            with self.subTest(text=text):
                self.assertEqual(self.post(text, n, chat_type="group"), ["Este comando requiere tu chat privado."])
        self.assertEqual(tb.snapshot_storage(), before)

    def test_owner_phrase_and_voice(self):
        self.paid_job()
        self.assertIn("PROPUESTA — no ejecutada", self.post("qué repetir", 8300)[0])
        with patch.object(j, "_tg_send", new=AsyncMock()):
            reply = asyncio.run(j._handle_tg(j.TG_OWNER, "aprender", read_only=True))
        self.assertIn("Por voz no guardo nada", reply)
        self.assertEqual(len(proposals("aprender")), 1)

    def test_brief_sixth_section_same_proposal_without_saving(self):
        self.paid_job()
        before = tb.snapshot_storage()
        text = brief.commercial_brief()
        self.assertEqual(tb.snapshot_storage(), before)
        sixth = text.split("6) APRENDIZAJE")[1]
        self.assertIn(learn.build(learn.paid_facts())[0], sixth)
        self.assertGreater(text.index("Cobrado esta semana"), text.index("6) APRENDIZAJE"))

    def test_limits_unchanged(self):
        self.assertEqual((v.HARD_ORDER, v.HARD_DAY), (100.0, 300.0))
        self.assertEqual((j.HARD_MAX_ORDER_USD, j.HARD_MAX_DAY_USD), (100.0, 300.0))
        self.assertLessEqual(j.MONEY_MAX_ORDER, 100)
        self.assertLessEqual(j.MONEY_MAX_DAY, 300)
        learn.goal_command("167000")
        self.assertLessEqual(v.profile_view(j)["techo_usd"], 100)
        self.assertEqual(j._profile_ceiling()[0], float(j.MONEY_MAX_ORDER))


if __name__ == "__main__":
    import unittest
    unittest.main()
