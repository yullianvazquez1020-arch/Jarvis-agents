"""Automatic voice queries are read-only; restored memory never replays tools."""
import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, patch
import test_jarvis as base
j = base.j

def answer(text):
    return N(content=[N(type="text", text=text)], stop_reason="end_turn")

class VoiceConversation(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True)
        j.conversations.clear(); j._locks.clear()

    def test_read_only_handler_scopes_tools_and_sends_text_first(self):
        with patch.object(j, "run", new=AsyncMock(return_value="Respuesta")) as run, \
             patch.object(j, "_tg_send", new=AsyncMock()) as send:
            self.assertEqual(asyncio.run(j._handle_tg(123, "Hola", read_only=True)), "Respuesta")
        self.assertEqual(run.await_args.kwargs["read_only"], "voice")
        self.assertEqual(run.await_args.kwargs["allowed_tools"], j.READ_ONLY_TOOLS)
        send.assert_awaited_once_with(123, "Respuesta")

    def test_model_cannot_mutate_even_when_question_contains_an_action(self):
        tool = N(content=[N(type="tool_use", id="t1", name="add_income", input={"amount": 99})], stop_reason="tool_use")
        with patch.object(j, "AI_READY", True), \
             patch.object(j, "_ai_call_scoped", new=AsyncMock(side_effect=[tool, answer("No ejecuté acciones.")])) as model, \
             patch.dict(j.HANDLERS, {"add_income": lambda **kw: self.fail("write tool ran")}):
            result = asyncio.run(j.run("tg:123", "¿Qué pasa si anotas 99?", allowed_tools=j.READ_ONLY_TOOLS, read_only="voice"))
        self.assertEqual(result, "No ejecuté acciones.")
        self.assertEqual(j._bload()["income"], [])
        seen_tools = {t["name"] for t in model.await_args_list[0].args[1]}
        self.assertNotIn("add_income", seen_tools)

    def test_read_tool_accidental_write_is_blocked_at_storage(self):
        tool = N(content=[N(type="tool_use", id="t2", name="overview", input={})], stop_reason="tool_use")
        with patch.object(j, "AI_READY", True), \
             patch.object(j, "_ai_call_scoped", new=AsyncMock(side_effect=[tool, answer("Solo lectura.")])), \
             patch.dict(j.HANDLERS, {"overview": lambda: j.add_income(99)}):
            asyncio.run(j.run("tg:123", "¿Cómo está todo?", allowed_tools=j.READ_ONLY_TOOLS, read_only="voice"))
        self.assertEqual(j._bload()["income"], [])
        self.assertIsNone(j._WRITE_BLOCK.get())

    def test_memory_restores_after_restart_without_replaying_actions(self):
        with patch.object(j, "AI_READY", True), patch.object(j, "_ai_call", new=AsyncMock(return_value=answer("Tu proyecto es IslaFix."))):
            asyncio.run(j.run("tg:123", "Mi proyecto se llama IslaFix"))
        j.conversations.clear(); j._locks.clear()
        observed = []
        async def model(history):
            observed.extend(history)
            return answer("IslaFix")
        with patch.object(j, "AI_READY", True), patch.object(j, "_ai_call", new=model), \
             patch.object(j, "run_tool", new=AsyncMock(side_effect=AssertionError("no replay"))):
            asyncio.run(j.run("tg:123", "¿Cómo se llama mi proyecto?"))
        self.assertEqual([m["role"] for m in observed], ["user", "assistant", "user"])
        self.assertIn("IslaFix", observed[0]["content"])

    def test_voice_turn_is_persisted_and_restored(self):
        with patch.object(j, "AI_READY", True), patch.object(j, "_ai_call_scoped", new=AsyncMock(return_value=answer("Hola"))):
            asyncio.run(j.run("tg:123", "Hola Jarvis", allowed_tools=j.READ_ONLY_TOOLS, read_only="voice"))
        j.conversations.clear()
        self.assertEqual([x["role"] for x in j.phase_a_restore("tg:123")], ["user", "assistant"])

    def test_memory_isolated_redacted_bounded_and_skips_incomplete_turns(self):
        secret = "sk-ant-api03-" + "Z" * 40
        hist = [{"session": "tg:other", "role": "user", "text": "private"},
                {"session": "tg:other", "role": "assistant", "text": "private"}]
        for i in range(15):
            hist.extend([{"session": "tg:123", "role": "user", "text": f"m{i} {secret}"},
                         {"session": "tg:123", "role": "assistant", "text": "reply"}])
        hist += [{"session": "tg:123", "role": "tool_use", "text": "ignore"},
                 {"session": "tg:123", "role": "user", "text": "unfinished"}]
        j.kv_set("jarvis:history", hist)
        restored = j.phase_a_restore("tg:123")
        self.assertEqual(len(restored), 20)
        encoded = json.dumps(restored)
        for wrong in ("private", "unfinished", "tool_use", secret):
            self.assertNotIn(wrong, encoded)
        self.assertEqual(j.phase_a_restore("tg:missing"), [])

    def test_session_ids_with_common_prefix_do_not_leak_memory(self):
        session = "a" * 40 + "first"
        j.phase_a_remember(session, "user", "first private")
        j.phase_a_remember(session, "assistant", "first reply")
        self.assertEqual(j.phase_a_restore("a" * 40 + "second"), [])
        self.assertEqual(len(j.phase_a_restore(session)), 2)
        self.assertEqual(j.phase_a_restore("a" * 129), [])

    def test_restore_failure_preserves_chat_availability(self):
        with patch.object(j, "phase_a_restore", side_effect=RuntimeError("storage down")), \
             patch.object(j, "AI_READY", True), patch.object(j, "_ai_call", new=AsyncMock(return_value=answer("Hola"))):
            self.assertEqual(asyncio.run(j.run("tg:123", "Explica como calcular materiales")), "Hola")

    def test_failed_turn_write_never_pairs_old_question_with_new_answer(self):
        j.phase_a_remember("tg:123", "user", "old unfinished question")
        before = j.kv_get("jarvis:history", [])
        with patch.object(j, "kv_set", side_effect=RuntimeError("temporary outage")) as save:
            asyncio.run(j._phase_a_remember_turn("tg:123", "new question", "new answer"))
        save.assert_called_once()
        self.assertEqual(j.kv_get("jarvis:history", []), before)
        self.assertEqual(j.phase_a_restore("tg:123"), [])
        asyncio.run(j._phase_a_remember_turn("tg:123", "new question", "new answer"))
        self.assertEqual([m["content"] for m in j.phase_a_restore("tg:123")], ["new question", "new answer"])

    def test_concurrent_turns_remain_paired_and_bounded(self):
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda i: j.phase_a_remember_turn("tg:123", f"q{i}", f"a{i}"), range(30)))
        hist = j.kv_get("jarvis:history", [])
        self.assertEqual(len(hist), 40)
        for user, assistant in zip(hist[::2], hist[1::2]):
            self.assertEqual((user["role"], assistant["role"]), ("user", "assistant"))
            self.assertEqual(user["text"][1:], assistant["text"][1:])

    def test_secret_crossing_text_limit_is_redacted_before_truncation(self):
        secret = "sk-ant-api03-" + "Z" * 40
        j.phase_a_remember_turn("tg:123", "x" * 1990 + " " + secret, "ok")
        text = j.kv_get("jarvis:history", [])[0]["text"]
        self.assertNotIn("sk-ant-", text)
        self.assertLessEqual(len(text), 2000)

    def test_read_only_error_does_not_claim_actions_were_saved(self):
        with patch.object(j, "run", new=AsyncMock(side_effect=RuntimeError("test"))), \
             patch.object(j, "_tg_send", new=AsyncMock()) as send:
            reply = asyncio.run(j._handle_tg(123, "Hola", read_only=True))
        self.assertIsNone(reply)  # Errors are sent as text and must not be spoken.
        send.assert_awaited_once()
        self.assertEqual(send.await_args.args[0], 123)
        message = send.await_args.args[1]
        self.assertIn("No ejecuté acciones", message)
        self.assertNotIn("pudieron haberse guardado", message)
