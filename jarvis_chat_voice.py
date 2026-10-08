# jarvis_chat_voice.py
# Conversación por voz en Telegram. No narra videos y no llama APIs de pago.
# Si falla la voz, el texto igual sale. El dictado no se ejecuta solo.
#
# Revisado (sobre 40b911c):
#  * Apagado por defecto: LOCAL_VOICE_ENABLED=true lo prende, después de probar una nota corta (512 MB es justo).
#  * Ya no se niega si OPENAI_API_KEY está puesta: este camino nunca la usa, así que no hace falta revisarla.
#  * ffmpeg sale de imageio-ffmpeg (ya está en requirements, y es el que usan los videos); Render no trae
#    ffmpeg del sistema.
#  * Comparte el candado de /producirvideo: no carga Whisper mientras se produce un video, y viceversa.
#  * Notas de hasta 60 s (se revisa la duración antes de descargar) y tiempo límite en cada paso.
#  * Los procesos hijos no reciben las llaves de Jarvis (mismo criterio que jarvis_local_tts).
#  * Telegram solo acepta notas de voz en OGG/Opus (o MP3/M4A): la respuesta se convierte a Opus. La frase
#    fija se genera una sola vez y queda en caché, así no se carga Piper en cada nota.
#  * Cada transcripción deja en el log la memoria máxima del proceso, para medir los 512 MB reales en Render.

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import shutil
import sys
import tempfile
import wave
from pathlib import Path

MAX_AUDIO = 1_500_000
MAX_SECONDS = 60
MAX_CHARS = 3200
WHISPER_TIMEOUT = 90
FFMPEG_TIMEOUT = 30
REPLY_TEXT = "Recibí tu nota. Revisa el texto antes de procesarla."
log = logging.getLogger(__name__)

# Variables que sí pasan a los procesos hijos (sin AGENT_API_KEY, TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY, etc.)
_SAFE_ENV = ("PATH", "LD_LIBRARY_PATH", "PYTHONPATH", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR",
             "HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "HOME", "TMPDIR")

_WORKER = r"""
import json, resource, sys
stage = "import"
try:
    req = json.loads(sys.stdin.read(4000))
    from faster_whisper import WhisperModel
    stage = "model"
    m = WhisperModel("tiny", device="cpu", compute_type="int8", cpu_threads=1, num_workers=1,
                     download_root=req["models"])
    stage = "transcribe"
    segs, _ = m.transcribe(req["wav"], language="es", vad_filter=True, beam_size=1)
    text = " ".join(s.text.strip() for s in segs)
    print(json.dumps({"text": text, "peak_memory_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)}))
except Exception as exc:
    # Never serialize exception messages, tracebacks, paths, URLs or credentials.
    kind = type(exc).__name__
    allowed = {"ImportError", "ModuleNotFoundError", "MemoryError", "OSError", "RuntimeError",
               "ValueError", "TypeError", "PermissionError", "FileNotFoundError", "HfHubHTTPError",
               "LocalEntryNotFoundError", "ConnectError", "ConnectTimeout", "ReadTimeout"}
    error = {"stage": stage, "kind": kind if kind in allowed else "Exception",
             "missing_whisper": isinstance(exc, ModuleNotFoundError) and exc.name == "faster_whisper"}
    print(json.dumps({"error": error}), flush=True)
    sys.exit(1)
"""

_ERROR_STAGES = {"import": "importar el transcriptor", "model": "descargar o cargar el modelo tiny",
                 "transcribe": "transcribir el audio"}
_ERROR_KINDS = {"ImportError", "ModuleNotFoundError", "MemoryError", "OSError", "RuntimeError",
                "ValueError", "TypeError", "PermissionError", "FileNotFoundError", "HfHubHTTPError",
                "LocalEntryNotFoundError", "ConnectError", "ConnectTimeout", "ReadTimeout", "Exception"}


def _worker_failure(code: int, out: bytes) -> str:
    """Only allowlisted diagnostics cross the worker boundary; stderr remains private."""
    try:
        error = json.loads(out.decode().strip().splitlines()[-1])["error"]
        stage = error["stage"] if error["stage"] in _ERROR_STAGES else "unknown"
        kind = error["kind"] if error["kind"] in _ERROR_KINDS else "Exception"
        missing = stage == "import" and kind == "ModuleNotFoundError" and error.get("missing_whisper") is True
    except (ValueError, UnicodeError, IndexError, KeyError, TypeError):
        stage, kind, missing = "unknown", "Exception", False
    log.warning("local whisper worker failed: exit=%s stage=%s kind=%s", code, stage, kind)
    if missing:
        return "faster-whisper no está instalado"
    if stage in _ERROR_STAGES:
        return f"falló al {_ERROR_STAGES[stage]} ({kind}); revisa los registros de Render"
    return f"el transcriptor terminó sin diagnóstico (exit={code}); no se confirmó la causa"


def enabled() -> bool:
    return os.getenv("LOCAL_VOICE_ENABLED", "false").strip().lower() in ("true", "1", "yes")


def model_dir() -> Path:
    return Path(os.getenv("WHISPER_MODEL_DIR", str(Path(__file__).parent / "whisper_models")))


def _child_env() -> dict:
    env = {k: v for k, v in os.environ.items() if k in _SAFE_ENV}
    env.update(OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1", HF_HUB_DISABLE_TELEMETRY="1",
               HF_HOME=str(model_dir() / "hf"))
    return env


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        exe = shutil.which("ffmpeg")
        if not exe:
            raise ValueError("no encuentro ffmpeg (imageio-ffmpeg)") from None
        return exe


async def _run(args, timeout, stdin=None, env=None):
    proc = await asyncio.create_subprocess_exec(*args, stdin=asyncio.subprocess.PIPE if stdin is not None else None,
                                                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                                                env=env)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(stdin), timeout=timeout)
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        raise
    return proc.returncode, out


