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

import account_navigation
import intents                                    # noqa: E402
import documentos                                # noqa: E402
from hand_mouse import HandMouse                  # noqa: E402
from audio import engines, latencia, una_voz      # noqa: E402
from audio.wav import AudioError, check_wav       # noqa: E402
import negocios                                  # noqa: E402
import paneles                                   # noqa: E402
import mouse_autonomo                            # noqa: E402
import ciclo                                     # noqa: E402
from jarvis_client import JarvisClient, ServerError, TokenStore, check_url, safe_events, PANELS  # noqa: E402

VERSION = "desktop-1"
log = logging.getLogger("jarvis.desktop")
UI_FILES = {"crystal-motion.js": "text/javascript; charset=utf-8", "crystal.css": "text/css; charset=utf-8", "crystal.js": "text/javascript; charset=utf-8", "crystal-core.jpg": "image/jpeg", "gestures.js": "text/javascript; charset=utf-8", "hud.css": "text/css; charset=utf-8", "reactor.js": "text/javascript; charset=utf-8", "startup.js": "text/javascript; charset=utf-8", "hand-mouse.js": "text/javascript; charset=utf-8", "hand-worker.js": "text/javascript; charset=utf-8", "atlas.js": "text/javascript; charset=utf-8", "avatar.css": "text/css; charset=utf-8", "avatar.js": "text/javascript; charset=utf-8", "hands.js": "text/javascript; charset=utf-8", "app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8",
            "hud.js": "text/javascript; charset=utf-8", "mask.js": "text/javascript; charset=utf-8",
            "wav.js": "text/javascript; charset=utf-8", "lipsync.js": "text/javascript; charset=utf-8",
            "torre.css": "text/css; charset=utf-8", "torre.js": "text/javascript; charset=utf-8",   # display Torre
            "torre.jpg": "image/jpeg",
            "orbe.js": "text/javascript; charset=utf-8", "negocios.js": "text/javascript; charset=utf-8", "torre-pisos.js": "text/javascript; charset=utf-8", "negocios.css": "text/css; charset=utf-8", "orbe.css": "text/css; charset=utf-8",   # orbe holográfico
            "mercado.css": "text/css; charset=utf-8", "mercado.js": "text/javascript; charset=utf-8",   # gráfica holográfica
            "cielo.js": "text/javascript; charset=utf-8",                                         # fondo de galaxia
            "mecanismo.js": "text/javascript; charset=utf-8",                                     # núcleo y emblema azul
            "hudx.js": "text/javascript; charset=utf-8",
            "ironman.css": "text/css; charset=utf-8", "ironman.js": "text/javascript; charset=utf-8",  # holograma + torre
            "aincrad.js": "text/javascript; charset=utf-8", "nucleo.js": "text/javascript; charset=utf-8", "nucleo-gl.js": "text/javascript; charset=utf-8", "nucleo.css": "text/css; charset=utf-8", "nucleo-home.js": "text/javascript; charset=utf-8", "nucleo-home.css": "text/css; charset=utf-8", "nucleo-modo.js": "text/javascript; charset=utf-8", "arranque.js": "text/javascript; charset=utf-8", "torre-aincrad.js": "text/javascript; charset=utf-8", "torre-aincrad.css": "text/css; charset=utf-8", "torre-cine.js": "text/javascript; charset=utf-8", "paneles.js": "text/javascript; charset=utf-8", "paneles.css": "text/css; charset=utf-8"}
VENDOR_FILES = {p.relative_to(HERE / "ui" / "vendor").as_posix(): "text/javascript; charset=utf-8"
                for p in sorted((HERE / "ui" / "vendor" / "three").rglob("*.js"))}   # todo three/**.js (MIT, local)
# Texturas CC0 (ambientCG) y HDRI CC0 (Poly Haven) de la torre cine: lista cerrada, misma bandera que vendor.
ASSET_FILES = {**{f"piedra-{n}.jpg": "image/jpeg" for n in ("color", "normal", "rugosidad", "ao")},
               **{f"roca-{n}.jpg": "image/jpeg" for n in ("color", "normal", "rugosidad")},
               "noche-1k.hdr": "application/octet-stream"}
IRONMAN_LINK = re.compile(rb"<!--ironman-->.*?<!--/ironman-->", re.S)                                          # HUD v2: barras y medidores
LAUNCH_TTL = 120
SESSION_TTL = 12 * 3600
WINDOW_STALE = 30
RATE_MIN, RATE_MAX = 0.7, 1.4
DEFAULTS = {"VOICE_BIND_HOST": "127.0.0.1", "VOICE_PORT": "8765", "VOICE_STT_BACKEND": "none",
            "VOICE_TTS_BACKEND": "auto", "JARVIS_REPLY_LANGUAGE": "en-GB", "VOICE_STT_LANGUAGE": "en", "VOICE_WAKE_WORD_ENABLED": "false", "VOICE_RETAIN_AUDIO": "false",
            "VOICE_AUTO_CAMERA": "false", "VOICE_STARTUP_AUDIO": "false", "VOICE_STARTUP_GREETING": "true", "JARVIS_FONDO": "true", "VOICE_SERVER_PLAYBACK": "auto", "VOICE_DEMO": "false", "VOICE_ALLOW_LAN": "false", "VOICE_HOME": str(Path.home() / ".jarvis-desktop"),
            "JARVIS_AVATAR_IRONMAN": "0"}   # holograma + Torre de Aincrad en /avatar/ironman: apagado por defecto (revisado)

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
                 "speak": "Panel de práctica de ejemplo.", "sensitive": False, "chart": None},
}


def _crear_stop_mouse():
    """Crea ~/.jarvis-control/STOP (o JARVIS_CONTROL_DIR/STOP). El ejecutor del mouse no mueve nada con STOP."""
    raw = os.environ.get("JARVIS_CONTROL_DIR", "").strip()
    folder = Path(raw) if raw else Path.home() / ".jarvis-control"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "STOP").write_text("parado por voz\n", encoding="utf-8")


def _num(v, low=-1e12, high=1e12):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and low <= x <= high else None


_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}[0-9:+\-.Z]{0,15}")


