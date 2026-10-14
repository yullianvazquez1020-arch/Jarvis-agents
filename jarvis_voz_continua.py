"""Voz continua de Jarvis: conversación tipo llamada por WebSocket (/ws/voz).

Cliente -> servidor: tramas binarias PCM16 mono 16 kHz (cualquier tamaño) y mensajes JSON
  {"type": "fin"} (cerrar) o {"type": "interrumpir"} (barge-in manual).
Servidor -> cliente: eventos JSON (listo, escuchando, transcripcion, respuesta, rechazado, interrumpido,
  audio_fin, error) y audio WAV binario, una trama por frase, para empezar a sonar antes de terminar.

Turnos: VAD por energía con umbral adaptativo (sin dependencias). Fin de frase tras SILENCE_END_MS de silencio.
Barge-in: si el dueño habla mientras Jarvis responde, se cancela la respuesta y se avisa "interrumpido".
Regla fija: NADA se aprueba por voz. /aprobar, /confirmar, /enviar y códigos se rechazan aquí también
(los pagos y mensajes siguen exigiendo /aprobar o /confirmar por Telegram, con topes $100/op y $300/día).
El texto se limpia con el redactor de main antes de registrarlo. Nunca se guarda el audio.
"""
from __future__ import annotations

import array
import asyncio
import io
import math
import os
import re
import unicodedata
import wave
from typing import Awaitable, Callable, Optional

RATE = 16000
FRAME_MS = 30
FRAME_BYTES = RATE * FRAME_MS // 1000 * 2          # 960 bytes = 30 ms PCM16
SILENCE_END_MS = 700
MIN_SPEECH_MS = 240
MAX_UTTERANCE_S = 30
SPEECH_START_FRAMES = 3                            # 90 ms seguidos de voz para abrir turno / barge-in
_CMD_WORDS = ("confirmar", "aprobar", "enviar", "ejecutar", "dictado", "cripto")
_EN_WORDS = ("the", "what", "how", "please", "call", "hello", "thanks", "thank", "can", "could", "would", "appointment", "price", "yes", "tomorrow", "about")
_ES_WORDS = ("el", "la", "los", "las", "que", "como", "por", "favor", "hola", "gracias", "cita", "precio", "puedes", "quiero", "para", "una", "bueno", "manana")


def voz_de(lang: str) -> str:
    """Cada turno usa una de las dos voces: Ald (español latinoamericano) o Alan (inglés)."""
    return "alan" if lang == "en" else "es"


def idioma(text: str, previo: str = "es") -> str:
    """Elige español o inglés según el turno. Si no hay señal, se queda el anterior."""
    words = re.findall(r"[a-z]+", _norm(text))
    if not words:
        return "es" if previo not in ("es", "en") else previo
    en = sum(1 for w in words if w in _EN_WORDS)
    es = sum(1 for w in words if w in _ES_WORDS)
    if en > es:
        return "en"
    if es > en:
        return "es"
    return "es" if previo not in ("es", "en") else previo


def enabled() -> bool:
    return os.getenv("VOZ_CONTINUA_ENABLED", "false").strip().lower() in ("1", "true", "yes", "si", "sí")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def refusal(text: str, lang: str = "es") -> Optional[str]:
    """Mismo filtro que desktop/voz_loop.py: motivo de rechazo o None. El aviso sale en el idioma del turno."""
    t = _norm(text)
    en = lang == "en"
    if not t:
        return "I didn't catch that." if en else "No entendí nada."
    if t.startswith("/") or re.search(r"(^|\s)(slash|barra)\s+\w+", t):
        return "Commands are typed, not spoken." if en else "Los comandos se escriben, no se dictan."
    if re.search(r"/\s*(" + "|".join(_CMD_WORDS) + r")\b", t) or re.search(r"\b(confirmar|aprobar|approve|confirm)\b", t):
        return "Nothing is approved or confirmed by voice. Type it in Telegram." if en else "Nada se aprueba ni se confirma por voz. Escríbelo en Telegram."
    if re.search(r"\b\d(?:[\s-]?\d){3,7}\b", t) or re.search(r"\b(codigo|clave|pin|password|contrasena)\b", t):
        return "That sounds like a code. Codes are only typed." if en else "Ese dictado parece llevar un código. Los códigos solo se escriben."
    return None


