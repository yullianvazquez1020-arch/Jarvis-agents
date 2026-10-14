"""Cliente de voz continua para la Mac: micrófono -> /ws/voz -> altavoz, con barge-in.

El servidor hace VAD, transcripción, respuesta y voz (Alan si JARVIS_REPLY_LANGUAGE=en-GB).
Aquí solo se captura el micro, se envía PCM16 16 kHz y se reproducen los WAV que llegan;
si llega "interrumpido" o el dueño empieza a hablar, se corta la reproducción al instante.
Nada se aprueba por voz (el servidor y voz_loop.refusal lo rechazan).
Uso: JARVIS_URL=wss://jarvis-agents.onrender.com JARVIS_ENCARGO_SECRET=... python3 desktop/voz_continua.py
Requiere (solo en la Mac): pip install websockets sounddevice
"""
from __future__ import annotations

import io
import json
import os
import wave

RATE = 16000
BLOCK = 480  # 30 ms


def ws_url(base: str) -> str:
    base = (base or "").strip().rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[8:]
    elif base.startswith("http://"):
        base = "ws://" + base[7:]
    if not base.startswith(("wss://", "ws://")):
        raise ValueError("JARVIS_URL debe empezar con https:// o wss://")
    if base.startswith("ws://") and not any(h in base for h in ("localhost", "127.0.0.1")):
        raise ValueError("Usa wss:// fuera de localhost: el secreto no viaja sin cifrar")
    return base + "/ws/voz"


def headers(secret: str) -> dict:
    if not secret:
        raise ValueError("Falta JARVIS_ENCARGO_SECRET")
    return {"X-Jarvis-Secret": secret}


def wav_frames(data: bytes):
    with wave.open(io.BytesIO(data), "rb") as w:
        return w.getframerate(), w.readframes(w.getnframes())


class Player:
    """Cola de audio interrumpible."""

    def __init__(self):
        self.queue = []

    def push(self, data: bytes):
        self.queue.append(wav_frames(data))

    def stop(self):
        self.queue.clear()


def handle_event(raw: str, player: Player) -> dict:
    ev = json.loads(raw)
    if ev.get("type") in ("interrumpido", "escuchando"):
        player.stop()
    return ev


async def main() -> int:  # pragma: no cover - necesita micrófono y red
    import asyncio
    import numpy as np
    import sounddevice as sd
    import websockets
    url = ws_url(os.getenv("JARVIS_URL", ""))
    hdr = headers(os.getenv("JARVIS_ENCARGO_SECRET", ""))
    player = Player()
    loop = asyncio.get_running_loop()
    mic: asyncio.Queue = asyncio.Queue()
    def cb(indata, frames, t, status):
        loop.call_soon_threadsafe(mic.put_nowait, bytes(indata))
    async with websockets.connect(url, additional_headers=hdr, max_size=8 * 1024 * 1024) as ws:
        async def send():
            with sd.RawInputStream(samplerate=RATE, blocksize=BLOCK, channels=1, dtype="int16", callback=cb):
                while True:
                    await ws.send(await mic.get())
        async def recv():
            async for msg in ws:
                if isinstance(msg, bytes):
                    player.push(msg)
                else:
                    ev = handle_event(msg, player)
                    if ev.get("texto"):
                        print(f"[{ev['type']}] {ev['texto']}")
        async def play():
            while True:
                if player.queue:
                    rate, pcm = player.queue.pop(0)
                    sd.play(np.frombuffer(pcm, dtype=np.int16), rate)
                    await asyncio.sleep(0.05)
                    while sd.get_stream().active:   # sd.stop() (barge-in) lo corta
                        await asyncio.sleep(0.03)
                else:
                    await asyncio.sleep(0.03)
        orig_stop = player.stop
        def stop():
            orig_stop(); sd.stop()
        player.stop = stop
        await asyncio.gather(send(), recv(), play())
    return 0


if __name__ == "__main__":  # pragma: no cover
    import asyncio
    raise SystemExit(asyncio.run(main()))