def clean_chart(raw):
    """Gráfica de la práctica: solo números finitos, fechas con forma de fecha y listas cortas. Nada se ejecuta."""
    if not isinstance(raw, dict) or raw.get("mode") != "practice":
        return None
    equity = []
    for e in (raw.get("equity") or [])[-400:]:
        if isinstance(e, dict) and isinstance(e.get("t"), str) and _STAMP.fullmatch(e["t"]):
            v = _num(e.get("v"), 0)
            if v is not None:
                equity.append({"t": e["t"], "v": round(v, 2)})
    trades = [{"t": t["t"], "side": t["side"], "product": str(t.get("product") or "")[:12]}
              for t in (raw.get("trades") or [])[-60:]
              if isinstance(t, dict) and t.get("side") in ("buy", "sell") and isinstance(t.get("t"), str)
              and _STAMP.fullmatch(t["t"])]
    products = []
    for m in (raw.get("products") or [])[:6]:
        if isinstance(m, dict) and re.fullmatch(r"[A-Z0-9]{2,10}-[A-Z]{3,5}", str(m.get("product") or "")):
            products.append({"product": m["product"], "price": _num(m.get("price"), 0),
                             "change_24h_pct": _num(m.get("change_24h_pct"), -1000, 1000),
                             "rsi": _num(m.get("rsi"), 0, 100),
                             "trend": m.get("trend") if m.get("trend") in ("alcista", "bajista", "lateral") else None,
                             "open": bool(m.get("open"))})
    raw_sum = raw.get("summary") if isinstance(raw.get("summary"), dict) else {}
    keys = ("equity", "pnl_total", "pnl_pct", "win_rate_pct", "vs_buy_and_hold", "closed_trades", "max_drawdown_pct",
            "drawdown_now_pct", "profit_factor", "expectancy", "fees_share_pct")
    summary = {k: _num(raw_sum.get(k)) for k in keys}
    summary["sample_ok"] = bool(raw_sum.get("sample_ok"))
    paused = raw.get("paused") if raw.get("paused") in ("drawdown", "daily_loss") else None
    return {"mode": "practice", "start": _num(raw.get("start"), 0), "equity": equity, "trades": trades,
            "products": products, "summary": summary, "paused": paused}


_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_JOB_STATUS = ("quote", "confirmed", "in_progress", "delivered", "invoiced")


def clean_jobs(raw):
    """Trabajos abiertos para las barras del HUD: texto corto, etapa conocida, avance 0-100 y fechas con forma de fecha."""
    out = []
    for j in (raw if isinstance(raw, list) else [])[:10]:
        if not isinstance(j, dict) or j.get("status") not in _JOB_STATUS:
            continue
        p = _num(j.get("progress"), 0, 100)
        out.append({"id": int(_num(j.get("id"), 0, 1e9) or 0), "title": str(j.get("title") or "")[:80],
                    "status": j["status"], "stage": str(j.get("stage") or "")[:20], "progress": int(p or 0),
                    "start": j["start"] if isinstance(j.get("start"), str) and _DATE.fullmatch(j["start"]) else None,
                    "due": j["due"] if isinstance(j.get("due"), str) and _DATE.fullmatch(j["due"]) else None,
                    "overdue": bool(j.get("overdue")), "due_date": j.get("due_date"), "created": j.get("created")})
    return out


def _demo_jobs():
    import datetime as _dt
    t = _dt.date.today()
    d = lambda n: (t + _dt.timedelta(days=n)).isoformat()
    rows = [("Cliente Ejemplo — Baño", "in_progress", "En progreso", 50, -6, -1, True),
            ("Cliente Ejemplo — Cocina", "delivered", "Entregado", 75, -10, 2, False),
            ("Oficina Ejemplo — Pintura", "confirmed", "Confirmado", 25, -2, 6, False),
            ("Local Ejemplo — Gabinetes", "quote", "Cotización", 10, 0, 11, False),
            ("Cliente Ejemplo — Losa", "invoiced", "Facturado", 90, -14, 1, False)]
    return [{"id": i, "title": r[0] + " (ejemplo)", "status": r[1], "stage": r[2], "progress": r[3],
             "start": d(r[4]), "due": d(r[5]), "overdue": r[6]} for i, r in enumerate(rows, 1)]


DEMO_JOBS = _demo_jobs()


def _demo_dd(values):
    peak, worst = values[0], 0.0
    for v in values:
        peak = max(peak, v); worst = max(worst, (peak - v) / peak * 100)
    return round(worst, 2), round((peak - values[-1]) / peak * 100, 2)


def _demo_chart():
    """Curva de EJEMPLO para el modo demo. No son datos de nadie."""
    import math as _m
    pts, v = [], 1000.0
    for i in range(168):
        v *= 1 + 0.0016 * _m.sin(i / 9) + 0.0009 * _m.cos(i / 4.3) - 0.0004
        day, hour = 1 + i // 24, i % 24
        pts.append({"t": f"2026-10-{day:02d}T{hour:02d}:00", "v": round(v, 2)})
    return {"mode": "practice", "start": 1000.0, "equity": pts,
            "trades": [{"t": pts[30]["t"], "side": "buy", "product": "BTC-USD"},
                       {"t": pts[71]["t"], "side": "sell", "product": "BTC-USD"},
                       {"t": pts[118]["t"], "side": "buy", "product": "ETH-USD"}],
            "products": [{"product": "BTC-USD", "price": None, "change_24h_pct": None, "rsi": 58.0, "trend": "alcista", "open": False},
                         {"product": "ETH-USD", "price": None, "change_24h_pct": None, "rsi": 49.0, "trend": "lateral", "open": True},
                         {"product": "SOL-USD", "price": None, "change_24h_pct": None, "rsi": 37.0, "trend": "bajista", "open": False}],
            "summary": {"equity": pts[-1]["v"], "pnl_total": round(pts[-1]["v"] - 1000, 2),
                        "max_drawdown_pct": _demo_dd([p["v"] for p in pts])[0],
                        "drawdown_now_pct": _demo_dd([p["v"] for p in pts])[1],
                        "pnl_pct": round((pts[-1]["v"] / 1000 - 1) * 100, 2), "win_rate_pct": 50.0,
                        "vs_buy_and_hold": None, "closed_trades": 2,
                        "profit_factor": 0.6, "expectancy": -4.2, "fees_share_pct": None, "sample_ok": False},
            "paused": None}


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
                               "VOICE_STT_THREADS", "VOICE_STT_FAST", "VOICE_TTS_VOICE", "VOICE_PIPER_BIN", "VOICE_PIPER_DIR", "JARVIS_STARTUP_SOUND",
                               "VOICE_CICLO", "VOICE_CICLO_DIR", "VOICE_PIPER_LENGTH_SCALE"]:
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