async def _ffmpeg(args, timeout=FFMPEG_TIMEOUT) -> int:
    try:
        code, _ = await _run([ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error", "-y"] + args, timeout,
                             env=_child_env())
    except asyncio.TimeoutError:
        raise ValueError("la conversión de audio tardó demasiado") from None
    return code


async def transcribe_local(raw: bytes) -> str:
    if not raw or len(raw) > MAX_AUDIO:
        raise ValueError("audio vacío o mayor de 1.5 MB")
    with tempfile.TemporaryDirectory(prefix="jarvis-voz-") as tmp:
        src = Path(tmp) / "nota.ogg"
        wav = Path(tmp) / "nota.wav"
        src.write_bytes(raw)
        if await _ffmpeg(["-i", str(src), "-t", str(MAX_SECONDS), "-ac", "1", "-ar", "16000", str(wav)]) != 0:
            raise ValueError("no pude convertir el audio")
        model_dir().mkdir(parents=True, exist_ok=True)
        try:
            code, out = await _run([sys.executable, "-c", _WORKER], WHISPER_TIMEOUT,
                                   stdin=json.dumps({"wav": str(wav), "models": str(model_dir())}).encode(),
                                   env=_child_env())
        except asyncio.TimeoutError:
            raise ValueError("la transcripción local tardó demasiado") from None
        if code:
            raise ValueError(_worker_failure(code, out)) from None
        try:
            result = json.loads(out.decode().strip().splitlines()[-1])
        except (ValueError, IndexError):
            raise ValueError("respuesta inválida del transcriptor local") from None
        log.warning("Local whisper ready: peak_memory_mb=%s", result.get("peak_memory_mb"))
        text = " ".join(str(result.get("text", "")).split())
        if not text:
            raise ValueError("no entendí el audio")
        return text[:4000]


async def speak_local(text: str) -> bytes:
    """WAV con la voz local (Piper, jarvis_local_tts)."""
    text = " ".join(text.split())[:MAX_CHARS]
    if not text:
        raise ValueError("no hay texto para hablar")
    import jarvis_local_tts
    with tempfile.TemporaryDirectory() as tmp:
        chunks = speech_chunks(text)
        paths = await jarvis_local_tts.local_narration(
            {"language": "es", "scenes": [{"narration": chunk} for chunk in chunks]}, tmp)
        merged = io.BytesIO()
        with wave.open(merged, "wb") as dst:
            params = None
            for path in paths:
                with wave.open(str(path), "rb") as src:
                    current = (src.getnchannels(), src.getsampwidth(), src.getframerate())
                    if params is None:
                        params = current
                        dst.setnchannels(params[0]); dst.setsampwidth(params[1]); dst.setframerate(params[2])
                    elif current != params:
                        raise ValueError("formatos de voz local incompatibles")
                    dst.writeframes(src.readframes(src.getnframes()))
        return merged.getvalue()


def speech_chunks(text: str) -> list[str]:
    """Piper accepts up to eight scenes, each at most 400 characters."""
    text = " ".join(text.split())[:MAX_CHARS]
    chunks = []
    while text:
        cut = min(400, len(text))
        if cut < len(text):
            boundary = text.rfind(" ", 0, cut + 1)
            if boundary > 0:
                cut = boundary
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
        if len(chunks) == 8:
            break
    return chunks


async def send_spoken_reply(core, chat_id, text: str) -> bool:
    """Speak only an already-sent response; never rerun the chat or its tools."""
    if not enabled():
        return False
    text = core._redact_secrets(str(text))[0]
    normalized = " ".join(text.split())
    chunks = speech_chunks(normalized)
    if not chunks:
        return False
    spoken = " ".join(chunks)
    caption = "Respuesta con voz femenina local."
    if spoken != normalized:
        caption = "Audio parcial por límite de longitud; la respuesta completa está en el texto."
    try:
        lock = _heavy_lock(core)
        if lock is not None:
            if lock.locked():
                raise RuntimeError("video o voz en curso")
            async with lock:
                ogg = await to_opus(await speak_local(spoken))
        else:
            ogg = await to_opus(await speak_local(spoken))
        async with core.httpx.AsyncClient(timeout=60) as hc:
            r = await hc.post(f"https://api.telegram.org/bot{core.TG_TOKEN}/sendVoice",
                              data={"chat_id": chat_id, "caption": caption},
                              files={"voice": ("respuesta.ogg", ogg, "audio/ogg")})
            if r.status_code != 200 or r.json().get("ok") is not True:
                raise RuntimeError("telegram no confirmó la voz")
        return True
    except Exception as exc:
        log.warning("spoken reply failed: kind=%s", type(exc).__name__)
        await core._tg_safe_send(chat_id, "La respuesta escrita ya está arriba. No pude enviar su audio local.")
        return False


async def to_opus(wav: bytes) -> bytes:
    """Telegram sendVoice: OGG con Opus."""
    with tempfile.TemporaryDirectory(prefix="jarvis-voz-") as tmp:
        src, dst = Path(tmp) / "r.wav", Path(tmp) / "r.ogg"
        src.write_bytes(wav)
        if await _ffmpeg(["-i", str(src), "-ac", "1", "-c:a", "libopus", "-b:a", "32k", str(dst)]) != 0:
            raise ValueError("no pude convertir la voz a Opus")
        return dst.read_bytes()


async def reply_voice() -> bytes:
    """La frase fija se genera una vez y queda en caché (no carga Piper en cada nota)."""
    cache = model_dir() / "respuesta-nota.ogg"
    if cache.exists() and cache.stat().st_size > 0:
        return cache.read_bytes()
    ogg = await to_opus(await speak_local(REPLY_TEXT))
    model_dir().mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_bytes(ogg)
    os.replace(tmp, cache)
    return ogg


def _heavy_lock(core):
    """El mismo candado de /producirvideo: Whisper y el video nunca a la vez en 512 MB."""
    growth = getattr(core, "_growth", None)
    return getattr(growth, "_video_lock", None)


async def handle_voice(core, chat_id, voice, load, alloc, stamp, save):
    try:
        seconds = int(voice.get("duration") or 0)
    except (TypeError, ValueError):
        seconds = 0
    if seconds > MAX_SECONDS:
        await core._tg_safe_send(chat_id, f"La nota dura {seconds} s. En local transcribo hasta {MAX_SECONDS} s; "
                                          "mándala más corta. No usé una API de pago.")
        return
    lock = _heavy_lock(core)
    if lock is not None and lock.locked():
        await core._tg_safe_send(chat_id, "Estoy produciendo un video y no caben los dos en memoria. Mándame la nota "
                                          "cuando termine. No usé una API de pago.")
        return
    async def work():
        raw = await core._tg_file(voice["file_id"])
        return await transcribe_local(raw)
    try:
        if lock is not None:
            async with lock:
                text = await work()
        else:
            text = await work()
    except Exception as exc:
        await core._tg_safe_send(chat_id, "No pude transcribir en local: " + str(exc)[:180] + ". No usé una API de pago.")
        return
    text = core._redact_secrets(text)[0]
    with core._data_lock:
        d = load()
        n = {"id": alloc(d, "voices"), "text": text, "status": "pending", "created": stamp()}
        d["voices"].append(n)
        save(d)
    await core._tg_send(chat_id, f"🎙 Dictado #{n['id']}:\n{text}\n\nRevisa monto y concepto antes de guardar. "
                                 f"/dictado {n['id']} para procesarlo. No ejecuté nada.")
    try:
        if lock is not None:
            if lock.locked():
                raise RuntimeError("video en curso")
            async with lock:
                ogg = await reply_voice()
        else:
            ogg = await reply_voice()
        async with core.httpx.AsyncClient(timeout=60) as hc:
            r = await hc.post(f"https://api.telegram.org/bot{core.TG_TOKEN}/sendVoice",
                              data={"chat_id": chat_id}, files={"voice": ("respuesta.ogg", ogg, "audio/ogg")})
            if r.status_code != 200:
                raise RuntimeError("telegram no confirmó la voz")
    except Exception:
        await core._tg_safe_send(chat_id, "La respuesta escrita ya está arriba. La voz local no salió; no usé una API de pago.")


def status() -> str:
    if not enabled():
        return "voz local apagada (LOCAL_VOICE_ENABLED=false)"
    try:
        import importlib.util
        ok = importlib.util.find_spec("faster_whisper") is not None
    except Exception:
        ok = False
    return "voz local activa (faster-whisper tiny)" if ok else "voz local prendida pero falta instalar faster-whisper"
