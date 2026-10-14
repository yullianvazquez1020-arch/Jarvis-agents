"""Jarvis: conversación por voz en tiempo real en la Mac del dueño (Python 3.9+).

Micrófono -> VAD (webrtcvad) -> ASR (faster-whisper) -> Jarvis (POST /api/encargo) -> TTS (Piper o `say`).
Barge-in: si hablas mientras Jarvis habla, se corta la voz al instante.
Regla fija: NADA se aprueba por voz. Un dictado que empiece con '/', que nombre /confirmar, /aprobar o /enviar,
o que contenga un código de confirmación (4-8 dígitos) se rechaza y no sale de la Mac.
Uso: JARVIS_URL=https://jarvis-agents.onrender.com JARVIS_ENCARGO_SECRET=... python3 desktop/voz_loop.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import unicodedata
from typing import Optional

RATE = 16000
FRAME_MS = 30
SILENCE_END_MS = 700          # fin de la frase tras 0,7 s de silencio
MAX_UTTERANCE_S = 30
_CMD_WORDS = ("confirmar", "aprobar", "enviar", "confirmarred", "ejecutar", "dictado", "cripto")


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c)).strip()


def refusal(text: str) -> Optional[str]:
    """Motivo de rechazo, o None si el dictado puede ir a Jarvis."""
    t = _norm(text)
    if not t:
        return "No entendí nada."
    if t.startswith("/") or re.search(r"(^|\s)(slash|barra)\s+\w+", t):
        return "Los comandos se escriben, no se dictan."
    if re.search(r"/\s*(" + "|".join(_CMD_WORDS) + r")\b", t) or re.search(r"\b(confirmar|aprobar)\b", t):
        return "Nada se aprueba ni se confirma por voz. Escríbelo en Telegram."
    if re.search(r"\b\d(?:[\s-]?\d){3,7}\b", t) or re.search(r"\b(codigo|clave|pin)\b", t):
        return "Ese dictado parece llevar un código. Los códigos solo se escriben."
    return None


def send_to_jarvis(text: str, url: str, secret: str, post=None) -> bool:
    """Envía el encargo por el camino del dueño. Nunca manda texto rechazado."""
    if refusal(text):
        return False
    if post is None:
        import requests
        post = requests.post
    r = post(url.rstrip("/") + "/api/encargo", headers={"X-Jarvis-Secret": secret},
             json={"texto": text[:4000]}, timeout=20)
    return getattr(r, "status_code", 0) == 200


class Speaker:
    """TTS interrumpible: Piper si existe (PIPER_MODEL), si no `say -v Paulina`."""

    def __init__(self):
        self.proc: Optional[subprocess.Popen] = None

    def command(self, text: str) -> list:
        model = os.getenv("PIPER_MODEL", "")
        if model and shutil.which("piper") and shutil.which("afplay"):
            return ["sh", "-c", 'piper --model "$1" --output_file /tmp/jarvis_voz.wav && afplay /tmp/jarvis_voz.wav',
                    "piper", model]
        return ["say", "-v", os.getenv("JARVIS_SAY_VOICE", "Paulina"), text]

    def speak(self, text: str) -> None:
        self.stop()
        cmd = self.command(text)
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE if cmd[0] == "sh" else None)
        if cmd[0] == "sh":
            self.proc.stdin.write(text.encode()); self.proc.stdin.close()

    def speaking(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self) -> None:          # barge-in
        if self.speaking():
            self.proc.terminate()
        self.proc = None


def segment(frames, is_speech, speaker: Optional[Speaker] = None):
    """Agrupa frames en frases. Si hay voz mientras Jarvis habla, lo corta (barge-in)."""
    buf, silent, limit = [], 0, SILENCE_END_MS // FRAME_MS
    for f in frames:
        if is_speech(f):
            if speaker is not None and speaker.speaking():
                speaker.stop()
            buf.append(f); silent = 0
        elif buf:
            silent += 1; buf.append(f)
            if silent >= limit or len(buf) * FRAME_MS >= MAX_UTTERANCE_S * 1000:
                yield b"".join(buf); buf, silent = [], 0
    if buf:
        yield b"".join(buf)


def main() -> int:  # pragma: no cover - necesita micrófono
    import numpy as np, sounddevice as sd, webrtcvad
    from faster_whisper import WhisperModel
    url, secret = os.getenv("JARVIS_URL", ""), os.getenv("JARVIS_ENCARGO_SECRET", "")
    if not url or not secret:
        print("Faltan JARVIS_URL y JARVIS_ENCARGO_SECRET (en tu Mac, nunca en Git)."); return 2
    vad, asr, spk = webrtcvad.Vad(2), WhisperModel(os.getenv("WHISPER_SIZE", "base"), compute_type="int8"), Speaker()
    n = RATE * FRAME_MS // 1000

    def frames():
        with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=n) as s:
            while True:
                yield bytes(s.read(n)[0])
    print("Jarvis escuchando. Ctrl+C para salir.")
    for audio in segment(frames(), lambda f: vad.is_speech(f, RATE), spk):
        pcm = np.frombuffer(audio, np.int16).astype(np.float32) / 32768
        text = " ".join(s.text for s in asr.transcribe(pcm, language="es", vad_filter=True)[0]).strip()
        if not text:
            continue
        print("Tú:", text)
        why = refusal(text)
        if why:
            spk.speak(why); continue
        spk.speak("Recibido, te respondo por Telegram." if send_to_jarvis(text, url, secret)
                  else "No pude enviarlo a Jarvis.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