ALERT_MODE_S = 30 * 60
BAD_SERVER = ("error", "down", "offline")


def local_player(which=shutil.which):
    """afplay en la Mac; paplay/aplay en Linux. None si no hay altavoz local."""
    for cmd in (["afplay"], ["paplay"], ["aplay", "-q"]):
        if which(cmd[0]):
            return cmd
    return None


SOUND_TYPES = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".ogg": "audio/ogg", ".m4a": "audio/mp4"}
GREETING = "Buenas, señor. Todo listo."


def startup_sound(cfg):
    """Archivo propio del dueño (JARVIS_STARTUP_SOUND, local y fuera de Git) o el encendido original del repo
    (desktop/ui/audio/encendido.wav, síntesis propia). JARVIS_STARTUP_SOUND=off = sin sonido."""
    own = str(cfg.get("JARVIS_STARTUP_SOUND", "") or "").strip()
    if own.lower() in ("off", "none", "0", "false"):
        return None
    if own:
        p = Path(own).expanduser()
        if p.is_file() and p.suffix.lower() in SOUND_TYPES and p.stat().st_size <= 20 * 2 ** 20:
            return p, SOUND_TYPES[p.suffix.lower()]
    if str(cfg.get("JARVIS_ARRANQUE", "") or "").strip().lower() == "rock":
        rock = HERE / "ui" / "audio" / "arranque-rock.wav"  # intro rock original (scripts/gen_arranque_rock.py)
        if rock.is_file():
            return rock, "audio/wav"
    default = HERE / "ui" / "audio" / "encendido.wav"
    return (default, "audio/wav") if default.is_file() else None


