"""Cliente de voz continua para la Mac: micrófono -> /ws/voz -> altavoz, con barge-in.

El servidor hace VAD, transcripción, respuesta y voz. Cada turno sale en español o en inglés.
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
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request
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


def device_token(env=None, home=None) -> str:
    """JARVIS_DEVICE_TOKEN, si no el token emparejado en ~/.jarvis-desktop/device.json (TokenStore)."""
    env = os.environ if env is None else env
    tok = (env.get("JARVIS_DEVICE_TOKEN") or "").strip()
    if tok:
        return tok
    try:
        from jarvis_client import TokenStore
    except Exception:
        return ""
    folder = home or env.get("VOICE_HOME") or str(Path.home() / ".jarvis-desktop")
    return (TokenStore(folder).load() or "").strip()


def auth_headers(env=None, home=None) -> dict:
    """Primero el token del dispositivo (Authorization: Bearer jd1...); si no hay, JARVIS_ENCARGO_SECRET."""
    env = os.environ if env is None else env
    tok = device_token(env, home)
    if tok.startswith("jd1."):
        return {"Authorization": "Bearer " + tok}
    secret = (env.get("JARVIS_ENCARGO_SECRET") or "").strip()
    if not secret:
        raise ValueError("Empareja este Mac con /emparejar (o pon JARVIS_ENCARGO_SECRET)")
    return headers(secret)


def hud_endpoint(base: str) -> str:
    """El aviso al HUD solo va a este equipo. Una URL externa se rechaza."""
    raw = (base or "").strip() or "http://127.0.0.1:8765"
    parsed = urllib.parse.urlsplit(raw.rstrip("/"))
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("el HUD solo se avisa en este equipo")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("el HUD solo se avisa en este equipo")
    port = parsed.port or 80
    host = parsed.hostname
    shown = f"[{host}]" if ":" in host else host
    return f"http://{shown}:{port}/api/voz"


def hud_token(home: str | None = None) -> str:
    """Token que el panel deja en ~/.jarvis-desktop/voz-token. Vacío si el panel nunca ha corrido."""
    carpeta = Path(home or os.getenv("VOICE_HOME") or (Path.home() / ".jarvis-desktop"))
    try:
        return carpeta.joinpath("voz-token").read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def hud_notice(ev: dict) -> dict | None:
    """Traduce un evento de /ws/voz a lo que el HUD sabe dibujar. No aprueba ni envía nada."""
    if not isinstance(ev, dict):
        return None
    kind = ev.get("type")
    lang = ev.get("idioma") if ev.get("idioma") in ("es", "en") else None
    text = " ".join(str(ev.get("texto") or "").split())[:240]
    notice: dict = {}
    if lang:
        notice["idioma"] = lang
    if kind == "escuchando":
        notice["estado"] = "escuchando"
    elif kind == "transcripcion" and text:
        notice["estado"] = "pensando"
        notice["linea"] = {"quien": "tu", "texto": text}
    elif kind in ("respuesta", "rechazado") and text:
        notice["estado"] = "hablando"
        notice["linea"] = {"quien": "jarvis", "texto": text}
    elif kind == "interrumpido":
        notice["estado"] = "escuchando"
        notice["corte"] = True
    elif kind in ("listo", "error"):
        notice["estado"] = "idle"
        if kind == "error" and text:
            notice["linea"] = {"quien": "jarvis", "texto": text}
    else:
        return None
    return notice


def post_hud(notice: dict, base: str | None = None, timeout: float = 0.4, token: str | None = None) -> bool:
    """Avisa al display. Si el HUD está cerrado o no hay token, no es un error: la voz sigue."""
    if not notice:
        return False
    tok = hud_token() if token is None else token
    if not tok:
        return False
    try:
        url = hud_endpoint(base if base is not None else os.getenv("JARVIS_HUD", ""))
        body = json.dumps(notice).encode()
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json", "X-Jarvis-Voz": tok})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (OSError, urllib.error.URLError, ValueError):
        return False


class HudLink:
    """Lleva el turno al HUD y deja la boca en movimiento mientras suena el audio."""

    def __init__(self, publish=None):
        self.publish = publish or post_hud
        self.hablando = False
        self.sono = False

    def _send(self, notice: dict) -> None:
        try:
            self.publish(notice)
        except Exception:
            return

    def event(self, ev: dict) -> None:
        if isinstance(ev, dict) and ev.get("type") == "audio_fin":
            if not self.sono:
                self.hablando = False
                self._send({"estado": "idle"})
            return
        notice = hud_notice(ev)
        if not notice:
            return
        if notice.get("estado") != "hablando":
            self.sono = False
        self.hablando = notice.get("estado") == "hablando"
        self._send(notice)

    def audio(self) -> None:
        self.sono = True
        if self.hablando:
            return
        self.hablando = True
        self._send({"estado": "hablando"})

    def silencio(self) -> None:
        if not self.hablando or not self.sono:
            return
        self.hablando = False
        self.sono = False
        self._send({"estado": "idle"})


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


def handle_event(raw: str, player: Player, publish=None) -> dict:
    ev = json.loads(raw)
    if ev.get("type") in ("interrumpido", "escuchando"):
        player.stop()
    if publish:
        try:
            publish(ev)
        except Exception:
            pass
    return ev


async def main() -> int:  # pragma: no cover - necesita micrófono y red
    import asyncio
    import numpy as np
    import sounddevice as sd
    import websockets
    url = ws_url(os.getenv("JARVIS_URL", ""))
    hdr = auth_headers()
    player = Player()
    link = HudLink()
    if not hud_token():
        print("El panel local no ha dejado su token (~/.jarvis-desktop/voz-token): la conversación no se "
              "verá en la pantalla. Abre el panel y vuelve a arrancar la voz. La llamada funciona igual.")
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
                    link.audio()
                else:
                    ev = handle_event(msg, player, link.event)
                    if ev.get("texto"):
                        print(f"[{ev['type']}] {ev['texto']}")
        async def play():
            while True:
                if player.queue:
                    link.audio()
                    rate, pcm = player.queue.pop(0)
                    sd.play(np.frombuffer(pcm, dtype=np.int16), rate)
                    await asyncio.sleep(0.05)
                    while sd.get_stream().active:   # sd.stop() (barge-in) lo corta
                        await asyncio.sleep(0.03)
                else:
                    link.silencio()
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
