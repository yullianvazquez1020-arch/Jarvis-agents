"""VOICE_MODEL: voice turns may use a faster model; everything else keeps CLAUDE_MODEL. Fictitious data only."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

import test_jarvis as base
j = base.j


def answer(text):
    return N(content=[N(type="text", text=text)], stop_reason="end_turn",
             usage=N(cache_read_input_tokens=0, cache_creation_input_tokens=0))


class VoiceModel(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True)
        j.conversations.clear(); j._locks.clear()
        self.models = []

        async def create(**kw):
            self.models.append(kw["model"])
            return answer("Listo.")
        p = patch.object(j.client.messages, "create", new=create); p.start(); self.addCleanup(p.stop)
        p = patch.object(j, "AI_READY", True); p.start(); self.addCleanup(p.stop)

    def turn(self, read_only, allowed=True, text="¿Cómo va el día de prueba?"):
        tools = j.READ_ONLY_TOOLS if allowed else None
        return asyncio.run(j.run("desk:prueba" if read_only else "tg:1", text, allowed_tools=tools,
                                 read_only=read_only))

    def test_desktop_and_voice_turns_use_voice_model(self):
        with patch.dict(os.environ, {"VOICE_MODEL": "claude-haiku-5-5"}):
            self.assertEqual(self.turn("escritorio"), "Listo.")
            self.turn("voice")
        self.assertEqual(self.models, ["claude-haiku-5-5", "claude-haiku-5-5"])

    def test_unset_keeps_main_model(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("VOICE_MODEL", None)
            self.turn("escritorio")
        self.assertEqual(self.models, [j.MODEL])

    def test_telegram_and_scoped_non_voice_never_use_it(self):
        # Telegram has its own model choice; VOICE_MODEL must not change it, nor a scoped non-voice channel.
        def both():
            j.conversations.clear(); self.turn(None, allowed=False); self.turn("otro_canal")
        os.environ.pop("VOICE_MODEL", None)
        both(); without = list(self.models); self.models.clear()
        with patch.dict(os.environ, {"VOICE_MODEL": "claude-voz-prueba-1"}):
            both()
        self.assertEqual(self.models, without)
        self.assertNotIn("claude-voz-prueba-1", self.models)

    def test_invalid_value_falls_back(self):
        for bad in ("bad model!", "x", "claude haiku", "../../etc", "A" * 90):
            with self.subTest(bad=bad), patch.dict(os.environ, {"VOICE_MODEL": bad}):
                self.models.clear(); j.conversations.clear()
                self.turn("escritorio")
                self.assertEqual(self.models, [j.MODEL])

    def test_flag_is_reset_after_the_turn_even_on_error(self):
        with patch.dict(os.environ, {"VOICE_MODEL": "claude-haiku-5-5"}):
            self.turn("escritorio")
            self.assertIsNone(j.voice_model())           # outside a turn: no voice model
            with patch.object(j, "_run_turn", side_effect=RuntimeError("falla de prueba")):
                with self.assertRaises(RuntimeError):
                    asyncio.run(j.run("desk:prueba", "hola", allowed_tools=j.READ_ONLY_TOOLS, read_only="escritorio"))
            self.assertIsNone(j.voice_model())

    def test_env_name_in_example_without_value(self):
        with open(Path(j.__file__).parent / ".env.example", encoding="utf-8") as f:
            lines = [l.strip() for l in f]
        self.assertIn("VOICE_MODEL=", lines)

    def test_explicit_desktop_model_reaches_provider_and_does_not_leak_to_telegram(self):
        with patch.dict(os.environ, {"VOICE_MODEL": "claude-voice-configured"}):
            self.turn(None, allowed=False, text="How is the other project?")
            telegram_model = self.models.pop()
            reply = asyncio.run(j.run("desk:explicit-test", "How is the test project?",
                allowed_tools=j.READ_ONLY_TOOLS, read_only="escritorio", model="claude-voice-explicit"))
            self.assertEqual(reply, "Listo.")
            self.assertIsNone(j.voice_model())
            self.turn(None, allowed=False, text="How is the other project?")
        self.assertEqual(self.models, ["claude-voice-explicit", telegram_model])

    def test_explicit_model_is_preserved_across_read_only_tool_round_trip(self):
        tool = N(content=[N(type="tool_use", id="read1", name="overview", input={})], stop_reason="tool_use")
        replies = iter([tool, answer("Read-only result.")])
        models = []

        async def create(**kw):
            models.append(kw["model"])
            return next(replies)

        with patch.object(j.client.messages, "create", new=create):
            reply = asyncio.run(j.run("desk:explicit-tools", "Show the current test overview",
                allowed_tools=j.READ_ONLY_TOOLS, read_only="escritorio", model="claude-voice-explicit"))
        self.assertEqual(reply, "Read-only result.")
        self.assertEqual(models, ["claude-voice-explicit", "claude-voice-explicit"])


if __name__ == "__main__":
    unittest.main()