def native_intro(app, cfg):
    """Al iniciar el servicio: música por los altavoces, saludo corto encima y la música se corta al terminar."""
    proc, player = None, local_player()
    snd = startup_sound(cfg)
    if snd and player and player[0] == "afplay":
        try:
            proc = subprocess.Popen(["afplay", "-v", "0.35", str(snd[0])],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            proc = None
    start = time.time()
    time.sleep(3.0 if proc else 0.5)
    try:
        audio, _ = app.tts.synthesize(GREETING, rate=app.prefs.get("rate", 1.0))
        app._play_local(audio)
        until = time.time() + _wav_secs(audio) + 1.0
    except Exception:
        until = time.time() + 1.0
    while time.time() < min(until, start + 15.0) and proc and proc.poll() is None:
        time.sleep(0.2)
    if proc and proc.poll() is None:
        proc.terminate()


def core_mode(server_state, last_alert_at, now):
    """Núcleo: "jarvis" (azul) normal; "ultron" (rojo/naranja) con aviso reciente o servidor caído."""
    if server_state in BAD_SERVER:
        return "ultron"
    if last_alert_at and now - last_alert_at < ALERT_MODE_S:
        return "ultron"
    return "jarvis"


CRIPTO_RE = {"BTC": r"\b(btc|bitcoin)\b", "ETH": r"\b(eth|ether|ethereum)\b", "SOL": r"\b(sol|solana)\b"}


def speech_topics(text):
    """Temas de una frase para que los rayos del núcleo apunten (cripto o negocio). Devuelve solo etiquetas."""
    t = str(text or "").lower(); out = [k for k, rx in CRIPTO_RE.items() if re.search(rx, t)]
    try:
        for n in negocios.torre().get("negocios", []):
            name = str(n.get("nombre", "")).lower()
            if name and name in t:
                out.append("negocio:" + str(n.get("id")))
    except Exception:
        pass
    return out[:4]


_VOZ_INIT_LOCK = threading.Lock()


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
        self.avatar_ironman = truthy(cfg.get("JARVIS_AVATAR_IRONMAN", "0"))
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
        self.health = {"state": "demo" if self.demo else "unknown", "latency_ms": None, "last_ok": None,
                       "info": dict(DEMO_STATUS) if self.demo else {}}       # la demo muestra su estado de ejemplo desde el inicio
        self.hud_cache = []
        self.last_alert = None; self.last_alert_at = 0.0
        self.alerts_seen = self._load_seen()
        self.voz = {"estado": "idle", "idioma": "es", "lineas": [], "corte": False}

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
                self.last_alert = fresh[-1]; self.last_alert_at = time.time()
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
        raw_jobs = None; jobs_count = None; as_of = None
        if self.demo:
            cards = [dict(c, as_of="", stale=c.get("stale", False), sensitive=False, demo=True) for c in DEMO_HUD]
        elif not self.client.url or not self._token():
            cards = []  # Missing connection is not permission to fabricate business data.
        else:
            got = self.client.hud()
            raw = got.get("cards") or []
            raw_jobs = got.get("jobs")
            jobs_count = got.get("jobs_count")
            as_of = got.get("as_of")
            cards = []
            for c in raw:
                if not isinstance(c, dict) or c.get("id") not in HUD_IDS:
                    continue
                cards.append({"id": c["id"], "title": str(c.get("title", ""))[:60], "value": str(c.get("value", ""))[:40],
                              "lines": [str(x)[:200] for x in (c.get("lines") or [])][:8], "as_of": str(c.get("as_of") or ""),
                              "stale": bool(c.get("stale")), "sensitive": bool(c.get("sensitive")),
                              "detail": c.get("detail") if c.get("detail") in PANELS else None, "demo": False})
        jobs = DEMO_JOBS if self.demo else clean_jobs(raw_jobs) if isinstance(raw_jobs, list) else None
        with self.lock:
            self.hud_cache = cards
        return {"cards": cards, "jobs": jobs, "jobs_count": len(DEMO_JOBS) if self.demo else jobs_count, "as_of": as_of, "demo": bool(cards and cards[0].get("demo"))}

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
        if str(self.cfg.get("JARVIS_REPLY_LANGUAGE", "")).lower().startswith("en"):
            status = {"ok": "online", "slow": "responding slowly", "down": "offline", "error": "reporting an error",
                      "unpaired": "not paired", "demo": "demo mode", "unknown": "not checked yet"}.get(h["state"], h["state"])
            return (f"Server {status}. Speech recognition {'ready' if not self.stt.problem() else 'not configured'}. "
                    f"Voice {'ready' if not self.tts.problem() else 'not configured'}. "
                    f"Microphone {'on' if self.prefs['mic'] else 'off'}. {wins} windows open.")
        voice = (f"reconocimiento {'listo' if not self.stt.problem() else 'no configurado'}, "
                 f"voz {'lista' if not self.tts.problem() else 'no configurada'}")
        return (f"Servidor: {server}. Voz: {voice}. Micrófono: {'encendido' if self.prefs['mic'] else 'apagado'}. "
                f"Ventanas abiertas: {wins}" + (", una por monitor si las moviste." if wins > 1 else ".")
                + " Enfoque: negocios externos. No compro, no llamo y no publico.")

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

    def paneles_negocio(self):
        """Cobros reales del servidor solo si está emparejado; nunca DEMO. Cripto: precio público en caché."""
        cobros = None
        if not self.demo and self.client.url and self._token():
            try:
                p = self.panel("cobros"); cobros = {"lineas": p.get("lines") or [], "as_of": p.get("as_of")}
            except Exception:   # servidor caído: el panel dice sin datos
                cobros = None
        try:
            cr = negocios.mercado()
        except Exception:
            cr = None
        return paneles.resumen(servidor_cobros=cobros, cripto=cr)

    def voz_view(self):
        with self.lock:
            v = self.voz
            return {"estado": v["estado"], "idioma": v["idioma"], "corte": bool(v.get("corte")),
                    "lineas": [dict(x) for x in v["lineas"]]}

    def voz_aviso(self, data):
        """Estado de la voz continua para el HUD. No aprueba, no envía y no guarda audio."""
        if not isinstance(data, dict):
            raise ValueError("JSON inválido")
        estado = str(data.get("estado") or "")
        if estado not in ("idle", "escuchando", "pensando", "hablando"):
            raise ValueError("estado no válido")
        idioma = data.get("idioma")
        linea = data.get("linea") if isinstance(data.get("linea"), dict) else None
        with self.lock:
            self.voz["estado"] = estado
            self.voz["corte"] = bool(data.get("corte"))
            if idioma in ("es", "en"):
                self.voz["idioma"] = idioma
            if linea:
                quien = linea.get("quien")
                texto = " ".join(str(linea.get("texto") or "").split())[:240]
                if quien in ("tu", "jarvis") and texto:
                    self.voz["lineas"] = (self.voz["lineas"] + [{"quien": quien, "texto": texto}])[-8:]
        vista = self.voz_view()
        self.emit({"type": "voz", "voz": vista})
        return vista

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
                    "startup": {"camera": truthy(self.cfg.get("VOICE_AUTO_CAMERA", "false")), "audio": truthy(self.cfg.get("VOICE_STARTUP_AUDIO", "false")),
                                "greeting": truthy(self.cfg.get("VOICE_STARTUP_GREETING", "true")),
                                "sound": startup_sound(self.cfg) is not None,
                                "fondo": truthy(self.cfg.get("JARVIS_FONDO", "true")) and (HERE / "ui" / "audio" / "fondo.wav").is_file()},
                    "stt": {"engine": self.stt.name, "problem": self.stt.problem()},
                    "tts": {"engine": self.tts.name, "problem": self.tts.problem()},
                    "processing": "Todo el audio se procesa en esta Mac" if self.stt.name != "none" else
                                  "Sin reconocimiento de voz: escribe tus consultas",
                    "wake_word": False, "retain_audio": self.retain, "prefs": dict(self.prefs),
                    "pairing": None if not p else {"code": p.get("code"), "status": p.get("status"),
                                                   "error": p.get("error")},
                    "panels": list(PANELS), "server": self.health_view(), "avatar_ironman": self.avatar_ironman,
                    "speaking": time.time() < getattr(self, "speaking_until", 0),
                    "speaking_topics": list(getattr(self, "speaking_topics", [])) if time.time() < getattr(self, "speaking_until", 0) else [],
                    "mode": core_mode(self.health_view().get("state"), self.last_alert_at, time.time()),
                    "alert": dict(self.last_alert) if self.last_alert and self.last_alert_at else None,
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
            if name == "practica":
                p["chart"] = _demo_chart()
            return p
        if not self.client.url or not self._token():
            raise ServerError(503, "Sin datos reales: configura y empareja el equipo")
        p = self.client.panel(name)
        lines = [str(x)[:500] for x in (p.get("lines") or [])][:80]
        return {"panel": name, "title": str(p.get("title", name))[:80], "lines": lines,
                "speak": engines.speakable(p.get("speak", "")), "sensitive": bool(p.get("sensitive")),
                "as_of": p.get("as_of"), "demo": False,
                **({"chart": clean_chart(p.get("chart"))} if name == "practica" else {})}

    # --- speech ---
    WAKE_RE = re.compile(r"^\W*(?:(?:oye|hey|ey)\W+)?(?P<w>jarvis|yarvis|harvis|jarbis|yarbis|harbis|harbys|jarvi)\b", re.I)

    def transcribe(self, wav):
        out = self.stt.transcribe(wav, retain_dir=(self.home / "audio") if self.retain else None)
        return self._wake_filter(out)

    def _wake_filter(self, out):
        """Solo voz: atiende si empieza con «Jarvis» o si sigue la conversación reciente."""
        if not truthy(self.cfg.get("VOICE_WAKE_WORD_ENABLED", "false")) or not out.get("text"):
            return out
        text = out["text"]
        m = self.WAKE_RE.match(text)
        if m or time.time() < getattr(self, "_wake_until", 0.0):
            self._wake_until = time.time() + self._wake_follow()
            if m:                                       # "Yarvis", "Harbys"... -> "Jarvis" para el resto del panel
                out = dict(out, text=text[:m.start("w")] + "Jarvis" + text[m.end("w"):])
            return out
        return dict(out, text="", reason="no_wake_word")

    def _wake_follow(self):
        try:
            return max(0.0, min(300.0, float(self.cfg.get("VOICE_WAKE_FOLLOW_S", "40"))))
        except (TypeError, ValueError):
            return 40.0

    def speak(self, text, turn_id=None, sensitive=False):
        """Synthesize and tell the audio window to play it. Text stays on screen if voice fails."""
        self.speaking_topics = speech_topics(text)          # solo etiquetas (BTC, id de negocio), nunca el texto
        with self.lock:
            discreet = self.prefs["discreet"]; rate = self.prefs["rate"]; owner = self.owner
        if discreet and (sensitive or re.search(r"\d", text or "")):
            text = "I left it on screen, sir."
        if (not owner and not self._playback_native()) or self.tts.problem():
            return None                                      # sin ventana dueña: en auto suena por los altavoces
        gen0 = getattr(self, "_voz_gen", 0)                  # generación tomada ANTES de sintetizar: un stop posterior la invalida
        native = self._playback_native()
        parts = speech_chunks(text)                          # baja latencia: la 1.ª frase suena mientras se sintetiza el resto
        first, total = None, 0.0
        t_tts = latencia.now_ms()
        for i, part in enumerate(parts):
            try:
                audio, ctype = self.tts.synthesize(part, rate=rate)
                if i == 0 and turn_id:
                    lat = self._lat(turn_id); lat["tts_first_audio_ms"] = latencia.now_ms() - t_tts
                    latencia.write(turn_id, lat)
            except engines.EngineError as e:
                if i == 0:
                    self.emit({"type": "state", "state": "error", "detail": f"voz: {e}"}); return None
                break
            aid = uuid.uuid4().hex
            with self.lock:
                if (turn_id and self.turns.get(turn_id, {}).get("cancelled")) or gen0 != getattr(self, "_voz_gen", 0):
                    return first                             # cancelled while synthesizing: never plays
                self.audio[aid] = (audio, ctype)
                for old in list(self.audio)[:-10]:
                    self.audio.pop(old, None)
                self.last["audio"] = aid
            if i == 0:
                first = aid                                  # una sola voz a la vez: corta lo que sonaba (nativo o navegador)
                self.stop_local_audio(); gen0 = getattr(self, "_voz_gen", 0)
                if native:
                    self.emit({"type": "audio.stop"})
            if native:                                       # una sola salida: altavoces si no hay ventana del panel viva
                self._play_local(audio, gen0)
            else:
                self.emit({"type": "audio.play", "id": aid, "turn": turn_id or first, "seq": i})
            total += _wav_secs(audio)
        self.speaking_until = time.time() + (total or 3)
        return first

    def _lat(self, tid):
        with self.lock:
            t = self.turns.get(tid)
            return t.setdefault("lat", {}) if t is not None else {}

    def prewarm_stt(self):
        """Precalienta whisper.cpp al arrancar el panel.

        Por qué: el log de latencia del dueño (33 turnos reales) dice que los primeros cuatro
        turnos tardan 6 669 ms en transcribir y los 29 siguientes 2 098 ms. Tres veces más al
        empezar, porque el modelo y el binario llegan al caché del sistema con el primer turno.
        Esto los trae antes, con un tono corto generado aquí: 0,4 s de audio, sin micrófono.

        No toca el micrófono, no graba nada, no sale de la Mac, y si falla no pasa nada: el
        primer turno real vuelve a pagar el arranque y ya está. El resultado se descarta."""
        import math
        if self.stt.problem():
            return

        def run():
            try:
                from audio import wav as _wav
            except ImportError:
                from desktop.audio import wav as _wav
            muestras = [int(1500 * math.sin(2 * math.pi * 220 * i / _wav.RATE))
                        for i in range(int(_wav.RATE * 0.4))]
            try:
                self.stt.transcribe(_wav.make_wav(muestras))     # se descarta a propósito
            except Exception:
                return                                            # el primer turno pagará el arranque

        threading.Thread(target=run, daemon=True).start()

    def prewarm_tts(self):
        """Precalienta say/Piper al arrancar (y deja el saludo en caché): la primera respuesta no paga el arranque."""
        def run():
            for line in (GREETING, "Yes, sir."):
                try:
                    self.tts.synthesize(line, rate=self.prefs["rate"])
                except Exception:
                    return
        if not self.tts.problem():
            threading.Thread(target=run, daemon=True).start()

    def _playback_mode(self):
        return str(self.cfg.get("VOICE_SERVER_PLAYBACK", "auto")).strip().lower()

    def _playback_native(self):
        """auto: nativo solo si no hay ninguna ventana del panel viva (si no, suena dos veces); true/native: siempre nativo."""
        m = self._playback_mode()
        if m in ("false", "0", "no", "off") or not local_player():
            return False
        if m in ("true", "1", "yes", "on", "native"):
            return True
        now = time.time()
        with self.lock:                                   # depende de la ventana DUEÑA del audio, no de cualquier ventana
            owner = getattr(self, "owner", None)
            live = bool(owner) and now - getattr(self, "windows", {}).get(owner, 0) < WINDOW_STALE
        return not live

    def _play_local(self, audio, gen=None):
        """Voz siempre activa sin depender del autoplay del navegador: reproduce en los altavoces de este equipo.
        Solo habla en local; nunca envía nada. VOICE_SERVER_PLAYBACK=false lo apaga."""
        if str(self.cfg.get("VOICE_SERVER_PLAYBACK", "auto")).lower() in ("false", "0", "no", "off"):
            return False
        player = local_player()
        if not player:
            return False
        with _VOZ_INIT_LOCK:                              # inicialización única aunque hablen dos hilos a la vez
            if not hasattr(self, "_voz_q"):
                import queue
                self._voz_q = queue.Queue(); self._voz_proc = None; self._voz_lock = threading.Lock()
                self._voz_gen = getattr(self, "_voz_gen", 0)
                threading.Thread(target=self._voz_worker, args=(player,), daemon=True).start()
            self._voz_q.put((self._voz_gen if gen is None else gen, audio))   # cola: una frase cada vez; gen previa al stop
        return True

    def _voz_worker(self, player):
        n = 0
        while True:
            gen, audio = self._voz_q.get()
            if gen != self._voz_gen:
                continue                                 # descartada por stop/cancelar
            n += 1; path = self.home / f"voz_{n % 2}.wav"
            try:
                path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(audio)
                with self._voz_lock:                     # comprobar y lanzar de forma atómica frente a stop_local_audio
                    if gen != self._voz_gen:
                        continue
                    una_voz.claim()                      # una sola voz en la Mac: corta otra voz de Jarvis (voz_loop, etc.)
                    proc = subprocess.Popen(player + [str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self._voz_proc = proc
                    una_voz.register(getattr(proc, "pid", 0))
                try:
                    proc.wait(timeout=120)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except OSError:
                pass
            finally:
                self._voz_proc = None

    def stop_local_audio(self):
        """/api/audio/stop, cancelar, Escape, silenciar: corta el reproductor nativo y vacía la cola."""
        with _VOZ_INIT_LOCK:                             # siempre invalida la generación, aunque la cola no exista aún
            self._voz_gen = getattr(self, "_voz_gen", 0) + 1
            if not hasattr(self, "_voz_q"):
                return
        with self._voz_lock:
            proc = self._voz_proc
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass

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
                                      "at": time.time(), "lat": dict(getattr(self, "_lat_pending", None) or {})}
            self._lat_pending = None
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
        self.stop_local_audio(); self.emit({"type": "audio.stop", "turn": turn_id})
        self.emit({"type": "turn.cancelled", "turn": turn_id})
        return {"cancelled": True, "already_done": done,
                "note": ("La respuesta ya había llegado; solo detuve el audio." if done else
                         "No mostraré ni leeré la respuesta cuando llegue. Esta vía es de solo consulta: "
                         "no había ninguna acción que deshacer.")}

    def _finish(self, tid, state, reply=None, sensitive=False, events=(), llm=False, panel_data=None):
        if str(self.cfg.get("JARVIS_REPLY_LANGUAGE", "")).lower().startswith("en"):
            reply = {
                "Apagué el micrófono.": "Microphone off.",
                "Micrófono encendido. Pulsa Hablar o la barra espaciadora.": "Microphone on. Ready to listen.",
                "Modo discreto activado: no leeré montos ni códigos.": "Discreet mode on. Amounts and codes stay on screen.",
                "Modo discreto desactivado.": "Discreet mode off.",
                "Todavía no he dicho nada.": "There is no previous reply yet.",
                "Listo, hablaré más despacio.": "Of course. I will speak a little more slowly.",
                "Listo, hablaré más rápido.": "Of course. I will speak a little faster.",
                "Paré el mouse. Para volver a encenderlo borra ~/.jarvis-control/STOP en la Mac.":
                    "Mouse stopped. Remove the STOP file on your Mac when you want to resume.",
            }.get(reply, reply)
        self._wake_until = time.time() + self._wake_follow()     # tras responder: seguir sin repetir «Jarvis»
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
            if kind == "stop_mouse":                                # parada remota del mouse: crea STOP
                _crear_stop_mouse(); self.emit({"type": "audio.stop"})
                return self._finish(tid, "done", "Mouse stopped, sir. To turn it back on, delete ~/.jarvis-control/STOP on the Mac.")
            if kind == "application":
                result = account_navigation.open_application(arg)
                return self._finish(tid, "done" if result["ok"] else "error", result["message"])
            if kind == "account":
                result = account_navigation.open_account(arg)
                return self._finish(tid, "done" if result["ok"] else "error", result["message"])
            if kind == "mouse":                                     # voz -> ejecutor del mouse (supervisado: /confirmar)
                r = mouse_autonomo.encargar_voz(arg)
                msg = ("On it, sir. Confirm on Telegram with /confirmar if it asks." if r["ok"]
                       else "I can't do that with the mouse right now, sir: " + str(r.get("motivo")) + ".")
                return self._finish(tid, "done", msg)
            if kind == "stop_audio":
                self.stop_local_audio(); self.emit({"type": "audio.stop"}); return self._finish(tid, "done")
            if kind == "mic_off":
                self.set_prefs(mic=False); self.emit({"type": "mic.off"})
                return self._finish(tid, "done", "Microphone off, sir.")
            if kind == "mic_on":                                   # 4.0.5 (3.4)
                self.set_prefs(mic=True); self.emit({"type": "mic.on"})
                return self._finish(tid, "done", "Microphone on. Press Talk or the space bar.")
            if kind in ("discreet_on", "discreet_off"):
                self.set_prefs(discreet=kind == "discreet_on")
                return self._finish(tid, "done", "Discreet mode on: I won't read amounts or codes aloud." if kind == "discreet_on"
                                    else "Discreet mode off.")
            if kind == "health":
                return self._finish(tid, "done", self.local_health_text())
            # Business conversation uses the paired server and current records,
            # not a fixed speech listing unrelated limitations.
            if kind == "repeat":
                with self.lock:
                    aid, last = self.last["audio"], self.last["text"]
                if aid and aid in self.audio:
                    self.emit({"type": "audio.play", "id": aid, "turn": tid}); return self._finish(tid, "done")
                return self._finish(tid, "done", last or "I haven't said anything yet, sir.")
            if kind in ("slower", "faster"):
                self.set_prefs(rate=self.prefs["rate"] + (-0.15 if kind == "slower" else 0.15))
                return self._finish(tid, "done", "Very well, I'll speak more slowly." if kind == "slower"
                                    else "Very well, I'll speak a little faster.")
            if kind == "refuse":
                return self._finish(tid, "done", arg)
            if kind == "panel":
                p = self.panel(arg)
                return self._finish(tid, "done", p.get("speak") or p["title"], sensitive=p.get("sensitive", False),
                                    panel_data=p)
            if kind == "empty":
                return self._finish(tid, "done", "I didn't catch that, sir.")
            if self.demo:
                return self._finish(tid, "done", "Demo mode: I'm not connected to your Jarvis, so I can't read your "
                                                 "data. Try \"open the agenda\" to see a sample panel.")
            if not self.client.url or not self._token():
                return self._finish(tid, "error", "No live connection to Jarvis. Please pair this computer; nothing was executed.")
            t_llm = latencia.now_ms()
            r = self.client.turn(tid, text)          # respuesta del servidor (sin streaming: = primer token)
            self._lat(tid)["llm_first_token_ms"] = latencia.now_ms() - t_llm
            state = r.get("state")
            if state == "uncertain":
                return self._finish(tid, "error", r.get("reply") or "I'm not sure Jarvis answered; please ask me again.")
            if state == "running":
                return self._finish(tid, "error", "Jarvis is still working on that; try again in a moment.")
            self._finish(tid, "done" if state == "done" else "error", str(r.get("reply") or "")[:4000],
                         sensitive=bool(r.get("sensitive")), events=safe_events(r.get("events")),
                         llm=bool(r.get("llm_used")))
        except ServerError as e:
            if e.status == 401:
                self._auth_lost(e.detail)
            msg = ("I couldn't reach Jarvis, sir, no connection. Please try again."
                   if e.status == 0 else f"Jarvis returned an error: {e.detail}")
            self.emit({"type": "state", "state": "sin conexión" if e.status == 0 else "error"})
            self._finish(tid, "error", msg)
        except Exception as e:                                   # never leave a turn stuck
            log.warning("turn failed: %s", type(e).__name__)
            self._finish(tid, "error", "Something failed in the local panel; please try again.")


documentos.install(Companion)

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
            if u.path == "/avatar/ironman":
                if not app.avatar_ironman:
                    return self._send(404, {"error": "no existe"})
                if not app.session_ok(self._cookie()):
                    return self._send(401, INDEX_401, "text/html; charset=utf-8")
                return self._send(200, (HERE / "ui" / "nucleo.html").read_bytes(), "text/html; charset=utf-8")   # sin Aincrad
            if u.path in ("/", "/hud", "/avatar", "/torre", "/nucleo", "/mercado", "/orbe"):   # /hud = second monitor (4.0.5, 3.2)
                if not app.session_ok(self._cookie()):
                    return self._send(401, INDEX_401, "text/html; charset=utf-8")
                page = {"/": "index.html", "/hud": "hud.html", "/avatar": "nucleo.html", "/torre": "nucleo.html", "/nucleo": "nucleo.html",   # la Torre de Aincrad se retiró: solo el núcleo
                       
                        "/mercado": "mercado.html", "/orbe": "orbe.html"}[u.path]
                body = (HERE / "ui" / page).read_bytes()
                if u.path == "/avatar" and not app.avatar_ironman:
                    body = IRONMAN_LINK.sub(b"", body)
                return self._send(200, body, "text/html; charset=utf-8")
            if not self._guard():
                return
            if u.path.startswith("/ui/") and u.path[4:] in UI_FILES:
                return self._send(200, (HERE / "ui" / u.path[4:]).read_bytes(), UI_FILES[u.path[4:]])
            if u.path.startswith("/ui/assets/") and u.path[11:] in ASSET_FILES:
                if not app.avatar_ironman:
                    return self._send(404, {"error": "no existe"})
                return self._send(200, (HERE / "ui" / "assets" / u.path[11:]).read_bytes(), ASSET_FILES[u.path[11:]])
            if u.path.startswith("/ui/vendor/") and u.path[11:] in VENDOR_FILES:
                if not app.avatar_ironman and not u.path[11:].startswith("three/"):   # three.js (MIT, local) lo usa el núcleo WebGL siempre;
                    return self._send(404, {"error": "no existe"})                    # antes daba 404 sin JARVIS_AVATAR_IRONMAN → caía al 2D viejo
                return self._send(200, (HERE / "ui" / "vendor" / u.path[11:]).read_bytes(), VENDOR_FILES[u.path[11:]])
            if u.path == "/api/hand-mouse/status":
                return self._send(200, app.hand_mouse.status())
            if u.path == "/api/state":
                return self._send(200, app.state())
            if u.path == "/api/mouse-autonomo":              # solo lectura: sesión, agente, STOP
                return self._send(200, mouse_autonomo.estado())
            if u.path == "/api/ambient-music":                # música de fondo original (gen_encendido.py), en bucle
                amb = HERE / "ui" / "audio" / "ambiente.wav"
                if not amb.is_file():
                    return self._send(404, {"error": "sin música"})
                return self._send(200, amb.read_bytes(), "audio/wav")
            if u.path == "/api/fondo-music":                  # fondo ambiental original (gen_fondo.py); JARVIS_FONDO=off lo apaga
                fondo = HERE / "ui" / "audio" / "fondo.wav"
                if not truthy(app.cfg.get("JARVIS_FONDO", "true")) or not fondo.is_file():
                    return self._send(404, {"error": "fondo apagado"})
                return self._send(200, fondo.read_bytes(), "audio/wav")
            if u.path == "/api/startup-sound":                # sonido de arranque (original o archivo propio local)
                found = startup_sound(app.cfg)
                if not found:
                    return self._send(404, {"error": "sin sonido de arranque"})
                return self._send(200, found[0].read_bytes(), found[1])
            if u.path == "/api/ciclo":
                c = getattr(app, "ciclo", None)
                return self._send(200, c.estado_view() if c else {"activo": False})
            if u.path == "/api/negocios":                     # torre de Aincrad: cifras DEMO, sin red
                return self._send(200, negocios.torre())
            if u.path == "/api/paneles-negocio":             # paneles del núcleo: solo datos reales locales
                return self._send(200, app.paneles_negocio())
            m = re.fullmatch(r"/api/evidencia/(\d{1,12}\.png)", u.path)
            if m:
                img = paneles.captura(paneles.control_dir(), m.group(1))
                return self._send(200, img, "image/png") if img else self._send(404, {"error": "no existe"})
            if u.path == "/api/cripto":                       # precios públicos, sin claves ni trading
                return self._send(200, negocios.mercado())
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
            if u.path == "/api/voz":
                return self._send(200, app.voz_view())
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
            if u.path == "/api/voz":
                if self.headers.get("Host") not in allowed_hosts:
                    return self._send(400, {"error": "host no permitido"})
                if not loopback_host(self.client_address[0]):
                    return self._send(403, {"error": "solo el equipo local"})
                try:
                    return self._send(200, app.voz_aviso(self._json(limit=4096)))
                except ValueError as e:
                    return self._send(400, {"error": str(e)[:200]})
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
                    t0 = latencia.now_ms()
                    out = app.transcribe(wav); out["id"] = uuid.uuid4().hex
                    app._lat_pending = {"vad_ms": latencia.VAD_SILENCE_MS, "stt_ms": latencia.now_ms() - t0,
                                        "audio_duration_ms": out.get("duration_s", 0) * 1000}
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
                if u.path == "/api/greet":                   # saludo de Alan tras el sonido; solo voz local
                    return self._send(200, {"audio": app.speak(GREETING)})
                if u.path == "/api/mouse-autonomo/orden":   # Jarvis encarga investigación; el ejecutor revalida
                    return self._send(200, mouse_autonomo.encargar(data.get("orden")))
                if u.path == "/api/open":
                    return self._send(200, app.open_detail(str(data.get("target", ""))[:20]))
                if u.path == "/api/alerts/repeat":
                    return self._send(200, app.alert_repeat())
                if u.path == "/api/alerts/silence":
                    with app.lock:
                        app.last_alert_at = 0.0                 # silenciar = el núcleo vuelve a modo Jarvis
                    app.stop_local_audio(); app.emit({"type": "audio.stop"}); return self._send(200, {"ok": True})
                if u.path == "/api/pulse":
                    app.pulse_once(); return self._send(200, app.health_view())
                if u.path == "/api/audio/stop":
                    app.stop_local_audio(); app.emit({"type": "audio.stop"}); return self._send(200, {"ok": True})
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


def loopback_host(addr: str) -> bool:
    return addr in ("127.0.0.1", "::1")


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address):
        # A closed tab can disconnect while a long poll is writing its reply.
        if isinstance(sys.exc_info()[1], (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


def serve(cfg, open_browser=True):
    host = check_bind(cfg["VOICE_BIND_HOST"], truthy(cfg["VOICE_ALLOW_LAN"]))
    port = int(cfg["VOICE_PORT"])
    app = Companion(cfg)
    app.prewarm_tts()                                  # TTS listo antes de la primera respuesta
    app.prewarm_stt()                                  # y Whisper: el primer turno tardaba 3x más
    httpd = Server((host, port), http.server.BaseHTTPRequestHandler)
    real_port = httpd.server_address[1]                  # differs from port only when port is 0 (tests)
    httpd.RequestHandlerClass = make_handler(app, host, real_port)
    def _estado_srv():
        try:
            return "servidor: " + " · ".join(app.panel("estado").get("lines", [])[:3])
        except Exception as e:
            return f"servidor no disponible ({type(e).__name__})"
    app.ciclo = ciclo.Ciclo(app.home, base=cfg.get("VOICE_CICLO_DIR", str(app.home / "archivos")), emit=app.emit,
                            speak=lambda t: app.speak(t, sensitive=True), stopped=mouse_autonomo.ae.stopped,
                            mouse=mouse_autonomo.encargar, estado=_estado_srv)
    return app, httpd, real_port


def check_mac():
    """Measure before choosing models: no installs, no network."""
    def run(cmd):
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=10, check=False)
            return (proc.stdout.decode(errors="replace") + "\n" + proc.stderr.decode(errors="replace")).strip()
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
        missing = [f for f in ("-nt", "-np", "-otxt", "-of", "-l", "-t")
                   if re.search(r"(?<![\w-])" + re.escape(f) + r"(?![\w-])", helptext) is None]
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


def _wav_secs(audio):
    try:
        import io, wave as _w
        with _w.open(io.BytesIO(audio)) as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        return 0.0


def speech_chunks(text, first_max=140, first_words=6):
    """Speak whole sentences; only split unusually long sentences at word boundaries.

    Keep legacy arguments for callers, but never force a six-word prosody break.
    """
    import textwrap
    t = str(text or "").strip()
    sentences = re.split(r"(?<=[.!?…])\s+", t, maxsplit=1)
    return [part for sentence in sentences for part in
            textwrap.wrap(sentence, width=450, break_long_words=False, break_on_hyphens=False)] or [""]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Jarvis desktop companion")
    ap.add_argument("--config"); ap.add_argument("--check", action="store_true")
    ap.add_argument("--bench"); ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--hand-mouse", action="store_true", help="habilita pruebas locales del puntero, sin clics")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    if a.check:
        return check_mac()
    # Sin saludo con `say` aparte: sonaba en español A LA VEZ que el saludo inglés de /api/greet.
    if a.bench:
        return bench(a.bench)
    cfg = load_config(a.config)
    if a.hand_mouse:
        if sys.platform != "darwin" or cfg["VOICE_BIND_HOST"] not in ("127.0.0.1", "localhost", "::1") or truthy(cfg["VOICE_DEMO"]):
            raise SystemExit("--hand-mouse solo se permite localmente en macOS, fuera de DEMO.")
        cfg["_HAND_MOUSE_ENABLED"] = True
    if truthy(cfg["VOICE_WAKE_WORD_ENABLED"]):
        print("Palabra de activación: activa. Empieza con «Jarvis»; después puedes seguir hablando sin repetirlo.")
    app, httpd, port = serve(cfg)
    if truthy(cfg.get("VOICE_STARTUP_GREETING", "true")) and not truthy(cfg.get("VOICE_DEMO", "false")):
        threading.Thread(target=native_intro, args=(app, cfg), daemon=True).start()   # música + saludo
    if truthy(cfg.get("VOICE_CICLO", "true")):
        app.ciclo.arrancar()                             # ciclo autónomo local, siempre encendido
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
