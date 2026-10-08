"""Voz local por Telegram (jarvis_chat_voice). ffmpeg real; faster-whisper sustituido por un módulo falso en un
proceso hijo real; Telegram simulado. Nunca se llama a una API de pago."""
import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_jarvis as base
j = base.j
import jarvis_chat_voice as cv
E = j._extensions
REAL_HANDLE_TG = j._handle_tg
REAL_SPEAK_LOCAL = cv.speak_local

FAKE_WHISPER = '''
import json, os
class Seg:
    def __init__(self, t): self.text = t
class WhisperModel:
    def __init__(self, size, **kw):
        out = os.environ.get("FAKE_WHISPER_LOG")
        if out:
            json.dump({"size": size, "kw": kw, "env": sorted(os.environ)}, open(out, "w"))
    def transcribe(self, path, **kw):
        assert open(path, "rb").read(4) == b"RIFF"
        return iter([Seg(" anota 25 dolares "), Seg("de gasolina  ")]), None
'''


def make_ogg(seconds=2):
    tmp = Path(tempfile.mkdtemp()) / "n.ogg"
    subprocess.run([cv.ffmpeg_exe(), "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i",
                    f"sine=frequency=440:duration={seconds}", "-c:a", "libopus", str(tmp)], check=True)
    return tmp.read_bytes()


class FakeHTTP:
    posts = []
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass
    async def post(self, url, **kw):
        FakeHTTP.posts.append((url, kw))
        class R:
            status_code = 200
            def json(self): return {"ok": True}
        return R()


class ChatVoice(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True)
        self.models = tempfile.mkdtemp()
        self.fake_pkg = tempfile.mkdtemp()
        (Path(self.fake_pkg) / "faster_whisper.py").write_text(FAKE_WHISPER)
        self.log = Path(tempfile.mkdtemp()) / "child.json"
        self.env = patch.dict(os.environ, {"STT_AGENT_URL": "", "LOCAL_VOICE_ENABLED": "true",
                                           "WHISPER_MODEL_DIR": self.models, "FAKE_WHISPER_LOG": str(self.log),
                                           "PYTHONPATH": self.fake_pkg, "OPENAI_API_KEY": "sk-proj-should-not-matter"})
        self.env.start(); self.addCleanup(self.env.stop)
        p = patch.object(cv, "_SAFE_ENV", cv._SAFE_ENV + ("FAKE_WHISPER_LOG",)); p.start(); self.addCleanup(p.stop)
        self.sent = []
        async def tg_send(chat, text): self.sent.append(text)
        self.ogg = make_ogg()
        FakeHTTP.posts = []
        self.patches = [patch.object(j, "_tg_send", new=tg_send), patch.object(j, "_tg_file", new=AsyncMock(return_value=self.ogg)),
                        patch.object(j.httpx, "AsyncClient", FakeHTTP),
                        patch.object(cv, "speak_local", new=AsyncMock(side_effect=self.fake_speak)),
                        patch.object(j, "_handle_tg", new=AsyncMock(side_effect=AssertionError("dictation must stay pending")))]
        for p in self.patches:
            p.start(); self.addCleanup(p.stop)

    async def fake_speak(self, text):
        out = Path(tempfile.mkdtemp()) / "s.wav"
        subprocess.run([cv.ffmpeg_exe(), "-nostdin", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1",
                        "-ar", "22050", str(out)], check=True)
        return out.read_bytes()

    def voice(self, seconds=3):
        asyncio.run(E.voice_message(123, {"file_id": "f1", "duration": seconds, "mime_type": "audio/ogg"}))

    def voices(self):
        return E.load()["voices"]

    def test_transcribes_locally_and_dictation_stays_pending(self):
        self.voice()
        v = self.voices()
        self.assertEqual([(x["text"], x["status"]) for x in v], [("anota 25 dolares de gasolina", "pending")])
        self.assertIn("/dictado 1", self.sent[0]); self.assertIn("No ejecuté nada", self.sent[0])
        child = json.loads(self.log.read_text())
        self.assertEqual(child["size"], "tiny")
        self.assertEqual((child["kw"]["device"], child["kw"]["compute_type"], child["kw"]["cpu_threads"]), ("cpu", "int8", 1))
        for secret in ("AGENT_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "TELEGRAM_BOT_TOKEN"):
            self.assertNotIn(secret, child["env"])                          # the child gets no keys

    def test_reply_is_ogg_opus_and_cached(self):
        self.voice(); self.voice()
        voice_posts = [kw for url, kw in FakeHTTP.posts if url.endswith("/sendVoice")]
        self.assertEqual(len(voice_posts), 2)
        name, data, mime = voice_posts[0]["files"]["voice"]
        self.assertEqual((name, mime), ("respuesta.ogg", "audio/ogg"))
        self.assertTrue(data.startswith(b"OggS")); self.assertIn(b"OpusHead", data[:200])
        self.assertEqual(cv.speak_local.await_count, 1)                    # Piper loaded once, then cache
        self.assertTrue(all("api.telegram.org" in url for url, _ in FakeHTTP.posts))   # no other API called

    def test_reply_holds_video_lock_during_synthesis(self):
        async def checked(text):
            self.assertTrue(j._growth._video_lock.locked())
            return await self.fake_speak(text)
        with patch.object(cv, "speak_local", new=AsyncMock(side_effect=checked)):
            self.voice()
        self.assertFalse(j._growth._video_lock.locked())
        self.assertTrue(any(url.endswith("/sendVoice") for url, _ in FakeHTTP.posts))

    def test_synthesis_failure_releases_video_lock_and_keeps_dictation(self):
        with patch.object(cv, "speak_local", new=AsyncMock(side_effect=ValueError("test failure"))):
            self.voice()
        self.assertFalse(j._growth._video_lock.locked())
        self.assertEqual(self.voices()[0]["status"], "pending")
        self.assertIn("La respuesta escrita ya está arriba", self.sent[-1])

    def test_not_installed_message_no_paid_api(self):
        (Path(self.fake_pkg) / "faster_whisper.py").write_text(
            'raise ModuleNotFoundError("secret details", name="faster_whisper")')
        self.voice()
        self.assertIn("faster-whisper no está instalado", self.sent[-1]); self.assertIn("No usé una API de pago", self.sent[-1])
        self.assertEqual(self.sent[-1].count("No usé una API de pago"), 1)
        self.assertEqual(self.voices(), []); self.assertEqual(FakeHTTP.posts, [])

    def test_dependency_import_failure_not_misreported_as_missing_whisper(self):
        (Path(self.fake_pkg) / "faster_whisper.py").write_text(
            'raise ImportError("private-token-and-path")')
        with self.assertLogs(cv.log, level="WARNING") as logs:
            self.voice()
        self.assertIn("importar el transcriptor (ImportError)", self.sent[-1])
        self.assertNotIn("no está instalado", self.sent[-1])
        self.assertNotIn("private-token-and-path", str(logs.output) + str(self.sent))
        self.assertEqual(self.voices(), [])

    def test_model_failure_reports_stage_without_exception_contents(self):
        (Path(self.fake_pkg) / "faster_whisper.py").write_text('''
class WhisperModel:
    def __init__(self, *a, **kw):
        raise RuntimeError("https://private.example/?token=SECRET")
''')
        with self.assertLogs(cv.log, level="WARNING") as logs:
            self.voice()
        self.assertIn("descargar o cargar el modelo tiny (RuntimeError)", self.sent[-1])
        self.assertIn("stage=model kind=RuntimeError", str(logs.output))
        self.assertNotIn("SECRET", str(logs.output) + str(self.sent))
        self.assertEqual(self.voices(), []); self.assertEqual(FakeHTTP.posts, [])

    def test_lazy_transcription_failure_reports_stage(self):
        (Path(self.fake_pkg) / "faster_whisper.py").write_text('''
class WhisperModel:
    def __init__(self, *a, **kw): pass
    def transcribe(self, *a, **kw):
        def segments():
            raise ValueError("private audio contents")
            yield
        return segments(), None
''')
        self.voice()
        self.assertIn("transcribir el audio (ValueError)", self.sent[-1])
        self.assertNotIn("private audio contents", str(self.sent))
        self.assertEqual(self.voices(), [])

    def test_unknown_worker_exit_does_not_claim_memory_or_missing_package(self):
        with self.assertLogs(cv.log, level="WARNING") as logs:
            message = cv._worker_failure(-9, b"private traceback SECRET")
        self.assertIn("exit=-9", message)
        self.assertIn("no se confirmó la causa", message)
        self.assertNotIn("memoria", message)
        self.assertNotIn("SECRET", message + str(logs.output))

    def test_worker_diagnostics_are_allowlisted(self):
        for error in ({"stage": "SECRET", "kind": "SECRET"}, None, ["SECRET"],
                      {"stage": "model", "kind": "SECRET", "missing_whisper": True}):
            with self.subTest(error=error), self.assertLogs(cv.log, level="WARNING") as logs:
                message = cv._worker_failure(1, json.dumps({"error": error}).encode())
            self.assertNotIn("SECRET", message + str(logs.output))
            self.assertNotIn("no está instalado", message)

    def test_real_audio_decoder_accepts_whisper_metadata_errors(self):
        # Real dependency boundary: PyAV 19 raises TypeError here before inference.
        # A generated WAV avoids network access, model downloads and private audio.
        from faster_whisper.audio import decode_audio
        with tempfile.TemporaryDirectory() as tmp:
            wav = str(Path(tmp) / "decoder.wav")
            with wave.open(wav, "wb") as stream:
                stream.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                stream.writeframes(b"\x00\x00" * 1600)
            audio = decode_audio(wav)
        self.assertEqual(audio.shape, (1600,))

    def test_type_error_is_reported_without_raw_details(self):
        with self.assertLogs(cv.log, level="WARNING") as logs:
            message = cv._worker_failure(1, json.dumps({"error": {
                "stage": "transcribe", "kind": "TypeError", "message": "SECRET"}}).encode())
        self.assertIn("transcribir el audio (TypeError)", message)
        self.assertNotIn("SECRET", message + str(logs.output))

    def test_approved_dictation_speaks_actual_reply_without_rerunning_chat(self):
        self.voice()
        FakeHTTP.posts = []
        response = "Hola, jefe. ¿En qué te ayudo?"
        with patch.object(j, "_handle_tg", new=AsyncMock(return_value=response)) as handler:
            asyncio.run(E.command(123, "/dictado", "1"))
            handler.assert_awaited_once_with(123, "anota 25 dolares de gasolina")
            self.assertEqual(cv.speak_local.await_args.args[0], response)
            asyncio.run(E.command(123, "/dictado", "1"))
            self.assertEqual(handler.await_count, 1)
        self.assertEqual(len(FakeHTTP.posts), 1)
        self.assertTrue(FakeHTTP.posts[0][0].endswith("/sendVoice"))

    def test_chat_returns_response_only_after_text_delivery(self):
        with patch.object(j, "run", new=AsyncMock(return_value="Respuesta completa")) as chat:
            self.assertEqual(asyncio.run(REAL_HANDLE_TG(123, "hola")), "Respuesta completa")
            chat.assert_awaited_once_with("tg:123", "hola")
        with patch.object(j, "run", new=AsyncMock(return_value="Respuesta")), \
             patch.object(j, "_tg_send", new=AsyncMock(side_effect=RuntimeError("delivery failed"))):
            self.assertIsNone(asyncio.run(REAL_HANDLE_TG(123, "hola")))

    def test_spoken_reply_redacts_secrets_and_labels_truncation(self):
        key = "sk-ant-api03-" + "Z" * 40
        response = key + " " + "Hola, jefe. " * 400
        self.assertTrue(asyncio.run(cv.send_spoken_reply(j, 123, response)))
        spoken = cv.speak_local.await_args.args[0]
        self.assertNotIn(key, spoken)
        self.assertLessEqual(len(spoken), cv.MAX_CHARS)
        self.assertIn("Audio parcial", FakeHTTP.posts[-1][1]["data"]["caption"])

    def test_spoken_reply_disabled_or_busy_keeps_text(self):
        with patch.dict(os.environ, {"LOCAL_VOICE_ENABLED": "false"}):
            self.assertFalse(asyncio.run(cv.send_spoken_reply(j, 123, "Hola")))
        cv.speak_local.assert_not_awaited()
        async def busy():
            async with j._growth._video_lock:
                return await cv.send_spoken_reply(j, 123, "Hola")
        self.assertFalse(asyncio.run(busy()))
        cv.speak_local.assert_not_awaited()
        self.assertIn("respuesta escrita", self.sent[-1])

    def test_spoken_reply_synthesis_failure_does_not_repeat_actions(self):
        with patch.object(cv, "speak_local", new=AsyncMock(side_effect=ValueError("failure"))):
            self.assertFalse(asyncio.run(cv.send_spoken_reply(j, 123, "Hola")))
        self.assertFalse(j._growth._video_lock.locked())
        j._handle_tg.assert_not_awaited()
        self.assertEqual(FakeHTTP.posts, [])

    def test_spoken_reply_requires_telegram_confirmation(self):
        class RejectHTTP(FakeHTTP):
            async def post(self, url, **kw):
                class R:
                    status_code = 200
                    def json(self): return {"ok": False}
                return R()
        with patch.object(j.httpx, "AsyncClient", RejectHTTP):
            self.assertFalse(asyncio.run(cv.send_spoken_reply(j, 123, "Hola")))
        self.assertIn("No pude enviar su audio", self.sent[-1])
        j._handle_tg.assert_not_awaited()

    def test_piper_chunks_and_wav_join_preserve_full_response(self):
        import jarvis_local_tts
        response = "Una respuesta larga para leer en voz. " * 20
        chunks = cv.speech_chunks(response)
        self.assertEqual(" ".join(chunks), " ".join(response.split()))
        self.assertTrue(all(len(chunk) <= 400 for chunk in chunks))
        async def narration(plan, tmp):
            self.assertEqual([s["narration"] for s in plan["scenes"]], chunks)
            paths = []
            for i, scene in enumerate(plan["scenes"]):
                path = Path(tmp) / f"{i}.wav"
                with wave.open(str(path), "wb") as wav:
                    wav.setparams((1, 2, 22050, 0, "NONE", "not compressed"))
                    wav.writeframes(b"\x00\x00" * 22050)
                paths.append(str(path))
            return paths
        with patch.object(jarvis_local_tts, "local_narration", new=narration):
            # Call the real synthesis wrapper rather than the fixture's fake speaker.
            wav = asyncio.run(REAL_SPEAK_LOCAL(response))
        import io
        with wave.open(io.BytesIO(wav), "rb") as stream:
            self.assertEqual(stream.getnframes(), 22050 * len(chunks))

    def test_not_while_producing_video(self):
        async def go():
            async with j._growth._video_lock:
                await E.voice_message(123, {"file_id": "f1", "duration": 3})
        asyncio.run(go())
        self.assertIn("produciendo un video", self.sent[-1]); j._tg_file.assert_not_awaited()
        self.assertFalse(self.log.exists())                                 # Whisper never loaded

    def test_video_waits_for_voice(self):
        async def go():
            started = asyncio.Event()
            real = cv.transcribe_local
            async def slow(raw):
                started.set(); await asyncio.sleep(0.2); return await real(raw)
            with patch.object(cv, "transcribe_local", new=slow):
                t = asyncio.create_task(E.voice_message(123, {"file_id": "f1", "duration": 3}))
                await started.wait()
                busy = j._growth._video_lock.locked()
                await t
            return busy
        self.assertTrue(asyncio.run(go()))                                  # /producirvideo would see it busy

    def test_long_note_refused_before_download(self):
        self.voice(seconds=95)
        self.assertIn("95 s", self.sent[-1]); j._tg_file.assert_not_awaited()

    def test_off_by_default_and_external_stt_untouched(self):
        with patch.dict(os.environ, {"LOCAL_VOICE_ENABLED": ""}):
            self.voice()
        self.assertIn("Falta STT_AGENT_URL", self.sent[-1]); self.assertFalse(self.log.exists())
        with patch.dict(os.environ, {"STT_AGENT_URL": "https://stt.example.com"}):
            with patch.object(cv, "handle_voice", new=AsyncMock(side_effect=AssertionError("local used"))):
                self.voice()                                                # goes the existing way (fake HTTP)
        self.assertTrue(any("stt.example.com/transcribe" in url for url, _ in FakeHTTP.posts))

    def test_status_and_diagnostics(self):
        # Both installation states must be deterministic, regardless of this test environment.
        with patch("importlib.util.find_spec", return_value=None):
            self.assertIn("falta instalar faster-whisper", cv.status())
        with patch("importlib.util.find_spec", return_value=object()):
            self.assertIn("voz local activa", cv.status())
        with patch.dict(os.environ, {"LOCAL_VOICE_ENABLED": "false"}):
            self.assertIn("apagada", cv.status())
        j.TG_TOKEN = ""
        self.assertIn("Voz local:", asyncio.run(j.diagnostics_text()))

    def test_secrets_in_transcript_are_masked(self):
        key = "sk-ant-api03-" + "Z" * 40
        with patch.object(cv, "transcribe_local", new=AsyncMock(return_value=f"mi clave {key}")):
            self.voice()
        self.assertNotIn(key, json.dumps(self.voices())); self.assertNotIn(key, self.sent[0])


if __name__ == "__main__":
    unittest.main()