def rms(frame: bytes) -> float:
    if len(frame) < 2:
        return 0.0
    a = array.array("h")
    a.frombytes(frame[: len(frame) // 2 * 2])
    return math.sqrt(sum(s * s for s in a) / len(a)) if a else 0.0


class VAD:
    """Detector de voz por energía con piso de ruido adaptativo."""

    def __init__(self, min_rms: float = 500.0, ratio: float = 3.0):
        self.floor = 100.0
        self.min_rms = min_rms
        self.ratio = ratio

    def is_speech(self, frame: bytes) -> bool:
        e = rms(frame)
        speech = e >= max(self.min_rms, self.floor * self.ratio)
        if not speech:                                  # solo el silencio mueve el piso de ruido
            self.floor = 0.95 * self.floor + 0.05 * max(e, 1.0)
        return speech


def pcm_to_wav(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(pcm)
    return buf.getvalue()


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", " ".join(str(text or "").split()))
    return [p for p in parts if p.strip()][:20]


SendJson = Callable[[dict], Awaitable[None]]
SendBytes = Callable[[bytes], Awaitable[None]]


class VozSession:
    """Máquina de turnos independiente de FastAPI (inyectable para pruebas)."""

    def __init__(self, *, transcribe, reply, speak, send_json: SendJson, send_bytes: SendBytes,
                 log: Callable[[str], None] = lambda s: None, redact: Callable[[str], str] = lambda s: s,
                 vad: Optional[VAD] = None):
        self.transcribe, self.reply, self.speak = transcribe, reply, speak
        self.send_json, self.send_bytes = send_json, send_bytes
        self.log, self.redact = log, redact
        self.vad = vad or VAD()
        self.idioma = "es"
        self._buf = bytearray()
        self._utt = bytearray()
        self._speech_run = 0
        self._silence_ms = 0
        self._in_speech = False
        self.task: Optional[asyncio.Task] = None
        self.turns = 0

    @property
    def responding(self) -> bool:
        return self.task is not None and not self.task.done()

    async def interrupt(self) -> bool:
        if not self.responding:
            return False
        self.task.cancel()
        try:
            await self.task
        except (asyncio.CancelledError, Exception):
            pass
        await self.send_json({"type": "interrumpido"})
        return True

    async def feed(self, data: bytes) -> None:
        self._buf.extend(data)
        while len(self._buf) >= FRAME_BYTES:
            frame = bytes(self._buf[:FRAME_BYTES]); del self._buf[:FRAME_BYTES]
            await self._frame(frame)

    async def _frame(self, frame: bytes) -> None:
        speech = self.vad.is_speech(frame)
        if not self._in_speech:
            self._speech_run = self._speech_run + 1 if speech else 0
            self._utt.extend(frame)
            self._utt[:] = self._utt[-FRAME_BYTES * SPEECH_START_FRAMES:]   # pre-roll corto
            if self._speech_run >= SPEECH_START_FRAMES:
                self._in_speech, self._silence_ms = True, 0
                await self.interrupt()                                     # barge-in
                await self.send_json({"type": "escuchando"})
            return
        self._utt.extend(frame)
        self._silence_ms = 0 if speech else self._silence_ms + FRAME_MS
        too_long = len(self._utt) >= RATE * 2 * MAX_UTTERANCE_S
        if self._silence_ms >= SILENCE_END_MS or too_long:
            pcm = bytes(self._utt)
            self._utt.clear(); self._in_speech = False; self._speech_run = 0
            if len(pcm) >= RATE * 2 * MIN_SPEECH_MS // 1000:
                self.task = asyncio.ensure_future(self._turn(pcm))

    async def _turn(self, pcm: bytes) -> None:
        try:
            text = await self.transcribe(pcm_to_wav(pcm))
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.send_json({"type": "error", "texto": self._aviso("audio")}); return
        self.idioma = idioma(text, self.idioma)
        clean = self.redact(text or "")
        await self.send_json({"type": "transcripcion", "texto": clean, "idioma": self.idioma})
        why = refusal(text, self.idioma)
        if why:
            self.log("voz continua: dictado rechazado")
            await self.send_json({"type": "rechazado", "texto": why, "idioma": self.idioma})
            await self._say(why); return
        self.turns += 1
        try:
            answer = await self.reply(text, self.idioma)
        except asyncio.CancelledError:
            raise
        except Exception:
            answer = self._aviso("respuesta")
        answer = self.redact(answer or "")
        await self.send_json({"type": "respuesta", "texto": answer, "idioma": self.idioma})
        await self._say(answer)

    def _aviso(self, cual: str) -> str:
        en = self.idioma == "en"
        if cual == "audio":
            return "I couldn't understand the audio." if en else "No pude entender el audio."
        if cual == "voz":
            return "Voice isn't available; the text is on screen." if en else "La voz no está disponible; mostré el texto."
        return "I had a problem answering. Try again." if en else "Tuve un problema al responder. Inténtalo otra vez."

    async def _say(self, text: str) -> None:
        for part in sentences(text):
            try:
                audio = await self.speak(part, self.idioma)
            except asyncio.CancelledError:
                raise
            except Exception:
                await self.send_json({"type": "error", "texto": self._aviso("voz")})
                break
            if audio:
                await self.send_bytes(audio)
        await self.send_json({"type": "audio_fin"})

    async def close(self) -> None:
        if self.responding:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass
