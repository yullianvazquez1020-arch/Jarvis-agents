"""Mecánica del banco de voz (scripts/bench_voice.py) con un doble de Piper: NO mide Piper real.
Comprueba que la memoria conjunta incluye al proceso hijo, que no se llama a Telegram y que en Render pide confirmación."""
import asyncio
import io
import json
import os
import sys
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import bench_voice  # noqa: E402
import jarvis_chat_voice as cv  # noqa: E402
import jarvis_local_tts as tts  # noqa: E402


def wav_bytes(seconds=0.5, rate=22050):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b"\0\0" * int(seconds * rate))
    return buf.getvalue()


async def fake_speak(text):
    """Doble: un proceso hijo que ocupa ~60 MB un momento, como haría el de Piper (sin modelo ni red)."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-c", "import time;a=bytearray(60*1024*1024);a[::4096]=b'x'*len(a[::4096]);time.sleep(0.3)")
    await proc.wait()
    import logging
    logging.getLogger("jarvis_local_tts").warning("Local voice ready: scenes=%s peak_memory_mb=%s",
                                                  len(cv.speech_chunks(text)), 77)
    return wav_bytes()


async def fake_opus(wav):
    return b"OggS" + b"\0" * 100


class BenchVoice(unittest.TestCase):
    def run_bench(self, *args):
        with patch.object(cv, "speak_local", fake_speak), patch.object(cv, "to_opus", fake_opus), \
                patch.object(tts, "ensure_model", lambda root: root), \
                patch("httpx.AsyncClient", side_effect=AssertionError("no Telegram")), \
                patch.dict(os.environ, {"RENDER": ""}):
            out = io.StringIO()
            with patch("sys.stdout", out):
                code = bench_voice.main(list(args))
        return code, json.loads(out.getvalue())

    def test_joint_memory_includes_child_and_both_modes_run(self):
        code, res = self.run_bench("--modo", "ambos", "-n", "3")
        self.assertEqual(code, 0)
        self.assertEqual(res["escenas_8"][0]["escenas"], 8)
        self.assertEqual(len(res["respuestas_consecutivas"]), 3)
        for row in res["escenas_8"] + res["respuestas_consecutivas"]:
            self.assertGreaterEqual(row["memoria_pico"]["hijos_mb"], 50)        # el hijo se ve en la suma
            self.assertGreaterEqual(row["memoria_pico"]["conjunta_mb"], row["memoria_pico"]["padre_mb"] + 50)
            self.assertEqual(row["piper_pico_mb"], 77)
        self.assertEqual(res["entorno"]["donde"], "local")
        self.assertEqual(res["entorno"]["telegram"], "no se llamó")
        self.assertLessEqual(max(len(s) for s in cv.speech_chunks(bench_voice.texto(cv.MAX_CHARS))), 400)

    def test_render_requires_confirmation(self):
        with patch.dict(os.environ, {"RENDER": "true"}), patch("sys.stderr", io.StringIO()):
            self.assertEqual(bench_voice.main(["--modo", "respuestas", "-n", "1"]), 2)

    def test_fictitious_text_fits_limits(self):
        self.assertEqual(len(cv.speech_chunks(bench_voice.texto(cv.MAX_CHARS))), 8)
        self.assertLessEqual(len(bench_voice.texto(cv.MAX_SPOKEN_REPLY)), cv.MAX_SPOKEN_REPLY)


if __name__ == "__main__":
    unittest.main()
