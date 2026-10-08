"""Local answers save API calls without intercepting actions or approvals."""
import asyncio
import datetime
import unittest
from unittest.mock import AsyncMock, patch
import jarvis_phase_a
import test_voice_conversation as voice
j = voice.j
answer = voice.answer


class LocalFirst(unittest.TestCase):
    def setUp(self):
        voice.VoiceConversation.setUp(self)
    def test_local_text_and_voice_never_call_provider(self):
        for scope in ({}, {"allowed_tools": j.READ_ONLY_TOOLS, "read_only": "voice"}):
            with patch.object(j, "AI_READY", False), \
                 patch.object(j, "_ai_call", new=AsyncMock()) as ai, \
                 patch.object(j, "_ai_call_scoped", new=AsyncMock()) as scoped:
                out = asyncio.run(j.run("tg:local", "Hola, Jarvis. ¿Cómo estás?", **scope))
            self.assertIn("Hola", out)
            ai.assert_not_awaited(); scoped.assert_not_awaited()
        self.assertEqual(len(j.phase_a_restore("tg:local")), 4)

    def test_full_match_keeps_actions_questions_and_approvals_out(self):
        now = datetime.datetime(2026, 10, 7, 22, 15)
        for text in ("hola anota 50 de gasolina", "gracias envia el correo", "hola compra bitcoin",
                     "dale", "si", "confirmar", "/confirmar 1 123456", "hola como estas y anota 20",
                     "que hora es y paga 100", "hola que debo pagar manana", "buenos dias recuerda llamar"):
            self.assertIsNone(jarvis_phase_a.smalltalk(text, now), text)

    def test_unknown_question_keeps_existing_provider_path(self):
        with patch.object(j, "AI_READY", True), \
             patch.object(j, "_ai_call", new=AsyncMock(return_value=answer("Consulta"))) as ai:
            self.assertEqual(asyncio.run(j.run("tg:local", "¿Cómo calculo materiales?")), "Consulta")
        ai.assert_awaited_once()

    def test_clock_uses_core_timezone(self):
        now = datetime.datetime(2026, 10, 7, 22, 15)
        with patch.object(j, "_now", return_value=now):
            self.assertIn("22:15", j.phase_a_smalltalk("¿Qué hora es?"))
            self.assertIn("07/10/2026", j.phase_a_smalltalk("¿Qué fecha es hoy?"))

    def test_desktop_restricted_scope_does_not_gain_local_bypass(self):
        with patch.object(j, "AI_READY", False):
            self.assertEqual(asyncio.run(j.run("desk:local", "hola", allowed_tools=set(), read_only="escritorio")), j.AI_OFF_MSG)
