#!/usr/bin/env python3
"""Jarvis desktop companion: local voice + monitor panels for the owner's Mac.

Runs ONLY on the Mac (never on Render). Python 3.8+, standard library only: no pip install needed.

    python3 desktop/app.py            start (prints a one-time link and opens it in the browser)
    python3 desktop/app.py --check    measure this Mac: macOS, CPU, Python, Spanish voices, whisper.cpp
    python3 desktop/app.py --bench FILE.wav   time whisper.cpp on a recording (real-time factor)

Security model (see docs/VOICE_DESKTOP.md):
  * Listens on 127.0.0.1 only (0.0.0.0 is refused; another LAN address only with VOICE_ALLOW_LAN=true).
  * Every request must carry a Host for this address; every POST must carry X-Jarvis-UI and, when the browser
    sends one, an Origin equal to this page. The browser session is an HttpOnly, SameSite=Strict cookie that
    comes from a one-time launch link (2 minutes). Other web sites cannot drive this server.
  * The browser never receives the device token, AGENT_API_KEY or any other key. Only this process talks to
    Render, with the device token in the Authorization header.
  * One window captures the microphone and plays audio; the others only show panels and events.
  * Audio is not kept (VOICE_RETAIN_AUDIO=false): temporary files are per request and deleted.
"""
import argparse
import http.server
import json
import logging
import os
import platform
import re
import secrets
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import intents                                    # noqa: E402
from hand_mouse import HandMouse                  # noqa: E402
from audio import engines                         # noqa: E402
from audio.wav import AudioError, check_wav       # noqa: E402
from jarvis_client import JarvisClient, ServerError, TokenStore, check_url, safe_events, PANELS  # noqa: E402

VERSION = "desktop-1"
log = logging.getLogger("jarvis.desktop")
UI_FILES = {"startup.js": "text/javascript; charset=utf-8", "hand-mouse.js": "text/javascript; charset=utf-8", "hand-worker.js": "text/javascript; charset=utf-8", "atlas.js": "text/javascript; charset=utf-8", "avatar.css": "text/css; charset=utf-8", "avatar.js": "text/javascript; charset=utf-8", "hands.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
            "hud.js": "text/javascript; charset=utf-8", "mask.js": "text/javascript; charset=utf-8",
            "wav.js": "text/javascript; charset=utf-8", "lipsync.js": "text/javascript; charset=utf-8"}
LAUNCH_TTL = 120
SESSION_TTL = 12 * 3600
WINDOW_STALE = 30
RATE_MIN, RATE_MAX = 0.7, 1.4
DEFAULTS = {"VOICE_BIND_HOST": "127.0.0.1", "VOICE_PORT": "8765", "VOICE_STT_BACKEND": "none",
            "VOICE_TTS_BACKEND": "none", "VOICE_WAKE_WORD_ENABLED": "false", "VOICE_RETAIN_AUDIO": "false",
            "VOICE_AUTO_CAMERA": "false", "VOICE_STARTUP_AUDIO": "false", "VOICE_DEMO": "false", "VOICE_ALLOW_LAN": "false", "VOICE_HOME": str(Path.home() / ".jarvis-desktop")}

PULSE_S = 180                 # 4.0.5: one authenticated heartbeat every 3 minutes (status + alerts)
SLOW_MS = 1500
HUD_IDS = ("cobros", "vencidos", "agenda", "balances", "stock", "mensajes", "practica")
DEMO_STATUS = {"jarvis_version": "DEMO", "storage": "DEMO (sin datos reales)", "ai_configured": False,
               "crypto_mode": "practice", "coinbase_connected": False, "real_trading_active": False}
DEMO_HUD = [
    {"id": "cobros", "title": "DEMO · Cobros pendientes", "value": "$350.00", "lines": ["Cliente Ejemplo — Cocina: $350.00"]},
    {"id": "vencidos", "title": "DEMO · Trabajos vencidos", "value": "1", "lines": ["#0 Cliente Ejemplo — Baño (ejemplo)"]},
    {"id": "agenda", "title": "DEMO · Agenda hoy y mañana", "value": "2", "lines": ["Hoy 9:00 Visita de obra (ejemplo)",
                                                                                  "Mañana 14:00 Entrega (ejemplo)"]},
    {"id": "balances", "title": "DEMO · Balances del banco", "value": "1 cuenta", "stale": True,
     "lines": ["Cuenta Ejemplo: $1,234.00 (dato de hace 5 días)"]},
    {"id": "stock", "title": "DEMO · Stock bajo", "value": "1", "lines": ["Tornillos: 2 ud (mínimo 10)"]},
    {"id": "mensajes", "title": "DEMO · Mensajes esperando /enviar", "value": "0", "lines": []},
    {"id": "practica", "title": "DEMO · Práctica cripto (simulada)", "value": "$1,000.00", "lines": ["Capital simulado de ejemplo"]},
]
DEMO_ALERTS = [{"key": "demo:1", "kind": "recordatorio", "text": "DEMO: recordatorio de ejemplo", "when": ""}]

DEMO_PANELS = {
    "estado": {"title": "DEMO — Estado", "lines": ["Datos de ejemplo. No es tu Jarvis.", "Versión: DEMO",
                                                   "Modo cripto: PRÁCTICA (ejemplo)"], "speak": "Modo demostración.",
               "sensitive": False},
    "agenda": {"title": "DEMO — Agenda", "lines": ["Datos de ejemplo, no son tuyos.", "• 9:00 Visita de obra (ejemplo)",
                                                   "• 14:00 Entrega de gabinetes (ejemplo)"],
               "speak": "Esto es una agenda de ejemplo.", "sensitive": False},
    "cobros": {"title": "DEMO — Cobros", "lines": ["Datos de ejemplo, no son tuyos.",
                                                   "• Cliente Ejemplo — Cocina: $350.00 (ejemplo)"],
               "speak": "Estos cobros son de ejemplo.", "sensitive": False},
    "practica": {"title": "DEMO — Práctica", "lines": ["Datos de ejemplo.", "Efectivo simulado: $1,000.00 (ejemplo)"],
                 "speak": "Panel de práctica de ejemplo.", "sensitive": False},
}


def truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "si", "sí")


def load_config(path=None):
    cfg = dict(DEFAULTS)
    files = [Path(path)] if path else [Path(DEFAULTS["VOICE_HOME"]) / "config.env", HERE / "config.env"]
    for f in files:
        if f.is_file():
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1); cfg[k.strip()] = v.strip().strip('"').strip("'")
            break
    for k in list(DEFAULTS) + ["JARVIS_SERVER_URL", "JARVIS_DEVICE_TOKEN", "VOICE_WHISPER_BIN", "VOICE_STT_MODEL_PATH",
                               "VOICE_STT_THREADS", "VOICE_TTS_VOICE", "VOICE_PIPER_BIN"]:
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def check_bind(host, allow_lan):
    if host in ("127.0.0.1", "localhost", "::1"):
        return host
    if host in ("0.0.0.0", "::", ""):
        raise SystemExit("VOICE_BIND_HOST=0.0.0.0 no está permitido: expondría el panel a toda la red.")
    if not allow_lan:
        raise SystemExit("Para escuchar en otra dirección pon VOICE_ALLOW_LAN=true (el micrófono además "
                         "necesita HTTPS válido en esa dirección).")
    return host


class Companion:
    """All state of one running companion. Thread-safe; the HTTP handler only calls methods here."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.hand_mouse = HandMouse(enabled=(cfg.get("_HAND_MOUSE_ENABLED") is True
            and cfg["VOICE_BIND_HOST"] in ("127.0.0.1", "localhost", "::1")
            and not truthy(cfg["VOICE_DEMO"])))
        self.lock = threading.RLock(); self.cond = threading.Condition(self.lock)
        self.home = Path(cfg["VOICE_HOME"])
        self.tokens = TokenStore(self.home)
        self.demo = truthy(cfg["VOICE_DEMO"])
        url = cfg.get("JARVIS_SERVER_URL", "")
        self.client = JarvisClient(check_url(url) if url else "", self._token)
        self.stt, self.tts = engines.build(cfg)
        self.retain = truthy(cfg["VOICE_RETAIN_AUDIO"])
        self.launch = {}; self.sessions = {}
        self.windows = {}; self.owner = None
        self.events = []; self.seq = 0
        self.turns = {}; self.last = {"text": "", "audio": None}
        self.audio = {}                                   # id -> (bytes, type); memory only, last 10
        self.pairing = None
        self.server_version = None
        self.prefs = {"rate": 1.0, "discreet": False, "review": False, "mic": True}
        self._load_prefs()
        # 4.0.5 (3.1-3.3): server health for the top bar, HUD cache and alerts shown once
        self.health = {"state": "demo" if self.demo else "unknown", "latency_ms": None, "last_ok": None, "info": {}}
        self.hud_cache = []
        self.last_alert = None
        self.alerts_seen = self._load_seen()

    # --- secrets and prefs ---
    def _token(self):
        return self.cfg.get("JARVIS_DEVICE_TOKEN") or self.tokens.load()

    def _load_prefs(self):
        try:
            data = json.loads((self.home / "prefs.json").read_text(encoding="utf-8"))
            for k in self.prefs:
                if k in data and type(data[k]) is type(self.prefs[k]):
                    self.prefs[k] = data[k]
        except (OSError, ValueError):
            pass
        self.prefs["rate"] = min(RATE_MAX, max(RATE_MIN, float(self.prefs["rate"])))

    def set_prefs(self, **kw):
        with self.lock:
            for k, v in kw.items():
                if k == "rate":
                    self.prefs["rate"] = round(min(RATE_MAX, max(RATE_MIN, float(v))), 2)
                elif k in ("discreet", "review", "mic"):
                    self.prefs[k] = bool(v)
            try:
                self.home.mkdir(parents=True, exist_ok=True)
                (self.home / "prefs.json").write_text(json.dumps(self.prefs), encoding="utf-8")
            except OSError:
                pass
            self.emit({"type": "prefs", "prefs": dict(self.prefs)})
            return dict(self.prefs)

    # --- alerts: each key is shown (and spoken) once, also across restarts ---
    def _load_seen(self):
        try:
            data = json.loads((self.home / "alerts_seen.json").read_text(encoding="utf-8"))
            return [str(x) for x in data][-300:] if isinstance(data, list) else []
        except (OSError, ValueError):
            return []

    def _save_seen(self):
        try:
            self.home.mkdir(parents=True, exist_ok=True)
            (self.home / "alerts_seen.json").write_text(json.dumps(self.alerts_seen[-300:]), encoding="utf-8")
        except OSError:
            pass

    def new_alerts(self, alerts):
        fresh = []
        with self.lock:
            for a in alerts or []:
                if not isinstance(a, dict) or not a.get("key") or a["key"] in self.alerts_seen:
                    continue
                item = {"key": str(a["key"])[:80], "kind": str(a.get("kind", ""))[:20], "text": str(a.get("text", ""))[:200],
                        "when": str(a.get("when", ""))[:20]}
                self.alerts_seen.append(item["key"]); fresh.append(item)
            if fresh:
                self.alerts_seen = self.alerts_seen[-300:]; self._save_seen()
                self.last_alert = fresh[-1]
        for item in fresh:
            self.emit(dict(item, type="alert"))
        if fresh:
            self.speak(fresh[-1]["text"] if len(fresh) == 1 else f"Tienes {len(fresh)} avisos nuevos.",
                       sensitive=True)
        return fresh

    def alert_repeat(self):
        with self.lock:
            a = self.last_alert
        if not a:
            return {"ok": False}
        self.emit(dict(a, type="alert", repeat=True)); self.speak(a["text"], sensitive=True)
        return {"ok": True}

    # --- server heartbeat (status + alerts in one request) ---
    def pulse_once(self):
        if self.demo:
            with self.lock:
                self.health.update(state="demo", info=dict(DEMO_STATUS), last_ok=time.time(), latency_ms=0)
            self.emit({"type": "health", "health": self.health_view()})
            self.new_alerts(DEMO_ALERTS); return
        if not self.client.url or not self._token():
            with self.lock:
                self.health.update(state="unpaired", info={})
            self.emit({"type": "health", "health": self.health_view()}); return
        t0 = time.time()
        try:
            st = self.client.pulse()
            ms = int((time.time() - t0) * 1000)
            info = {k: st.get(k) for k in ("jarvis_version", "storage", "ai_configured", "crypto_mode",
                                           "coinbase_connected", "real_trading_active")}
            with self.lock:
                self.health.update(state="ok" if ms < SLOW_MS else "slow", latency_ms=ms, last_ok=time.time(), info=info)
                self.server_version = info.get("jarvis_version")    # only after an authenticated answer
            self.emit({"type": "health", "health": self.health_view()})
            self.new_alerts(st.get("alerts"))
        except ServerError as e:
            if e.status == 401:
                self._auth_lost(e.detail)
            with self.lock:
                self.health.update(state="down" if e.status == 0 else "error", latency_ms=None)
                self.server_version = None
            self.emit({"type": "health", "health": self.health_view()})

    def health_view(self):
        with self.lock:
            h = dict(self.health)
        age = None if not h["last_ok"] else int(time.time() - h["last_ok"])
        if h["state"] == "ok" and age is not None and age > 2 * PULSE_S + 30:
            h["state"] = "slow"                                   # no fresh answer for a while: amber
        h["age_s"] = age; h.pop("last_ok", None)
        return h

    def pulse_loop(self, stop):
        while not stop.is_set():
            try:
                self.pulse_once()
            except Exception as e:                                # never kill the loop
                log.warning("pulse failed: %s", type(e).__name__)
            stop.wait(PULSE_S)

    # --- HUD for the second monitor (read-only) ---
    def hud(self):
        if self.demo:
            cards = [dict(c, as_of="", stale=c.get("stale", False), sensitive=False, demo=True) for c in DEMO_HUD]
        elif not self.client.url or not self._token():
            cards = []  # Missing connection is not permission to fabricate business data.
        else:
            raw = self.client.hud().get("cards") or []
            cards = []
            for c in raw:
                if not isinstance(c, dict) or c.get("id") not in HUD_IDS:
                    continue
                cards.append({"id": c["id"], "title": str(c.get("title", ""))[:60], "value": str(c.get("value", ""))[:40],
                              "lines": [str(x)[:200] for x in (c.get("lines") or [])][:8], "as_of": str(c.get("as_of") or ""),
                              "stale": bool(c.get("stale")), "sensitive": bool(c.get("sensitive")),
                              "detail": c.get("detail") if c.get("detail") in PANELS else None, "demo": False})
        with self.lock:
            self.hud_cache = cards
        return {"cards": cards, "demo": bool(cards and cards[0].get("demo"))}

    def open_detail(self, target):
        """A card or panel clicked on any monitor opens in the main window. Only shows; never writes."""
        if target in PANELS:
            data = self.panel(target)
        else:
            with self.lock:
                card = next((c for c in self.hud_cache if c["id"] == target), None)
            if not card:
                raise KeyError(target)
            data = {"panel": "hud:" + card["id"], "title": card["title"], "lines": card["lines"], "as_of": card["as_of"],
                    "sensitive": card["sensitive"], "demo": card.get("demo", False)}
        self.emit({"type": "panel.open", "data": data})
        return {"ok": True}

    def local_health_text(self):
        """'¿Cómo estás?' answered locally: server, voice, microphone, windows. Never balances."""
        h = self.health_view(); info = h.get("info") or {}
        server = {"ok": f"responde (Jarvis {info.get('jarvis_version')}, {h.get('latency_ms')} ms)",
                  "slow": f"responde con retraso ({h.get('latency_ms') or '?'} ms)", "down": "sin red",
                  "error": "responde con error", "unpaired": "este equipo no está emparejado",
                  "demo": "modo DEMO, sin conectar", "unknown": "todavía no lo he comprobado"}.get(h["state"], h["state"])
        with self.lock:
            wins = sum(1 for t in self.windows.values() if time.time() - t < WINDOW_STALE)
        voice = (f"reconocimiento {'listo' if not self.stt.problem() else 'no configurado'}, "
                 f"voz {'lista' if not self.tts.problem() else 'no configurada'}")
        return (f"Servidor: {server}. Voz: {voice}. Micrófono: {'encendido' if self.prefs['mic'] else 'apagado'}. "
                f"Ventanas abiertas: {wins}" + (", una por monitor si las moviste." if wins > 1 else "."))

    # --- browser sessions ---
    def new_launch(self):
        tok = secrets.token_urlsafe(24)
        with self.lock:
            self.launch[tok] = time.time() + LAUNCH_TTL
        return tok

    def use_launch(self, tok):
        with self.lock:
            exp = self.launch.pop(tok or "", 0)
            if exp < time.time():
                return None
            sid = secrets.token_urlsafe(32); self.sessions[sid] = time.time() + SESSION_TTL
            return sid

    def session_ok(self, sid):
        with self.lock:
            return bool(sid) and self.sessions.get(sid, 0) > time.time()

    # --- events (long poll) ---
    def emit(self, ev):
        with self.cond:
            self.seq += 1; ev = dict(ev, seq=self.seq, at=time.time())
            self.events = (self.events + [ev])[-500:]
            self.cond.notify_all()

    def poll(self, since, window, timeout=20.0):
        end = time.time() + timeout
        with self.cond:
            self._seen(window)
            while True:
                new = [e for e in self.events if e["seq"] > since]
                if new or time.time() >= end:
                    return {"events": new, "seq": self.seq, "owner": self.owner == window}
                self.cond.wait(max(0.1, end - time.time()))
                self._seen(window)

    # --- windows: one captures audio, the others only display ---
    def _seen(self, window):
        if window:
            self.windows[window] = time.time()
            if self.owner and time.time() - self.windows.get(self.owner, 0) > WINDOW_STALE:
                self.owner = None

    def hello(self, window):
        with self.lock:
            self._seen(window)
            if self.owner is None:
                self.owner = window; self.emit({"type": "audio.owner", "window": window})
            return {"owner": self.owner == window}

    def claim_audio(self, window):
        with self.lock:
            self._seen(window); self.owner = window
            self.emit({"type": "audio.owner", "window": window})
            return {"owner": True}

    # --- state for the UI (no secrets) ---
    def state(self):
        with self.lock:
            p = self.pairing
            return {"version": VERSION, "demo": self.demo, "server_configured": bool(self.client.url),
                    "paired": bool(self._token()), "server_version": self.server_version,
                    "startup": {"camera": truthy(self.cfg.get("VOICE_AUTO_CAMERA", "false")), "audio": truthy(self.cfg.get("VOICE_STARTUP_AUDIO", "false"))},
                    "stt": {"engine": self.stt.name, "problem": self.stt.problem()},
                    "tts": {"engine": self.tts.name, "problem": self.tts.problem()},
                    "processing": "Todo el audio se procesa en esta Mac" if self.stt.name != "none" else
                                  "Sin reconocimiento de voz: escribe tus consultas",
                    "wake_word": False, "retain_audio": self.retain, "prefs": dict(self.prefs),
                    "pairing": None if not p else {"code": p.get("code"), "status": p.get("status"),
                                                   "error": p.get("error")},
                    "panels": list(PANELS), "server": self.health_view(),
                    "windows": sum(1 for t in self.windows.values() if time.time() - t < WINDOW_STALE)}

    def refresh_status(self):
        """Kept for callers of 4.0.4: one heartbeat now."""
        return self.pulse_once()

    # --- pairing ---
    def pair_start(self):
        if self.demo or not self.client.url:
            raise ServerError(400, "configura JARVIS_SERVER_URL y apaga VOICE_DEMO para emparejar")
        r = self.client.pair_start(platform.node()[:40] or "Mac")
        with self.lock:
            self.pairing = {"id": r["pairing_id"], "secret": r["claim_secret"], "code": r["code"],
                            "status": "pending", "until": time.time() + int(r.get("expires_in", 600))}
        threading.Thread(target=self._pair_poll, daemon=True).start()
        return {"code": r["code"], "instructions": r.get("instructions", "")}

    def _pair_poll(self, every=3.0):
        while True:
            with self.lock:
                p = self.pairing
                if not p or p["status"] != "pending" or p.get("polling"):
                    return
                p["polling"] = True                       # one poller at a time
            try:
                if self._pair_step(p, every):
                    return
            finally:
                with self.lock:
                    p.pop("polling", None)

    def _pair_step(self, p, every):
        """One claim attempt. -> True when finished (approved, expired or error); False to try again later."""
        if time.time() > p["until"]:
            with self.lock:
                p["status"] = "expired"
            self.emit({"type": "pairing", "status": "expired"})
            return True
        try:
            r = self.client.pair_claim(p["id"], p["secret"])
        except ServerError as e:
            with self.lock:
                p["status"] = "error"; p["error"] = e.detail
            self.emit({"type": "pairing", "status": "error", "detail": e.detail})
            return True
        if r.get("status") == "approved" and r.get("token"):
            self.tokens.save(r["token"], r.get("device_id"))
            with self.lock:
                p["status"] = "approved"; p.pop("secret", None)
            self.emit({"type": "pairing", "status": "approved"})
            self.refresh_status()
            return True
        time.sleep(every)
        return False

    def _auth_lost(self, detail):
        """4.0.5 (2.2): revoked or expired token -> forget it so the panel offers pairing again."""
        if not self.cfg.get("JARVIS_DEVICE_TOKEN"):
            self.tokens.delete()
        with self.lock:
            self.server_version = None
        self.emit({"type": "pairing", "status": "removed", "detail": detail})

    def unpair(self):
        self.tokens.delete()
        with self.lock:
            self.server_version = None
        self.emit({"type": "pairing", "status": "removed"})

    # --- panels ---
    def panel(self, name):
        if name not in PANELS:
            raise ServerError(404, "panel desconocido")
        if self.demo:
            p = dict(DEMO_PANELS.get(name, {"title": name, "lines": ["DEMO: sin datos reales"], "speak": "Este panel está en demostración.", "sensitive": True})); p.update(panel=name, demo=True)
            return p
        if not self.client.url or not self._token():
            raise ServerError(503, "Sin datos reales: configura y empareja el equipo")
        p = self.client.panel(name)
        lines = [str(x)[:500] for x in (p.get("lines") or [])][:80]
        return {"panel": name, "title": str(p.get("title", name))[:80], "lines": lines,
                "speak": engines.speakable(p.get("speak", "")), "sensitive": bool(p.get("sensitive")),
                "as_of": p.get("as_of"), "demo": False}

    # --- speech ---
    def transcribe(self, wav):
        return self.stt.transcribe(wav, retain_dir=(self.home / "audio") if self.retain else None)

    def speak(self, text, turn_id=None, sensitive=False):
        """Synthesize and tell the audio window to play it. Text stays on screen if voice fails."""
        with self.lock:
            discreet = self.prefs["discreet"]; rate = self.prefs["rate"]; owner = self.owner
        if discreet and (sensitive or re.search(r"\d", text or "")):
            text = "Te lo dejé en pantalla."
        if not owner or self.tts.problem():
            return None
        try:
            audio, ctype = self.tts.synthesize(text, rate=rate)
        except engines.EngineError as e:
            self.emit({"type": "state", "state": "error", "detail": f"voz: {e}"}); return None
        aid = uuid.uuid4().hex
        with self.lock:
            if turn_id and self.turns.get(turn_id, {}).get("cancelled"):
                return None                                  # cancelled while synthesizing: never plays
            self.audio[aid] = (audio, ctype)
            for old in list(self.audio)[:-10]:
                self.audio.pop(old, None)
            self.last["audio"] = aid
        self.emit({"type": "audio.play", "id": aid, "turn": turn_id})
        return aid

    # --- turns ---
    def start_turn(self, request_id, text, source="text"):
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", str(request_id or "")):
            raise ValueError("request_id inválido")
        text = str(text or "").strip()
        if not text or len(text) > 1000:
            raise ValueError("texto vacío o demasiado largo")
        with self.lock:
            t = self.turns.get(request_id)
            if t:
                if t["text"] != text:
                    raise ValueError("ese request_id ya se usó con otro texto")
                return {"turn_id": request_id, "state": t["state"]}     # window reload / double click: no repeat
            if any(x["state"] in ("accepted", "consultando") for x in self.turns.values()):
                raise ValueError("ya hay una consulta en curso")
            self.turns[request_id] = {"text": text, "state": "accepted", "cancelled": False, "source": source,
                                      "at": time.time()}
            for old in sorted(self.turns, key=lambda k: self.turns[k]["at"])[:-100]:
                self.turns.pop(old, None)
        self.emit({"type": "transcript.final", "turn": request_id, "text": text})
        threading.Thread(target=self._run_turn, args=(request_id, text), daemon=True).start()
        return {"turn_id": request_id, "state": "accepted"}

    def cancel_turn(self, turn_id):
        with self.lock:
            t = self.turns.get(turn_id)
            if not t:
                raise KeyError(turn_id)
            done = t["state"] in ("done", "error")
            t["cancelled"] = True
        self.emit({"type": "audio.stop", "turn": turn_id})
        self.emit({"type": "turn.cancelled", "turn": turn_id})
        return {"cancelled": True, "already_done": done,
                "note": ("La respuesta ya había llegado; solo detuve el audio." if done else
                         "No mostraré ni leeré la respuesta cuando llegue. Esta vía es de solo consulta: "
                         "no había ninguna acción que deshacer.")}

    def _finish(self, tid, state, reply=None, sensitive=False, events=(), llm=False, panel_data=None):
        with self.lock:
            t = self.turns[tid]; t["state"] = state; cancelled = t["cancelled"]
            if reply is not None:
                t["reply"] = reply
        if cancelled:
            self.emit({"type": "turn.late", "turn": tid}); return     # never shown or spoken
        if panel_data:
            self.emit({"type": "panel.open", "turn": tid, "data": panel_data})
        for e in events:
            if e["type"] == "panel.open":
                try:
                    self.emit({"type": "panel.open", "turn": tid, "data": self.panel(e["panel"])})
                except ServerError as err:
                    self.emit({"type": "state", "state": "error", "detail": err.detail})
        if reply is not None:
            with self.lock:
                self.last["text"] = reply
            self.emit({"type": "reply.text", "turn": tid, "text": reply, "llm": llm, "sensitive": sensitive})
            self.emit({"type": "state", "state": "hablando" if not self.tts.problem() else "listo"})
            self.speak(reply, turn_id=tid, sensitive=sensitive)
        self.emit({"type": "turn.done" if state == "done" else "turn.error", "turn": tid})
        self.emit({"type": "state", "state": "listo"})

    def _run_turn(self, tid, text):
        with self.lock:
            self.turns[tid]["state"] = "consultando"
        self.emit({"type": "state", "state": "consultando", "turn": tid})
        kind, arg = intents.parse(text)
        try:
            if kind == "stop_audio":
                self.emit({"type": "audio.stop"}); return self._finish(tid, "done")
            if kind == "mic_off":
                self.set_prefs(mic=False); self.emit({"type": "mic.off"})
                return self._finish(tid, "done", "Apagué el micrófono.")
            if kind == "mic_on":                                   # 4.0.5 (3.4)
                self.set_prefs(mic=True); self.emit({"type": "mic.on"})
                return self._finish(tid, "done", "Micrófono encendido. Pulsa Hablar o la barra espaciadora.")
            if kind in ("discreet_on", "discreet_off"):
                self.set_prefs(discreet=kind == "discreet_on")
                return self._finish(tid, "done", "Modo discreto activado: no leeré montos ni códigos." if kind == "discreet_on"
                                    else "Modo discreto desactivado.")
            if kind == "health":
                return self._finish(tid, "done", self.local_health_text())
            if kind == "repeat":
                with self.lock:
                    aid, last = self.last["audio"], self.last["text"]
                if aid and aid in self.audio:
                    self.emit({"type": "audio.play", "id": aid, "turn": tid}); return self._finish(tid, "done")
                return self._finish(tid, "done", last or "Todavía no he dicho nada.")
            if kind in ("slower", "faster"):
                self.set_prefs(rate=self.prefs["rate"] + (-0.15 if kind == "slower" else 0.15))
                return self._finish(tid, "done", "Listo, hablaré más despacio." if kind == "slower"
                                    else "Listo, hablaré más rápido.")
            if kind == "refuse":
                return self._finish(tid, "done", arg)
            if kind == "panel":
                p = self.panel(arg)
                return self._finish(tid, "done", p.get("speak") or p["title"], sensitive=p.get("sensitive", False),
                                    panel_data=p)
            if kind == "empty":
                return self._finish(tid, "done", "No te escuché.")
            if self.demo:
                return self._finish(tid, "done", "DEMO: no estoy conectado a tu Jarvis, así que no consulto tus "
                                                 "datos. Prueba «abre la agenda» para ver un panel de ejemplo.")
            if not self.client.url or not self._token():
                return self._finish(tid, "error", "Sin conexión real con Jarvis. Configura y empareja este equipo; no se ejecutó ninguna acción.")
            r = self.client.turn(tid, text)
            state = r.get("state")
            if state == "uncertain":
                return self._finish(tid, "error", r.get("reply") or "No sé si Jarvis contestó; pregúntame otra vez.")
            if state == "running":
                return self._finish(tid, "error", "Jarvis todavía está trabajando en esa consulta; intenta en un momento.")
            self._finish(tid, "done" if state == "done" else "error", str(r.get("reply") or "")[:4000],
                         sensitive=bool(r.get("sensitive")), events=safe_events(r.get("events")),
                         llm=bool(r.get("llm_used")))
        except ServerError as e:
            if e.status == 401:
                self._auth_lost(e.detail)
            msg = ("No pude hablar con Jarvis (sin conexión). Tu pregunta no se repetirá sola; inténtalo otra vez."
                   if e.status == 0 else f"Jarvis respondió con un error: {e.detail}")
            self.emit({"type": "state", "state": "sin conexión" if e.status == 0 else "error"})
            self._finish(tid, "error", msg)
        except Exception as e:                                   # never leave a turn stuck
            log.warning("turn failed: %s", type(e).__name__)
            self._finish(tid, "error", "Algo falló en el panel local; inténtalo otra vez.")


INDEX_401 = (b"<!doctype html><meta charset=utf-8><title>Jarvis</title><body style='background:#071426;color:#cfe;"
             b"font:18px system-ui;padding:40px'><h1>Jarvis</h1><p>Abre el enlace que muestra la terminal "
             b"(sirve una sola vez y vence en 2 minutos). Si se venci\xc3\xb3, reinicia el panel.</p>")


def make_handler(app, host, port):
    allowed_hosts = {f"{host}:{port}", f"localhost:{port}", f"127.0.0.1:{port}"}
    origins = {f"http://{h}" for h in allowed_hosts}

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "jarvis-desktop"
        sys_version = ""

        def log_message(self, fmt, *args):          # path only (never bodies or cookies); launch token removed
            log.info("%s %s", self.command, self.path.split("?")[0])

        # --- helpers ---
        def _send(self, code, body=b"", ctype="application/json; charset=utf-8", headers=None):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'self'; media-src 'self' blob:; "
                             "img-src 'self' data: blob:; style-src 'self'; "
                             "script-src 'self' 'wasm-unsafe-eval' https://cdn.jsdelivr.net; "
                             "connect-src 'self' https://cdn.jsdelivr.net https://storage.googleapis.com; "
                             "worker-src 'self' blob:; frame-ancestors 'none'")
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _cookie(self):
            for part in (self.headers.get("Cookie") or "").split(";"):
                k, _, v = part.strip().partition("=")
                if k == "jd_session":
                    return v
            return ""

        def _guard(self, post=False):
            if self.headers.get("Host") not in allowed_hosts:
                self._send(400, {"error": "host no permitido"}); return False
            if post:
                origin = self.headers.get("Origin")
                if self.headers.get("X-Jarvis-UI") != "1" or (origin is not None and origin not in origins):
                    self._send(403, {"error": "origen no permitido"}); return False
            if not app.session_ok(self._cookie()):
                self._send(401, {"error": "sesión no válida"}); return False
            return True

        def _json(self, limit=16384):
            n = int(self.headers.get("Content-Length") or 0)
            if n > limit:
                raise ValueError("solicitud demasiado grande")
            data = json.loads(self.rfile.read(n) or b"{}")
            if not isinstance(data, dict):
                raise ValueError("JSON inválido")
            return data

        # --- GET ---
        def do_GET(self):
            u = urllib.parse.urlsplit(self.path); q = urllib.parse.parse_qs(u.query)
            if self.headers.get("Host") not in allowed_hosts:
                return self._send(400, {"error": "host no permitido"})
            if u.path == "/" and "launch" in q:
                sid = app.use_launch(q["launch"][0])
                if not sid:
                    return self._send(401, INDEX_401, "text/html; charset=utf-8")
                return self._send(303, b"", headers={"Location": "/", "Set-Cookie":
                                  f"jd_session={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}"})
            if u.path in ("/", "/hud", "/avatar"):                       # /hud = second monitor (4.0.5, 3.2)
                if not app.session_ok(self._cookie()):
                    return self._send(401, INDEX_401, "text/html; charset=utf-8")
                page = {"/": "index.html", "/hud": "hud.html", "/avatar": "avatar.html"}[u.path]
                return self._send(200, (HERE / "ui" / page).read_bytes(), "text/html; charset=utf-8")
            if not self._guard():
                return
            if u.path.startswith("/ui/") and u.path[4:] in UI_FILES:
                return self._send(200, (HERE / "ui" / u.path[4:]).read_bytes(), UI_FILES[u.path[4:]])
            if u.path == "/api/hand-mouse/status":
                return self._send(200, app.hand_mouse.status())
            if u.path == "/api/state":
                return self._send(200, app.state())
            if u.path == "/api/hud":
                try:
                    return self._send(200, app.hud())
                except ServerError as e:
                    return self._send(e.status if e.status >= 400 else 502, {"error": e.detail})
            if u.path == "/api/events":
                try:
                    since = int(q.get("since", ["0"])[0])
                except ValueError:
                    since = 0
                window = (q.get("window", [""])[0] or "")[:64]
                return self._send(200, app.poll(since, window))
            m = re.fullmatch(r"/api/panels/([a-z]+)", u.path)
            if m:
                try:
                    return self._send(200, app.panel(m.group(1)))
                except ServerError as e:
                    return self._send(e.status if e.status >= 400 else 502, {"error": e.detail})
            m = re.fullmatch(r"/voice/audio/([0-9a-f]{32})", u.path)
            if m:
                with app.lock:
                    item = app.audio.get(m.group(1))
                return self._send(200, item[0], item[1]) if item else self._send(404, {"error": "no existe"})
            self._send(404, {"error": "no existe"})

        # --- POST ---
        def do_POST(self):
            u = urllib.parse.urlsplit(self.path)
            if not self._guard(post=True):
                return
            try:
                if u.path == "/voice/transcribe":
                    n = int(self.headers.get("Content-Length") or 0)
                    if n > 44 + 16000 * 2 * 60:
                        return self._send(413, {"error": "audio demasiado largo"})
                    if (self.headers.get("Content-Type") or "").split(";")[0] not in ("audio/wav", "audio/x-wav"):
                        return self._send(415, {"error": "se espera audio/wav"})
                    wav = self.rfile.read(n)
                    app.emit({"type": "state", "state": "transcribiendo"})
                    out = app.transcribe(wav); out["id"] = uuid.uuid4().hex
                    app.emit({"type": "state", "state": "listo"})
                    return self._send(200, out)
                data = self._json()
                if u.path.startswith("/api/hand-mouse/"):
                    if host not in ("127.0.0.1", "localhost", "::1") or self.headers.get("Origin") not in origins:
                        return self._send(403, {"error": "el puntero requiere origen local explícito"})
                    try:
                        if u.path == "/api/hand-mouse/arm":
                            out = app.hand_mouse.arm(self._cookie(), data)
                        elif u.path == "/api/hand-mouse/frame":
                            out = app.hand_mouse.frame(self._cookie(), data)
                        elif u.path == "/api/hand-mouse/stop":
                            out = app.hand_mouse.stop(self._cookie(), data.get("lease"))
                        else:
                            return self._send(404, {"error": "acción no disponible"})
                        return self._send(200, out)
                    except RuntimeError as exc:
                        return self._send(503, {"error": str(exc)})
                if u.path == "/voice/synthesize":
                    audio, ctype = app.tts.synthesize(str(data.get("text", ""))[:1500], rate=app.prefs["rate"])
                    return self._send(200, audio, ctype)
                if u.path == "/conversation/turns":
                    return self._send(202, app.start_turn(data.get("request_id"), data.get("text"),
                                                          data.get("source", "text")))
                m = re.fullmatch(r"/conversation/turns/([A-Za-z0-9_-]{8,64})/cancel", u.path)
                if m:
                    return self._send(200, app.cancel_turn(m.group(1)))
                if u.path == "/api/window/hello":
                    return self._send(200, app.hello(str(data.get("window", ""))[:64]))
                if u.path == "/api/audio/claim":
                    return self._send(200, app.claim_audio(str(data.get("window", ""))[:64]))
                if u.path == "/api/open":
                    return self._send(200, app.open_detail(str(data.get("target", ""))[:20]))
                if u.path == "/api/alerts/repeat":
                    return self._send(200, app.alert_repeat())
                if u.path == "/api/alerts/silence":
                    app.emit({"type": "audio.stop"}); return self._send(200, {"ok": True})
                if u.path == "/api/pulse":
                    app.pulse_once(); return self._send(200, app.health_view())
                if u.path == "/api/audio/stop":
                    app.emit({"type": "audio.stop"}); return self._send(200, {"ok": True})
                if u.path == "/api/prefs":
                    return self._send(200, app.set_prefs(**{k: data[k] for k in ("rate", "discreet", "review", "mic")
                                                            if k in data}))
                if u.path == "/api/pair/start":
                    return self._send(200, app.pair_start())
                if u.path == "/api/pair/remove":
                    app.unpair(); return self._send(200, {"ok": True})
                self._send(404, {"error": "no existe"})
            except (AudioError, engines.EngineError) as e:
                app.emit({"type": "state", "state": "error", "detail": str(e)})
                self._send(503 if isinstance(e, engines.EngineError) else 400, {"error": str(e)})
            except ServerError as e:
                self._send(e.status if 400 <= e.status < 500 else 502, {"error": e.detail})
            except KeyError:
                self._send(404, {"error": "no existe"})
            except ValueError as e:
                self._send(400, {"error": str(e)[:200]})

    return Handler


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(cfg, open_browser=True):
    host = check_bind(cfg["VOICE_BIND_HOST"], truthy(cfg["VOICE_ALLOW_LAN"]))
    port = int(cfg["VOICE_PORT"])
    app = Companion(cfg)
    httpd = Server((host, port), http.server.BaseHTTPRequestHandler)
    real_port = httpd.server_address[1]                  # differs from port only when port is 0 (tests)
    httpd.RequestHandlerClass = make_handler(app, host, real_port)
    return app, httpd, real_port


def check_mac():
    """Measure before choosing models: no installs, no network."""
    def run(cmd):
        try:
            return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=10,
                                  check=False).stdout.decode(errors="replace").strip()
        except (OSError, subprocess.TimeoutExpired):
            return ""
    cfg = load_config()
    print("Jarvis desktop — comprobación de este equipo")
    print(f"• Sistema: {platform.platform()}  ({run(['sw_vers', '-productVersion']) or 'sw_vers no disponible'})")
    print(f"• CPU: {run(['sysctl', '-n', 'machdep.cpu.brand_string']) or platform.processor() or platform.machine()}")
    mem = run(["sysctl", "-n", "hw.memsize"])
    print(f"• Memoria: {int(mem) // 2 ** 30} GB" if mem.isdigit() else "• Memoria: no disponible")
    print(f"• Python: {platform.python_version()} ({sys.executable})" +
          ("" if sys.version_info >= (3, 8) else "  ⚠️ se necesita 3.8 o más"))
    voices = [v for v in run(["say", "-v", "?"]).splitlines() if re.search(r"\bes[_-]", v)]
    print(f"• Comando say: {'sí' if shutil.which('say') else 'no (solo existe en macOS)'}")
    print("• Voces en español del sistema: " + (", ".join(v.split()[0] for v in voices) or "ninguna encontrada"))
    # 4.0.5 (3.6): microphone and monitors, read from the system report (nothing is recorded)
    audio = run(["system_profiler", "SPAudioDataType"])
    mics = len(re.findall(r"Input Channels", audio))
    print("• Micrófono: " + (f"{mics} entrada(s) de audio detectada(s)" if mics else
                             "no detectado aquí (system_profiler no disponible o sin entrada)") +
          ". El permiso real lo pide Safari al pulsar Hablar.")
    shown = run(["system_profiler", "SPDisplaysDataType"])
    screens = len(re.findall(r"Resolution:", shown))
    print("• Monitores: " + (f"{screens} detectado(s)" + (" — puedes abrir el HUD en el segundo" if screens > 1 else
                                                           " — el HUD se puede abrir en otra ventana")
                             if screens else "no detectados aquí (system_profiler no disponible)"))
    stt, tts = engines.build(cfg)
    print(f"• STT ({cfg['VOICE_STT_BACKEND']}): " + (stt.problem() or "listo"))
    if cfg["VOICE_STT_BACKEND"] == "whisper_cpp" and not stt.problem():
        helptext = run([stt.binary, "--help"]) + run([stt.binary, "-h"])
        missing = [f for f in ("-nt", "-np", "-otxt", "-of", "-l", "-t") if f not in helptext]
        print("  Opciones de whisper-cli que usa el panel: " +
              ("todas presentes" if not missing else "⚠️ faltan " + ", ".join(missing) + " (versión distinta)"))
    print(f"• TTS ({cfg['VOICE_TTS_BACKEND']}): " + (tts.problem() or "listo"))
    print(f"• ffmpeg: {'sí' if shutil.which('ffmpeg') else 'no (no hace falta: el panel envía WAV 16 kHz)'}")
    print(f"• Servidor: {cfg.get('JARVIS_SERVER_URL') or 'no configurado'} · emparejado: "
          f"{'sí' if (cfg.get('JARVIS_DEVICE_TOKEN') or TokenStore(cfg['VOICE_HOME']).load()) else 'no'}")


def bench(path):
    cfg = load_config(); stt, _ = engines.build(cfg)
    wav = Path(path).read_bytes(); secs = check_wav(wav)
    t0 = time.time(); out = stt.transcribe(wav); dt = time.time() - t0
    print(f"Audio {secs:.1f}s · cálculo {dt:.1f}s · RTF {dt / secs:.2f} (menos de 1 = más rápido que tiempo real)")
    print(f"Texto: {out['text']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Jarvis desktop companion")
    ap.add_argument("--config"); ap.add_argument("--check", action="store_true")
    ap.add_argument("--bench"); ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--hand-mouse", action="store_true", help="habilita pruebas locales del puntero, sin clics")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if a.check:
        return check_mac()
    if a.bench:
        return bench(a.bench)
    cfg = load_config(a.config)
    if a.hand_mouse:
        if sys.platform != "darwin" or cfg["VOICE_BIND_HOST"] not in ("127.0.0.1", "localhost", "::1") or truthy(cfg["VOICE_DEMO"]):
            raise SystemExit("--hand-mouse solo se permite localmente en macOS, fuera de DEMO.")
        cfg["_HAND_MOUSE_ENABLED"] = True
    if truthy(cfg["VOICE_WAKE_WORD_ENABLED"]):
        print("Aviso: la palabra de activación aún no está implementada (fase 2); se ignora.")
    app, httpd, port = serve(cfg)
    host = cfg["VOICE_BIND_HOST"]
    link = f"http://{host}:{port}/?launch={app.new_launch()}"
    print(f"\nJarvis panel listo. Abre este enlace (sirve una vez, 2 minutos):\n  {link}\n"
          "Para otra ventana/monitor, abre la misma dirección sin ?launch en el mismo navegador.\n"
          "Ctrl+C para cerrar.", flush=True)
    stop = threading.Event()
    threading.Thread(target=app.pulse_loop, args=(stop,), daemon=True).start()   # status + alerts every 3 min
    if not a.no_browser:
        webbrowser.open(link)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.hand_mouse.close()
        httpd.server_close()


if __name__ == "__main__":
    main()
