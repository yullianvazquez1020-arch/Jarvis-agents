"""Revisión del PR #11: correcciones 1-8. Sin red ni APIs de pago."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import AsyncMock, patch

import test_jarvis as base
j = base.j
import jarvis_chat_voice as cv
E = j._extensions


def answer(text):
    return N(content=[N(type="text", text=text)], stop_reason="end_turn")


class Base(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True)
        j.conversations.clear(); j._locks.clear()


class VoiceTurnLeavesNoAction(Base):
    """(1) A refused action from a voice note never reaches the next text turn."""
    def test_text_turn_sees_only_plain_text(self):
        tool = N(content=[N(type="tool_use", id="t1", name="add_expense", input={"amount": 250})], stop_reason="tool_use")
        with patch.object(j, "AI_READY", True), \
             patch.object(j, "_ai_call_scoped", new=AsyncMock(side_effect=[tool, answer("No ejecuté nada.")])):
            asyncio.run(j.run("tg:1", "¿Cómo anoto 250?", allowed_tools=j.READ_ONLY_TOOLS, read_only="voice"))
        self.assertEqual(j.conversations["tg:1"], [{"role": "user", "content": "¿Cómo anoto 250?"},
                                                   {"role": "assistant", "content": [{"type": "text", "text": "No ejecuté nada."}]}])
        seen = []
        async def full(history):
            seen.extend(history); return answer("ok")
        with patch.object(j, "AI_READY", True), patch.object(j, "_ai_call", new=full):
            asyncio.run(j.run("tg:1", "dale"))
        blocks = [b for m in seen if isinstance(m["content"], list) for b in m["content"]]
        self.assertTrue(all(isinstance(b, dict) and b["type"] == "text" for b in blocks))
        self.assertEqual(j._bload()["expenses"], [])

    def test_text_turns_still_keep_their_tools(self):
        tool = N(content=[N(type="tool_use", id="t1", name="overview", input={})], stop_reason="tool_use")
        with patch.object(j, "AI_READY", True), \
             patch.object(j, "_ai_call", new=AsyncMock(side_effect=[tool, answer("listo")])):
            asyncio.run(j.run("tg:2", "resumen"))
        self.assertEqual(len(j.conversations["tg:2"]), 4)            # unchanged behaviour for text

    def test_too_many_steps_keeps_previous_context(self):
        tool = N(content=[N(type="tool_use", id="t", name="overview", input={})], stop_reason="tool_use")
        j.conversations["tg:3"] = [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "hola"}]
        with patch.object(j, "AI_READY", True), patch.object(j, "_ai_call_scoped", new=AsyncMock(return_value=tool)):
            asyncio.run(j.run("tg:3", "¿qué hay?", allowed_tools=j.READ_ONLY_TOOLS, read_only="voice"))
        self.assertEqual(len(j.conversations["tg:3"]), 2)


class Transcription(unittest.TestCase):
    """(2) beam 1 by default, bounded; (3) only real names in the hint."""
    def test_beam(self):
        for value, want in (("", 1), ("x", 1), ("3", 3), ("0", 1), ("99", 5)):
            with patch.dict(os.environ, {"WHISPER_BEAM": value}):
                self.assertEqual(cv.whisper_beam(), want)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WHISPER_BEAM", None)
            self.assertEqual(cv.whisper_beam(), 1)

    def test_hint(self):
        self.assertNotIn("Coquí", cv.NAME_HINT); self.assertNotIn("Juey", cv.NAME_HINT)
        self.assertIn("ISLAFIX PRO LLC", cv.NAME_HINT)


class VoicesBounded(Base):
    """(4) answered/processed notes are capped; pending ones are never dropped; /dictado accepts answered."""
    def test_trim(self):
        d = {"voices": [{"id": i, "status": "pending" if i % 50 == 0 else "done"} for i in range(1, 451)]}
        cv._trim_voices(d)
        pending = [v["id"] for v in d["voices"] if v["status"] == "pending"]
        self.assertEqual(pending, [50, 100, 150, 200, 250, 300, 350, 400, 450])
        self.assertEqual(sum(v["status"] != "pending" for v in d["voices"]), cv.MAX_DONE_VOICES)
        self.assertEqual(d["voices"][-1]["id"], 450)

    def test_dictado_accepts_answered(self):
        with j._data_lock:
            d = E.load(); d["voices"] = [{"id": 1, "text": "hola", "status": "answered", "created": "x"}]; E.save(d)
        with patch.object(j, "_handle_tg", new=AsyncMock(return_value="ok")) as h, \
             patch.dict(os.environ, {"LOCAL_VOICE_ENABLED": "false"}):
            asyncio.run(E.command(1, "/dictado", "1"))
        h.assert_awaited_once_with(1, "hola")
        self.assertEqual(E.load()["voices"][0]["status"], "processing")


class BusyMessage(Base):
    """(5) a second note during a voice note gets the right message, not "produciendo un video"."""
    def test_message(self):
        sent = []
        async def tg(chat, text): sent.append(text)
        async def go():
            async with j._growth._video_lock:
                with cv._Busy():
                    await cv.handle_voice(j, 1, {"file_id": "f", "duration": 3}, None, None, None, None)
                await cv.handle_voice(j, 1, {"file_id": "f", "duration": 3}, None, None, None, None)
        with patch.object(j, "_tg_safe_send", new=tg):
            asyncio.run(go())
        self.assertIn("otra nota de voz", sent[0]); self.assertIn("produciendo un video", sent[1])
        self.assertEqual(cv._voice_busy["n"], 0)


class NoSpokenErrors(Base):
    """(6) the read-only voice path returns None on failure, so nothing is read aloud."""
    def test_failure_and_ai_off(self):
        with patch.object(j, "_tg_send", new=AsyncMock()) as send:
            with patch.object(j, "run", new=AsyncMock(side_effect=RuntimeError("x"))):
                self.assertIsNone(asyncio.run(j._handle_tg(1, "hola", read_only=True)))
            with patch.object(j, "run", new=AsyncMock(return_value=j.AI_OFF_MSG)):
                self.assertIsNone(asyncio.run(j._handle_tg(1, "hola", read_only=True)))
                self.assertEqual(asyncio.run(j._handle_tg(1, "hola")), j.AI_OFF_MSG)   # text path unchanged
        self.assertEqual(send.await_count, 3)                                   # the text still went out


class Diagnostics(Base):
    """(7) the restore claim only appears when restore is loaded."""
    def test_without_restore(self):
        j.TG_TOKEN = ""
        restore = j.phase_a_restore
        try:
            del j.phase_a_restore
            text = asyncio.run(j.diagnostics_text())
            self.assertIn("No sobrevive un deploy", text); self.assertNotIn("Recupera hasta 10", text)
        finally:
            j.phase_a_restore = restore
        self.assertIn("Recupera hasta 10", asyncio.run(j.diagnostics_text()))


class SessionsBounded(Base):
    """(8) at most MAX_SESSIONS chats in memory; a busy one is never dropped."""
    def test_cap(self):
        for i in range(60):
            j.conversations[f"s{i}"] = []
        busy = asyncio.Lock()
        async def hold():
            await busy.acquire()
        asyncio.run(hold())
        j._locks["s0"] = busy
        j._evict_sessions()
        self.assertEqual(len(j.conversations), j.MAX_SESSIONS - 1)
        self.assertIn("s0", j.conversations); self.assertNotIn("s1", j.conversations)


if __name__ == "__main__":
    unittest.main()
