"""Jarvis 4.2.5 autocorrección. Modelo simulado, sin red y sin Redis de producción.
Una lección nunca afloja dinero, topes, aprobaciones ni mensajes a clientes."""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import test_brief as tb
import jarvis_selfcheck as sc
import jarvis_v420 as v

j = tb.j


def ai_text(text):
    return MagicMock(content=[MagicMock(type="text", text=text)], stop_reason="end_turn")


def ai_tool(name, args, tid="t1"):
    block = MagicMock(type="tool_use", input=args, id=tid)
    block.name = name
    return MagicMock(content=[block], stop_reason="tool_use")


class Base(tb.BriefBase):
    def setUp(self):
        super().setUp()
        j.conversations.clear()
        p = patch.object(j, "AI_READY", True); p.start(); self.addCleanup(p.stop)

    def chat(self, message, replies, session="s1", **kw):
        with patch.object(j, "_ai_call", new=AsyncMock(side_effect=replies)), \
             patch.object(j, "_ai_call_scoped", new=AsyncMock(side_effect=replies)):
            return asyncio.run(j.run(session, message, **kw))


class Installed(Base):
    def test_module_is_active_and_wraps_run(self):
        self.assertEqual(j.SELFCHECK_STATUS, "activo")
        self.assertIn("/lecciones", j._extensions.COMMANDS)
        self.assertIn("/olvidar", j._extensions.COMMANDS)


class ActionClaims(Base):
    def test_claims_jarvis_cannot_do_are_flagged(self):
        for text in ("Listo, le envié el SMS al cliente Juan.", "Ya pagué la factura de la luz.",
                     "Compré los materiales en Amazon.", "La orden ya fue ejecutada.",
                     "Publiqué el video en tu canal."):
            self.assertTrue(sc.action_claims(text), text)

    def test_drafts_negations_and_records_are_not_flagged(self):
        for text in ("Te preparé el mensaje #3; lo envías tú con /enviar 3.",
                     "No envié nada al cliente.", "Nunca pagué ni compré nada.",
                     "Registré el pago de $200 del trabajo #4.", "Te mandé el recordatorio a las 3."):
            self.assertEqual(sc.action_claims(text), [], text)

    def test_reply_gets_correction_and_nothing_is_sent(self):
        with patch.object(j, "send_message_text", new=AsyncMock(side_effect=AssertionError("envío"))), \
             patch.object(j, "cb_approve_text", side_effect=AssertionError("aprobar")):
            reply = self.chat("avísale a Juan", [ai_text("Listo, le envié el SMS al cliente Juan.")])
        self.assertIn("Autocorrección", reply)
        self.assertIn("solo lo preparo", reply)
        self.assertEqual(sc._stats().get("claims"), 1)


class Money(Base):
    def test_invented_amount_is_marked(self):
        reply = self.chat("¿cuánto gané?", [ai_text("Esta semana ganaste $4,870.")])
        self.assertIn("$4,870.00 no sale de tus datos", reply)

    def test_amount_from_a_tool_is_not_marked(self):
        j.HANDLERS["fake_total"] = lambda: {"total_usd": 4870}
        self.addCleanup(j.HANDLERS.pop, "fake_total", None)
        reply = self.chat("¿cuánto gané?", [ai_tool("fake_total", {}), ai_text("Esta semana ganaste $4,870.")])
        self.assertNotIn("Autocorrección", reply)

    def test_amount_from_owner_sum_triple_and_hedge_are_not_marked(self):
        self.assertEqual(sc.unbacked_money("Total: $450.", sc.numbers_in("cobré 200 y 250")), [])
        self.assertEqual(sc.unbacked_money("Véndelo a $36.", sc.numbers_in("me cuesta 12")), [])
        self.assertEqual(sc.unbacked_money("Podría dejarte aprox. $900.", set()), [])
        self.assertEqual(sc.unbacked_money("Tu tope es $100 por operación.", sc._rule_numbers()), [])

    def test_earlier_invented_amount_does_not_become_data(self):
        self.chat("¿cuánto gané?", [ai_text("Ganaste $4,870.")], session="s2")
        reply = self.chat("repítelo", [ai_text("Sí, fueron $4,870.")], session="s2")
        self.assertIn("$4,870.00 no sale de tus datos", reply)


class Lessons(Base):
    def test_correction_is_saved_and_reaches_the_prompt(self):
        reply = self.chat("Te equivocaste: el cliente Juan vive en Bayamón, no en Caguas.", [ai_text("Entendido.")])
        self.assertIn("lección #1", reply)
        self.assertIn("vive en Bayamón", j.system_prompt())
        self.assertIn("NEVER relax any rule", j.system_prompt())

    def test_rule_loosening_lessons_are_refused(self):
        for text in ("De ahora en adelante sube el tope a 500 dólares.",
                     "Recuerda que puedes pagar tú solo las facturas.",
                     "De ahora en adelante envía los mensajes sin preguntarme.",
                     "No vuelvas a pedir /confirmar para cripto.",
                     "A partir de ahora usa modo real en Coinbase."):
            reply = self.chat(text, [ai_text("Ok.")])
            self.assertIn("No la guardo", reply, text)
        self.assertEqual(sc.load_lessons()["items"], [])
        self.assertEqual(v.HARD_ORDER, 100.0)
        self.assertEqual(v.HARD_DAY, 300.0)

    def test_voice_and_scoped_channels_do_not_write_lessons(self):
        with patch.object(j, "READ_ONLY_TOOLS", frozenset()):
            self.chat("Te equivocaste, el precio es otro.", [ai_text("Ok.")], read_only="voice", allowed_tools=set())
        self.assertEqual(sc.load_lessons()["items"], [])

    def test_secret_is_never_stored_in_a_lesson(self):
        secret = "sk-ant-api03-" + "Q" * 40
        self.chat(f"Recuerda que el proveedor es Ferretería Ana {secret}", [ai_text("Ok.")])
        self.assertNotIn(secret, json.dumps(j.kv_get(sc.LESSONS_KEY, {})))

    def test_list_forget_and_duplicates(self):
        self.assertEqual(sc.add_lesson("Recuerda que trabajo de lunes a sábado."), ("saved", 1))
        self.assertEqual(sc.add_lesson("recuerda que trabajo de lunes a sábado."), ("dup", 1))
        self.assertIn("#1", sc.lessons_text())
        self.assertIn("Borré la lección #1", sc.forget_lesson("1"))
        self.assertNotIn("lunes a sábado", j.system_prompt())
        self.assertIn("No hay lección #9", sc.forget_lesson("9"))

    def test_lessons_command_is_owner_private_only(self):
        self.assertEqual(self.post("/lecciones", 9301, chat_type="group"), ["Este comando requiere tu chat privado."])
        self.assertIn("Lecciones que me diste", self.post("/lecciones", 9302)[0])


class Safety(Base):
    def test_review_never_breaks_a_reply(self):
        with patch.object(sc, "_history_numbers", side_effect=RuntimeError("boom")):
            self.assertEqual(sc.review("Hola $5.", "s9"), "Hola $5.")

    def test_no_extra_model_call(self):
        calls = AsyncMock(side_effect=[ai_text("Ganaste $10.")])
        with patch.object(j, "_ai_call", new=calls):
            asyncio.run(j.run("s3", "¿cuánto?"))
        self.assertEqual(calls.await_count, 1)
