"""Voice recovery: configured languages, bilingual questions and cancellable native intro.

Browser and hardware are doubles. These checks do not certify the owner's microphone,
speakers, Telegram delivery, or the memory needed by Whisper/Piper in production.
"""
import asyncio
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
import app as desktop_app
import jarvis_chat_voice as voice
import jarvis_local_tts


class TelegramLanguage(unittest.TestCase):
    def test_dictation_uses_configured_language_unless_explicitly_overridden(self):
        async def run():
            with patch.object(voice, "transcribe_local_detect", new=AsyncMock(return_value=("Hello", "en"))) as detect:
                self.assertEqual(await voice.transcribe_local(b"audio"), "Hello")
                detect.assert_awaited_once_with(b"audio", "")
                detect.reset_mock()
                await voice.transcribe_local(b"audio", "es")
                detect.assert_awaited_once_with(b"audio", "es")
        asyncio.run(run())

    def test_reply_language_matches_the_existing_recognition_default(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(voice.reply_language(), "en-GB")
        for value, expected in (("es", "es"), (" es-PR ", "es"), ("es_MX", "es"),
                                ("en", "en-GB"), ("EN_gb", "en-GB")):
            with self.subTest(value=value), patch.dict(os.environ, {"JARVIS_REPLY_LANGUAGE": value}):
                self.assertEqual(voice.reply_language(), expected)

    def test_explicit_and_default_english_use_the_same_male_piper_voice(self):
        seen = []

        async def narration(plan, destination):
            seen.append(plan["language"])
            output = Path(destination) / "speech.wav"
            with wave.open(str(output), "wb") as stream:
                stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                stream.writeframes(b"\0\0" * 160)
            return [str(output)]

        with patch.dict(os.environ, {"JARVIS_REPLY_LANGUAGE": "en-GB"}), \
                patch.object(jarvis_local_tts, "local_narration", new=narration):
            for language in (None, "en", "en-GB", "en_GB", "alan"):
                audio = asyncio.run(voice.speak_local("Hello, sir.", language))
                self.assertTrue(audio.startswith(b"RIFF"))
            asyncio.run(voice.speak_local("Buenas, señor.", "es-PR"))
        self.assertEqual(seen, ["alan"] * 5 + ["es"])

    def test_english_and_spanish_questions_get_exactly_one_read_only_reply(self):
        for text in ("Hello Jarvis", "Jarvis, how are you?", "What comes next?",
                     "Cuéntame del proyecto", "¿Cómo va el negocio?"):
            with self.subTest(text=text):
                data = {"voices": []}
                core = SimpleNamespace(
                    _data_lock=threading.RLock(), _tg_file=AsyncMock(return_value=b"audio"),
                    _redact_secrets=lambda value: (value, False),
                    _tg_send=AsyncMock(), _tg_safe_send=AsyncMock(),
                    _handle_tg=AsyncMock(return_value="Reply already delivered."))
                with patch.dict(os.environ, {"LOCAL_VOICE_ENABLED": "true", "LOCAL_VOICE_AUTO_REPLY": "true"}), \
                        patch.object(voice, "transcribe_local", new=AsyncMock(return_value=text)), \
                        patch.object(voice, "send_spoken_reply", new=AsyncMock(return_value=True)) as speak:
                    asyncio.run(voice.handle_voice(core, 123, {"file_id": "test", "duration": 2},
                        lambda: data, lambda *_: 1, lambda: "test-time", lambda _: None))
                core._handle_tg.assert_awaited_once_with(123, text, read_only=True)
                speak.assert_awaited_once_with(core, 123, "Reply already delivered.")
                self.assertEqual(data["voices"][0]["status"], "answered")

    def test_actions_and_approval_commands_remain_manual(self):
        for text in ("buy bitcoin", "send the message", "delete the note", "compra bitcoin",
                     "envía el mensaje", "/confirmar 1 123456", "How are you? /confirmar 1 123456"):
            self.assertFalse(voice.is_voice_query(text), text)


class NativeIntro(unittest.TestCase):
    def companion(self):
        app = desktop_app.Companion.__new__(desktop_app.Companion)
        app._voz_gen = 0
        app.prefs = {"rate": 1.0}
        app.tts = SimpleNamespace(synthesize=Mock(return_value=(b"audio", "audio/wav")))
        app._play_local = Mock(return_value=True)
        return app

    def run_intro(self, app, cfg=None, delay=None):
        process = Mock()
        process.poll.return_value = None
        clock = [0.0]

        def sleep(seconds):
            clock[0] += seconds
            if delay:
                delay(app)

        with patch.object(desktop_app, "local_player", return_value=["afplay"]), \
                patch.object(desktop_app, "startup_sound", return_value=(Path("intro.wav"), "audio/wav")), \
                patch.object(desktop_app.subprocess, "Popen", return_value=process) as popen, \
                patch.object(desktop_app.time, "sleep", side_effect=sleep), \
                patch.object(desktop_app.time, "monotonic", side_effect=lambda: clock[0]), \
                patch.object(desktop_app, "_wav_secs", return_value=0.5):
            desktop_app.native_intro(app, cfg or {})
        return process, popen, clock[0]

    def test_stop_during_synthesis_never_enqueues_the_late_greeting(self):
        app = self.companion()

        def synthesize(*args, **kwargs):
            app.stop_local_audio()
            return b"late greeting", "audio/wav"

        app.tts.synthesize.side_effect = synthesize
        process, _, _ = self.run_intro(app)
        app._play_local.assert_not_called()
        self.assertGreaterEqual(process.terminate.call_count, 1)
        self.assertIsNone(app._intro_process)
        self.assertEqual(app._intro_until, 0)

    def test_stop_before_synthesis_cleans_up_the_intro(self):
        app = self.companion()
        process, _, _ = self.run_intro(app, delay=lambda c: c.stop_local_audio())
        app.tts.synthesize.assert_not_called()
        app._play_local.assert_not_called()
        self.assertGreaterEqual(process.terminate.call_count, 1)
        self.assertIsNone(app._intro_process)

    def test_normal_greeting_keeps_its_generation_and_stops_music(self):
        app = self.companion()
        process, popen, elapsed = self.run_intro(app)
        app.tts.synthesize.assert_called_once_with(desktop_app.GREETING, rate=1.0)
        app._play_local.assert_called_once_with(b"audio", 0)
        self.assertEqual(popen.call_count, 1)
        process.terminate.assert_called_once()
        self.assertLessEqual(elapsed, 15.0)
        self.assertEqual(app._intro_until, 0)

    def test_playback_disabled_does_not_start_music_or_greeting(self):
        app = self.companion()
        _, popen, _ = self.run_intro(app, {"VOICE_SERVER_PLAYBACK": "false"})
        popen.assert_not_called()
        app.tts.synthesize.assert_not_called()
        app._play_local.assert_not_called()


if __name__ == "__main__":
    unittest.main()
