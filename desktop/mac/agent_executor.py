#!/usr/bin/env python3
"""Ejecutor local de la Mac. Jarvis solo propone; nada corre sin confirmación.

La denylist no se confirma. No hay WhatsApp ni mensajes a clientes.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import time
import unicodedata
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

AGENTS = {"chatgpt", "grok", "claude", "jarvis", "gestos"}
OWNER = "yullian"
MAX_MINUTES = 30
MAX_PER_MINUTE = 20
SESSION_SECONDS = 600
CONFIRM_SECONDS = 60
GRANT_HOURS = 8          # un permiso de --otorgar vence a las 8 horas si no se usa
MAX_GRANT_HOURS = 24
MAX_LINE = 4000
APP_NAME = re.compile(r"^[A-Za-z0-9 ._-]{1,40}$")

DENY_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
# Se buscan como SUBCADENA del texto sin espacios ni signos, no como palabra suelta: así 1firstbank.com,
# bancopopular.com, mi-banco.pr o "ath movil" también quedan bloqueados.
DENY_PARTS = (
    "bank", "banco", "banca", "popular", "oriental", "firstbank", "mibanco", "cooperativa",
    "paypal", "stripe", "checkout", "venmo", "zelle", "cashapp", "athmovil", "applepay", "googlepay",
    "pago", "payment", "factura", "tarjeta", "wallet", "billetera",
    "coinbase", "binance", "kraken", "robinhood", "webull",
    "equifax", "experian", "transunion", "annualcreditreport", "creditkarma",
)
DENY_COMPACT = tuple(re.sub(r"[^a-z0-9]", "", part) for part in DENY_PARTS)
SECRET_RE = re.compile(r"\b(sudo|curl|password|contrasena|clave)\b|\brm\s+-")
DENY_APPS = {
    "terminal", "iterm", "finder", "system settings", "system preferences",
    "ajustes", "llavero", "keychain access", "keychain", "mail", "mail.app",
    "mensajes", "messages", "whatsapp", "telegram",
}
DANGEROUS = {
    frozenset({"command", "backspace"}),        # borrar; también cubre cmd+shift/alt+backspace
    frozenset({"command", "q"}),                # salir; también cubre cmd+shift+q (cerrar sesión) y ctrl+cmd+q
    frozenset({"command", "alt", "escape"}),    # forzar salida
    frozenset({"command", "space"}),            # Spotlight: abre cualquier app
    frozenset({"command", "enter"}),
    frozenset({"control", "command", "power"}),
    frozenset({"control", "alt", "command", "power"}),
}
FREE_ACTIONS = {"scroll", "screenshot", "wait", "move"}
ALLOW_HOSTS = {"github.com", "jarvis-agents.onrender.com", "127.0.0.1", "localhost"}
ALLOW_APPS = {"notes", "safari"}
# Modo autónomo (opcional, apagado por defecto): JARVIS_AUTONOMO=1 o --autonomo.
AUTO_ACTIONS = {"move", "click", "double_click", "scroll", "screenshot", "wait", "type", "open_url", "open_app"}
AUTO_AGENT = "jarvis"
AUTO_LOCK_MINUTES = 5
HEARTBEAT_SECONDS = 5
KEY_ALIAS = {
    "cmd": "command", "meta": "command", "option": "alt",
    "delete": "backspace", "return": "enter", "spacebar": "space", "ctrl": "control", "opt": "alt",
    "⌘": "command", "⌥": "alt", "⌃": "control",
}


def control_dir() -> Path:
    raw = os.environ.get("JARVIS_CONTROL_DIR", "").strip()
    path = Path(raw) if raw else Path.home() / ".jarvis-control"
    path.mkdir(parents=True, exist_ok=True)
    return path


def owner_dir() -> Path:
    """Carpeta del dueño, aparte de la carpeta de control donde escriben los agentes. Guarda la llave que
    firma los permisos y los permisos ya gastados."""
    raw = os.environ.get("JARVIS_OWNER_DIR", "").strip()
    path = Path(raw) if raw else Path.home() / ".jarvis-owner"
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def now() -> datetime:
    return datetime.now(timezone.utc)


def norm(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text).casefold())
    return "".join(ch for ch in folded if not unicodedata.combining(ch))


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse_stamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def read_lock() -> dict | None:
    path = control_dir() / "lock.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        expires = parse_stamp(data["expires"])
    except (OSError, ValueError, KeyError, TypeError):
        return None
    if expires <= now():
        return None
    if data.get("agent") not in AGENTS:
        return None
    return {"agent": data["agent"], "expires": stamp(expires)}


def write_lock(agent: str, minutes: int) -> None:
    payload = {"agent": agent, "expires": stamp(now() + timedelta(minutes=minutes))}
    path = control_dir() / "lock.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.replace(tmp, path)


def take_lock(agent: str, minutes: int) -> int:
    if agent not in AGENTS:
        print("RECHAZADO agente no permitido")
        return 2
    if not 1 <= minutes <= MAX_MINUTES:
        print(f"RECHAZADO minutos entre 1 y {MAX_MINUTES}")
        return 2
    current = read_lock()
    if current and current["agent"] != agent:
        print("OCUPADO")
        return 2
    write_lock(agent, minutes)
    print(f"TURNO {agent} {minutes} min")
    return 0


def release_lock(name: str) -> int:
    current = read_lock()
    if current is None:
        print("LIBRE")
        return 0
    if name != OWNER and name != current["agent"]:
        print("RECHAZADO no es tu turno")
        return 2
    path = control_dir() / "lock.json"
    path.unlink(missing_ok=True)
    print("LIBRE")
    return 0


def lock_status() -> int:
    current = read_lock()
    print("LIBRE" if current is None else f"{current['agent']} hasta {current['expires']}")
    return 0


def stopped() -> bool:
    return (control_dir() / "STOP").exists()


def autonomo() -> bool:
    """Modo autónomo solo si el dueño lo enciende en su Mac. Apagado por defecto."""
    return os.environ.get("JARVIS_AUTONOMO", "").strip() == "1"


def heartbeat() -> None:
    _write_json("autonomo.json", {"latido": stamp(now()), "pid": os.getpid()})


def auto_ok(action: dict) -> bool:
    """Lista segura del modo autónomo. Todo lo demás (atajos, apps o webs fuera de lista, denylist) nunca se
    aprueba solo."""
    if not autonomo() or denial(action):
        return False
    kind = str(action.get("action") or "")
    if kind not in AUTO_ACTIONS or action.get("agent") not in AGENTS:
        return False
    if kind == "open_url":
        return allowed_host(host_of(str(action.get("url") or "")))
    if kind == "open_app":
        return norm(action.get("app") or "") in ALLOW_APPS
    return True


def session_open() -> bool:
    if autonomo():                      # sin vencimiento de 10 min; el latido muestra que sigue vivo
        heartbeat()
        return True
    path = control_dir() / "session.json"
    moment = now()
    if not path.exists():
        path.write_text(json.dumps({"started": stamp(moment)}), encoding="utf-8")
        return True
    try:
        started = parse_stamp(json.loads(path.read_text(encoding="utf-8"))["started"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return (moment - started).total_seconds() <= SESSION_SECONDS


def session_status() -> str:
    """Consulta sin crear ni renovar una sesión."""
    if autonomo():
        return "modo autónomo: sin vencimiento (STOP sigue activo)"
    path = control_dir() / "session.json"
    if not path.exists():
        return "sin sesión"
    try:
        elapsed = (now() - parse_stamp(json.loads(path.read_text(encoding="utf-8"))["started"])).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return "sesión inválida"
    if elapsed < 0 or elapsed > SESSION_SECONDS:
        return "sesión vencida"
    return f"sesión activa: {int(SESSION_SECONDS - elapsed)} s restantes"


def start_session(*, ask=None, tty=None) -> int:
    """Renovación explícita del dueño; nunca concede permisos para acciones."""
    if tty is None:
        tty = sys.stdin.isatty()
    if not tty:
        print("RECHAZADO --start-session requiere tu Terminal.")
        return 2
    code = secrets.token_hex(3)
    try:
        answer = (ask or input)(f"Para abrir una sesión de 10 minutos escribe {code}: ")
    except EOFError:
        answer = ""
    if not secrets.compare_digest(str(answer).strip(), code):
        print("CANCELADO. Sesión sin cambios.")
        return 3
    try:
        with _owner_flock("ejecutor.lock", wait=False):
            if stopped() or read_lock() is not None:
                print("BLOQUEADO STOP activo o turno existente. Sesión sin cambios.")
                return 3
            _write_json("session.json", {"started": stamp(now())})
    except BlockingIOError:
        print("OCUPADO otro ejecutor. Sesión sin cambios.")
        return 2
    print("Sesión renovada por 10 minutos. Los permisos de las órdenes se conservan sin ampliar.")
    return 0


def hotkey_set(keys) -> frozenset[str]:
    if not isinstance(keys, list) or not keys:
        return frozenset()
    return frozenset(KEY_ALIAS.get(str(key).lower(), str(key).lower()) for key in keys)


def hotkey_order(keys) -> list[str]:
    """Las teclas en el orden en que se pulsan (modificadores primero, como vienen), sin repetir.
    Antes se ordenaban alfabéticamente y cmd+c podía pulsarse como c+cmd."""
    if not isinstance(keys, list):
        return []
    out: list[str] = []
    for key in keys:
        name = KEY_ALIAS.get(str(key).lower(), str(key).lower())
        if name not in out:
            out.append(name)
    return out


def host_of(url: str) -> str:
    match = re.match(r"^[a-z][a-z0-9+.-]*://([^/?#]+)", norm(url))
    if not match:
        return ""
    host = match.group(1).split("@")[-1].split(":")[0].rstrip(".")
    return host[4:] if host.startswith("www.") else host


def allowed_host(host: str) -> bool:
    return host in ALLOW_HOSTS or host.endswith(".github.com")


def _textos(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found = []
        for item in value.values():
            found.extend(_textos(item))
        return found
    if isinstance(value, list):
        found = []
        for item in value:
            found.extend(_textos(item))
        return found
    return []


def denied_text(text: str) -> bool:
    folded = norm(text)
    compact = re.sub(r"[^a-z0-9]", "", folded)
    return bool(DENY_RE.search(folded)) or any(part in compact for part in DENY_COMPACT)


def dangerous_keys(keys) -> bool:
    pressed = hotkey_set(keys)
    return any(combo <= pressed for combo in DANGEROUS)


def denial(action: dict) -> str | None:
    kind = str(action.get("action") or "")
    if denied_text(" ".join(_textos(action))):
        return "denylist"
    if kind == "type":
        text = str(action.get("text") or "")
        if SECRET_RE.search(norm(text)):
            return "denylist"
        if "\n" in text or "\r" in text or action.get("enter") is True:
            return "enter"
    if kind == "hotkey" and dangerous_keys(action.get("keys")):
        return "atajo"
    if kind == "open_app" and norm(action.get("app") or "") in DENY_APPS:
        return "app"
    return None


def lane(action: dict) -> str:
    if action.get("agent") == "jarvis":
        return "supervisado"
    kind = str(action.get("action") or "")
    if kind in FREE_ACTIONS:
        return "libre"
    if kind == "open_url" and allowed_host(host_of(str(action.get("url") or ""))):
        return "libre"
    if kind == "open_app" and norm(action.get("app") or "") in ALLOW_APPS:
        return "libre"
    return "supervisado"


def needs_confirm(action: dict, libre: bool) -> bool:
    # El carril libre no exime. Sin confirmación de un uso el puntero no se mueve.
    del libre
    return True


def describe(action: dict) -> str:
    """Todo lo que se autoriza, tal como se ejecutará: coordenadas, desplazamiento, texto, URL, app o teclas."""
    kind = str(action.get("action") or "")
    head = f"{action.get('agent')} {kind}"
    if kind in {"move", "click", "double_click"}:
        return f"{head} x={action.get('x')} y={action.get('y')}"
    if kind == "scroll":
        return f"{head} dy={action.get('dy')}"
    if kind == "wait":
        return f"{head} {action.get('seconds')} s"
    if kind == "type":
        text = str(action.get("text") or "")
        shown = json.dumps(text, ensure_ascii=False)[1:-1]
        return f"{head} «{shown}» ({len(text)} caracteres)"
    if kind == "open_url":
        return f"{head} {action.get('url')}"
    if kind == "open_app":
        return f"{head} {action.get('app')}"
    if kind == "hotkey":
        return f"{head} {'+'.join(hotkey_order(action.get('keys')))}"
    return head


def action_key(action: dict) -> str:
    text = str(action.get("text") or "")
    keys = hotkey_order(action.get("keys"))
    payload = {
        "agent": action.get("agent"),
        "action": action.get("action"),
        "x": action.get("x"),
        "y": action.get("y"),
        "dy": action.get("dy"),
        "seconds": action.get("seconds"),
        "url": action.get("url"),
        "app": action.get("app"),
        "text_hash": hashlib.sha256(text.encode()).hexdigest()[:12] if text else "",
        "keys": keys,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


@contextlib.contextmanager
def _owner_flock(name: str, *, wait: bool = True):
    """Candado de archivo en la carpeta del dueño. Con wait=False, si otro proceso lo tiene, lanza BlockingIOError."""
    path = owner_dir() / name
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if wait else fcntl.LOCK_NB))
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _grants() -> list[dict]:
    path = control_dir() / "usos.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    grants = data.get("grants") if isinstance(data, dict) else None
    return [g for g in grants if isinstance(g, dict)] if isinstance(grants, list) else []


def _save_grants(grants: list[dict]) -> None:
    _write_json("usos.json", {"grants": grants})


def _grant_key(create: bool) -> bytes | None:
    """Llave que firma los permisos. Solo --otorgar la crea; si falta, ningún permiso vale."""
    path = owner_dir() / "permisos.key"
    if not path.exists():
        if not create:
            return None
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return path.read_bytes() or None
        with os.fdopen(fd, "wb") as handle:
            handle.write(secrets.token_bytes(32))
    data = path.read_bytes()
    return data if len(data) >= 32 else None


def _sign(secret: bytes, key: str, expires: str, nonce: str) -> str:
    return hmac.new(secret, f"{key}|{expires}|{nonce}".encode(), hashlib.sha256).hexdigest()


def _spent() -> set[str]:
    path = owner_dir() / "gastados.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return {str(x) for x in data} if isinstance(data, list) else set()


def _mark_spent(nonce: str) -> None:
    spent = sorted(_spent() | {nonce})[-5000:]
    path = owner_dir() / "gastados.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(spent), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _grant_valid(grant: dict, key: str, secret: bytes | None, spent: set[str]) -> bool:
    if secret is None or grant.get("key") != key or grant.get("used") is True:
        return False
    nonce, expires, sig = str(grant.get("nonce") or ""), str(grant.get("expires") or ""), str(grant.get("sig") or "")
    if not nonce or nonce in spent:
        return False
    try:
        if parse_stamp(expires) <= now():
            return False
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(sig, _sign(secret, key, expires, nonce))


def grant_once(action: dict, hours: float = GRANT_HOURS) -> bool:
    """Permiso firmado, de un solo uso y con vencimiento. Solo lo llama --otorgar, después del código del dueño."""
    if denial(action) or action.get("agent") not in AGENTS:
        return False
    if not 0 < hours <= MAX_GRANT_HOURS:
        return False
    with _owner_flock("permisos.lock"):
        secret = _grant_key(create=True)
        if secret is None:
            return False
        key = action_key(action)
        spent = _spent()
        grants = [g for g in _grants() if _grant_valid(g, g.get("key"), secret, spent)]   # limpia vencidos y falsos
        if any(g.get("key") == key for g in grants):
            return False
        expires = stamp(now() + timedelta(hours=hours))
        nonce = secrets.token_hex(12)
        grants.append({"key": key, "expires": expires, "nonce": nonce, "sig": _sign(secret, key, expires, nonce)})
        _save_grants(grants)
        return True


def consume_grant(action: dict) -> str | None:
    """Gasta un permiso válido. Un permiso escrito a mano, vencido o ya gastado no vale."""
    if denial(action):
        return None
    with _owner_flock("permisos.lock"):               # leer, validar y gastar es una sola operación
        secret = _grant_key(create=False)
        if secret is None:
            return None
        key = action_key(action)
        spent = _spent()
        grants = _grants()
        for grant in grants:
            if _grant_valid(grant, key, secret, spent):
                _mark_spent(str(grant["nonce"]))      # primero se gasta: nunca corre dos veces
                _save_grants([g for g in grants if g is not grant])
                return "codigo"
        return None


def load_rate() -> list[datetime]:
    """El tope de ritmo vale entre corridas: se guarda en disco."""
    path = control_dir() / "ritmo.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [parse_stamp(x) for x in data if isinstance(x, str)][-MAX_PER_MINUTE * 3:]
    except (OSError, ValueError, TypeError):
        return []


def save_rate(recent: list[datetime]) -> None:
    moment = now()
    fresh = [stamp(x) for x in recent if (moment - x).total_seconds() < 60]
    _write_json("ritmo.json", fresh)


def audit(action: dict, verdict: str, reason: str, *, dry: bool = True) -> None:
    text = str(action.get("text") or "")
    row = {
        "at": stamp(now()),
        "agent": action.get("agent"),
        "action": action.get("action"),
        "verdict": verdict,
        "reason": reason,
        "dry_run": dry,
        "text_len": len(text),
        "text_hash": hashlib.sha256(text.encode()).hexdigest()[:12] if text else "",
    }
    with (control_dir() / "audit.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def judge(action: dict, recent: list[datetime]) -> tuple[str, str]:
    if stopped():
        return "BLOQUEADO", "stop"
    if not session_open():
        return "BLOQUEADO", "sesion"
    kind = action.get("action")
    agent = action.get("agent")
    if kind not in FREE_ACTIONS | {"click", "double_click", "type", "hotkey", "open_url", "open_app"}:
        return "RECHAZADO", "accion"
    if agent not in AGENTS:
        return "RECHAZADO", "agente"
    current = read_lock()
    if current is None or current["agent"] != agent:
        return "RECHAZADO", "turno"
    moment = now()
    fresh = [item for item in recent if (moment - item).total_seconds() < 60]
    recent[:] = fresh
    if len(fresh) >= MAX_PER_MINUTE:
        return "BLOQUEADO", "ritmo"
    why = denial(action)
    if why:
        return "BLOQUEADO", why
    recent.append(moment)
    return "SECO", lane(action)


def _write_json(name: str, payload: dict) -> None:
    path = control_dir() / name
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def begin_pending(action: dict) -> dict:
    pending = {
        "id": secrets.token_hex(8),
        "code": secrets.token_hex(3),
        "agent": action.get("agent"),
        "action": action.get("action"),
        "detail": describe(action),
        "expires": stamp(now() + timedelta(seconds=CONFIRM_SECONDS)),
    }
    # El código vive solo en memoria y en tu pantalla: el archivo que ven los agentes no lo lleva.
    public = {k: v for k, v in pending.items() if k not in {"code", "detail"}}
    _write_json("pendiente.json", {"pending": public})
    return pending


def clear_pending() -> None:
    (control_dir() / "pendiente.json").unlink(missing_ok=True)
    (control_dir() / "decision.json").unlink(missing_ok=True)


def burn(pending: dict) -> None:
    pending["code"] = ""
    clear_pending()


def consume_decision(pending: dict) -> str | None:
    path = control_dir() / "decision.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return None
    path.unlink(missing_ok=True)
    if data.get("id") != pending.get("id"):
        return None
    # decision.json lo puede escribir cualquier proceso: un gesto solo puede CANCELAR, nunca confirmar.
    burn(pending)
    return "cancelar"


def answer_of(pending: dict, answer: str) -> str | None:
    """Solo el código de un uso confirma. Una «s» suelta ya no basta."""
    code = str(pending.get("code") or "")
    if code and secrets.compare_digest(answer, code):
        burn(pending)
        return "codigo"
    return None


def note_gesture(ok: bool) -> str:
    path = control_dir() / "pendiente.json"
    if not path.exists():
        return "sin pendiente"
    try:
        pending = json.loads(path.read_text(encoding="utf-8"))["pending"]
    except (OSError, ValueError, KeyError, TypeError):
        return "sin pendiente"
    _write_json("decision.json", {"id": pending.get("id"), "ok": bool(ok)})
    return "anotado"


def safe_url(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("url")
    if denial({"action": "open_url", "url": url}):
        raise ValueError("denylist")
    return url.strip()


def perform(action: dict, pointer) -> None:
    if denial(action) or stopped():
        raise RuntimeError("bloqueado")
    kind = action["action"]
    if kind == "move":
        pointer.move(int(action["x"]), int(action["y"]))
    elif kind == "click":
        pointer.click(int(action["x"]), int(action["y"]))
    elif kind == "double_click":
        pointer.double_click(int(action["x"]), int(action["y"]))
    elif kind == "scroll":
        pointer.scroll(int(action.get("dy") or 0))
    elif kind == "wait":
        pointer.wait(min(10.0, max(0.0, float(action.get("seconds") or 0))))
    elif kind == "type":
        pointer.write(str(action.get("text") or ""))
    elif kind == "hotkey":
        pointer.hotkey(hotkey_order(action.get("keys")))
    elif kind == "screenshot":
        folder = control_dir() / "capturas"
        folder.mkdir(parents=True, exist_ok=True)
        pointer.shot(folder / f"{int(time.time())}.png")
    elif kind == "open_url":
        pointer.open_url(safe_url(str(action.get("url") or "")))
    elif kind == "open_app":
        app = str(action.get("app") or "")
        if not APP_NAME.fullmatch(app) or norm(app) in DENY_APPS:
            raise RuntimeError("app")
        pointer.open_app(app)
    else:
        raise RuntimeError("accion")


def _observador(pointer, name: str):
    for cls in type(pointer).__mro__:
        if name in cls.__dict__:
            fn = getattr(pointer, name)
            return fn if callable(fn) else None
    return None


def frente_seguro(action: dict, pointer) -> str | None:
    """Justo antes de mover o clicar en modo autónomo. None = se puede. En la Mac, app y página se leen otra vez."""
    kind = str(action.get("action") or "")
    if kind not in {"move", "click", "double_click"}:
        return None
    frontmost = _observador(pointer, "frontmost")
    if frontmost is None:
        return "app_frente_desconocida" if sys.platform == "darwin" else None
    try:
        front = frontmost() or ""
    except Exception:
        return "app_frente_desconocida"
    if norm(front) not in ALLOW_APPS:
        return "app_frente"
    if norm(front) != "safari":
        return None
    page_url = _observador(pointer, "page_url")
    if page_url is None:
        return "sitio_no_verificado"
    try:
        url = page_url() or ""
    except Exception:
        return "sitio_no_verificado"
    if not allowed_host(host_of(url)):
        return "sitio_no_verificado"
    if kind == "move":
        return None
    try:
        otra = page_url() or ""
        frente = frontmost() or ""
    except Exception:
        return "sitio_no_verificado"
    if otra != url or norm(frente) != norm(front):
        return "sitio_no_verificado"
    return None


def finish(action: dict, how: str | None, pointer) -> str:
    """Última revisión justo antes de mover: código, parada, denylist, sesión vigente y turno."""
    if how == "cancelar" or how is None:
        clear_pending()
        return "CANCELADO"
    if how == "autonomo" and not auto_ok(action):
        clear_pending()
        return "BLOQUEADO"
    if how not in {"codigo", "autonomo"} or stopped() or denial(action) or not session_open():
        clear_pending()
        return "BLOQUEADO"
    current = read_lock()
    if current is None or current["agent"] != action.get("agent"):
        clear_pending()
        return "RECHAZADO"
    if how == "autonomo":
        why = frente_seguro(action, pointer)
        if why:
            clear_pending()
            return "BLOQUEADO"
    perform(action, pointer)
    return "HECHO"


class MacPointer:
    """pyautogui solo después de confirmación. FAILSAFE: esquina superior izquierda (apagado solo en modo
    autónomo; STOP sigue valiendo)."""

    def __init__(self, failsafe: bool = True):
        import pyautogui
        pyautogui.FAILSAFE = failsafe
        pyautogui.PAUSE = 0
        self.pg = pyautogui

    def frontmost(self) -> str:
        if sys.platform != "darwin":
            return ""
        import subprocess
        out = subprocess.run(["osascript", "-e", 'tell application "System Events" to get name of first '
                              'application process whose frontmost is true'], capture_output=True, text=True, timeout=5)
        return out.stdout.strip()

    def page_url(self) -> str:
        if sys.platform != "darwin":
            return ""
        import subprocess
        out = subprocess.run(
            ["osascript", "-e", 'tell application "Safari" to get URL of current tab of front window'],
            capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""

    def move(self, x: int, y: int) -> None:
        self.pg.moveTo(x, y, duration=0.16, tween=self.pg.easeOutQuad)

    def click(self, x: int, y: int) -> None:
        self.pg.click(x, y)

    def double_click(self, x: int, y: int) -> None:
        self.pg.doubleClick(x, y)

    def scroll(self, dy: int) -> None:
        self.pg.scroll(dy)

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)

    def write(self, text: str) -> None:
        self.pg.write(text, interval=0.02)

    def hotkey(self, keys: list[str]) -> None:
        mapped = ["command" if key == "command" else key for key in keys]
        self.pg.hotkey(*mapped)

    def shot(self, path: Path) -> None:
        self.pg.screenshot(str(path))

    def open_url(self, url: str) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("abrir url solo en la Mac")
        import subprocess
        subprocess.run(["open", safe_url(url)], check=True)

    def open_app(self, app: str) -> None:
        if sys.platform != "darwin":
            raise RuntimeError("abrir app solo en la Mac")
        import subprocess
        subprocess.run(["open", "-a", app], check=True)


def wait_confirm(pending: dict) -> str | None:
    import select
    print(f"Pendiente: {pending.get('detail') or pending['action']}.\n"
          f"Escribe el código de un solo uso {pending['code']} para confirmar. Un gesto ✊ solo cancela. "
          f"Tienes {CONFIRM_SECONDS} s.")
    deadline = time.monotonic() + CONFIRM_SECONDS
    while time.monotonic() < deadline:
        if stopped():
            return None
        decision = consume_decision(pending)
        if decision:
            return decision
        ready, _, _ = select.select([sys.stdin], [], [], 0.2)
        if not ready:
            continue
        line = sys.stdin.readline()
        if line == "":
            return None
        got = answer_of(pending, line.strip())
        if got:
            return got
        print("No vale. El codigo es de un solo uso.")
    return None


def run_actions(path: Path, *, dry: bool, libre: bool, pointer=None, automatic: bool = False,
                retry: list | None = None) -> int:
    """retry (opcional): recibe las líneas frenadas solo por ritmo, para reencolarlas sin perderlas."""
    if not path.is_file():
        print("RECHAZADO archivo")
        return 2
    if dry:
        return _run_actions(path, dry=True, libre=libre, pointer=pointer, automatic=automatic)
    try:
        with _owner_flock("ejecutor.lock", wait=False):   # un solo ejecutor real a la vez
            return _run_actions(path, dry=False, libre=libre, pointer=pointer, automatic=automatic, retry=retry)
    except BlockingIOError:
        if retry is not None:   # nada se ejecutó: todo el lote vuelve a la cola
            retry.extend(raw for raw in path.read_text(encoding="utf-8").splitlines() if raw.strip())
        print("OCUPADO otro ejecutor está corriendo. No ejecuté nada.")
        return 2


def _run_actions(path: Path, *, dry: bool, libre: bool, pointer=None, automatic: bool = False,
                 retry: list | None = None) -> int:
    recent = load_rate()
    worst = 0
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        if len(raw) > MAX_LINE:
            print(f"{line_no} RECHAZADO largo")
            worst = 2
            continue
        try:
            action = json.loads(raw)
        except ValueError:
            print(f"{line_no} RECHAZADO json")
            worst = 2
            continue
        if not isinstance(action, dict):
            print(f"{line_no} RECHAZADO json")
            worst = 2
            continue
        acquired = False
        if autonomo() and not dry and auto_ok(action) and read_lock() is None:
            if stopped():
                print(f"{line_no} BLOQUEADO stop")
                audit(action, "BLOQUEADO", "stop", dry=False)
                worst = max(worst, 3)
                continue
            if take_lock(action.get("agent"), AUTO_LOCK_MINUTES) == 0:
                acquired = True
        elif automatic and not dry:
            blocked = "STOP activo" if stopped() else ("sesión vencida o inválida; usa --start-session" if not session_open() else denial(action))
            if blocked:
                print(f"{line_no} BLOQUEADO automatico: {blocked}")
                audit(action, "BLOQUEADO", blocked, dry=False)
                worst = max(worst, 3)
                continue
            with _owner_flock("permisos.lock"):
                secret = _grant_key(create=False)
                approved = secret is not None and any(_grant_valid(g, action_key(action), secret, _spent()) for g in _grants())
            if not approved:
                print(f"{line_no} ESPERA confirmacion")
                audit(action, "ESPERA", "permiso ausente, vencido o consumido", dry=False)
                worst = max(worst, 3)
                continue
            if read_lock() is not None:
                print(f"{line_no} OCUPADO turno existente")
                audit(action, "OCUPADO", "turno existente", dry=False)
                worst = max(worst, 2)
                continue
            if take_lock(action.get("agent"), 5) != 0:
                worst = max(worst, 2)
                continue
            acquired = True
        verdict, reason = judge(action, recent)
        save_rate(recent)
        if verdict != "SECO":
            if acquired:
                release_lock(action["agent"])
            audit(action, verdict, reason, dry=dry)
            print(f"{line_no} {verdict} {reason} {action.get('agent')} {action.get('action')}")
            if retry is not None and verdict == "BLOQUEADO" and reason == "ritmo":
                retry.append(raw)   # reintentable: no se pierde, vuelve a la cola tras la ventana
            worst = max(worst, 2 if verdict == "RECHAZADO" else 3)
            continue
        if dry:
            audit(action, "SECO", reason, dry=True)
            print(f"{line_no} SECO {reason} {action.get('agent')} {action.get('action')}")
            continue
        how = "autonomo" if auto_ok(action) else consume_grant(action)
        if how is None and sys.stdin.isatty() and not automatic:
            pending = begin_pending(action)
            how = wait_confirm(pending)
        elif how is None:
            if acquired:
                release_lock(action["agent"])
            audit(action, "ESPERA", "confirmacion", dry=False)
            print(f"{line_no} ESPERA confirmacion {action.get('agent')} {action.get('action')}")
            worst = 3
            continue
        try:
            result = finish(action, how, pointer)
        except Exception as exc:
            result = "BLOQUEADO"
            print(f"Control detenido: {type(exc).__name__}")
            (control_dir() / "STOP").touch()
        finally:
            if acquired:
                release_lock(action["agent"])
        audit(action, result, how or "tiempo", dry=False)
        print(f"{line_no} {result} {action.get('agent')} {action.get('action')}")
        if result != "HECHO":
            worst = 3
    return worst


def write_ax_status() -> None:
    """Deja en ~/.jarvis-control/accesibilidad.json si ESTE proceso (python3.9 del LaunchAgent) tiene Accesibilidad.
    Solo lectura de macOS (AXIsProcessTrusted); no pide ni concede nada."""
    trusted = None
    try:
        import ctypes
        lib = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        trusted = bool(lib.AXIsProcessTrusted())
    except Exception:  # noqa: BLE001 - fuera de macOS: desconocido
        trusted = None
    try:
        (control_dir() / "accesibilidad.json").write_text(json.dumps(
            {"trusted": trusted, "python": sys.executable, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}), encoding="utf-8")
    except OSError:
        pass


def run_autonomo(pointer, *, ciclos: int | None = None, pausa: float = 1.0) -> int:
    """Bucle 24/7: lee órdenes nuevas de ~/.jarvis-control/autonomo/entrada.jsonl, las pasa por la misma
    revisión (STOP, denylist, ritmo, turno, lista segura) y las archiva. Con STOP no ejecuta nada."""
    if not autonomo():
        print("RECHAZADO modo autónomo apagado (JARVIS_AUTONOMO=1 o --autonomo).")
        return 2
    folder = control_dir() / "autonomo"
    folder.mkdir(parents=True, exist_ok=True)
    entrada, hechas = folder / "entrada.jsonl", folder / "procesadas.jsonl"
    vuelta = 0
    while ciclos is None or vuelta < ciclos:
        vuelta += 1
        heartbeat()
        if vuelta == 1 or vuelta % 30 == 0:
            write_ax_status()
        if not stopped():
            # Lotes pendientes primero (de un reinicio o reencolados por ritmo), del más viejo al más nuevo.
            if entrada.exists() and entrada.stat().st_size:
                os.replace(entrada, folder / f"lote-{int(time.time() * 1000)}.jsonl")
            ahora_ms = int(time.time() * 1000)
            for lote in sorted(folder.glob("lote-*.jsonl"), key=_lote_ms):
                if stopped():
                    break   # el resto queda en disco hasta que quiten STOP
                if _lote_ms(lote) > ahora_ms:
                    continue   # reencolado: espera a que pase la ventana de ritmo
                pendientes: list[str] = []
                run_actions(lote, dry=False, libre=False, pointer=pointer, retry=pendientes)
                with hechas.open("a", encoding="utf-8") as handle:
                    handle.write(f"# lote {stamp(now())}\n")
                if pendientes:
                    siguiente = folder / f"lote-{int(time.time() * 1000) + 60_000}.jsonl"
                    while siguiente.exists():
                        siguiente = folder / f"lote-{_lote_ms(siguiente) + 1}.jsonl"
                    tmp = siguiente.with_suffix(".tmp")
                    tmp.write_text("\n".join(pendientes) + "\n", encoding="utf-8")
                    os.replace(tmp, siguiente)
                lote.unlink(missing_ok=True)
        if ciclos is None or vuelta < ciclos:
            time.sleep(pausa)
    return 0


def _lote_ms(path: Path) -> int:
    try:
        return int(path.stem.split("-", 1)[1])
    except (IndexError, ValueError):
        return 0


def otorgar(path: Path, hours: float = GRANT_HOURS, *, ask=None, tty: bool | None = None) -> int:
    """El dueño aprueba una vez, antes de irse. Muestra cada orden, pide teclear un código que solo sale en su
    pantalla y entonces firma un permiso de un uso por orden. Un agente sin terminal no puede otorgarse nada."""
    if not path.is_file():
        print("RECHAZADO archivo")
        return 2
    if tty is None:
        tty = sys.stdin.isatty()
    if not tty:
        print("RECHAZADO --otorgar solo se usa desde tu terminal, escribiendo el código. No otorgué nada.")
        return 2
    if not 0 < hours <= MAX_GRANT_HOURS:
        print(f"RECHAZADO horas entre 1 y {MAX_GRANT_HOURS}")
        return 2
    worst, ready = 0, []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            action = json.loads(raw)
        except ValueError:
            print(f"{line_no} RECHAZADO json")
            worst = 2
            continue
        if not isinstance(action, dict) or denial(action) or action.get("agent") not in AGENTS:
            print(f"{line_no} BLOQUEADO {action.get('agent') if isinstance(action, dict) else ''}")
            worst = 3
            continue
        print(f"{line_no} PROPUESTA {describe(action)}")
        ready.append((line_no, action))
    if not ready:
        return worst or 3
    code = secrets.token_hex(3)
    ask = ask or input
    try:
        typed = str(ask(f"Para aprobar {len(ready)} orden(es), una vez cada una y por {hours:g} h, escribe {code}: "))
    except EOFError:
        typed = ""
    if not secrets.compare_digest(typed.strip(), code):
        print("CANCELADO. No otorgué nada.")
        return 3
    for line_no, action in ready:
        if not grant_once(action, hours):
            print(f"{line_no} BLOQUEADO {action.get('agent')} {action.get('action')}")
            worst = 3
            continue
        print(f"{line_no} OTORGADO {describe(action)} · vence en {hours:g} h")
    return worst


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as owner_tmp:
        os.environ["JARVIS_CONTROL_DIR"] = tmp
        os.environ["JARVIS_OWNER_DIR"] = owner_tmp
        assert take_lock("claude", 10) == 0
        assert "claude" in (control_dir() / "lock.json").read_text(encoding="utf-8")
        assert take_lock("chatgpt", 10) == 2
        assert release_lock("chatgpt") == 2
        assert release_lock("yullian") == 0
        assert take_lock("gestos", 31) == 2
        write_lock("claude", 10)
        expired = {"agent": "claude", "expires": stamp(now() - timedelta(seconds=1))}
        (control_dir() / "lock.json").write_text(json.dumps(expired), encoding="utf-8")
        assert read_lock() is None
        assert take_lock("grok", 5) == 0

        samples = [
            ({"agent": "grok", "action": "click", "x": 10, "y": 10}, "SECO", "supervisado"),
            ({"agent": "chatgpt", "action": "click", "x": 10, "y": 10}, "RECHAZADO", "turno"),
            ({"agent": "grok", "action": "open_url", "url": "https://www.paypal.com/checkout"}, "BLOQUEADO", "denylist"),
            ({"agent": "grok", "action": "type", "text": "sudo reboot"}, "BLOQUEADO", "denylist"),
            ({"agent": "grok", "action": "type", "text": "rm -rf /tmp/nada"}, "BLOQUEADO", "denylist"),
            ({"agent": "grok", "action": "type", "text": "curl https://example.invalid"}, "BLOQUEADO", "denylist"),
            ({"agent": "grok", "action": "type", "text": "hola", "enter": True}, "BLOQUEADO", "enter"),
            ({"agent": "grok", "action": "hotkey", "keys": ["cmd", "q"]}, "BLOQUEADO", "atajo"),
            ({"agent": "grok", "action": "open_app", "app": "Terminal"}, "BLOQUEADO", "app"),
            ({"agent": "grok", "action": "open_url", "url": "https://github.com/"}, "SECO", "libre"),
            ({"agent": "grok", "action": "open_app", "app": "Safari"}, "SECO", "libre"),
            ({"agent": "grok", "action": "scroll", "dy": -1}, "SECO", "libre"),
            ({"agent": "grok", "action": "move", "x": 1, "y": 1, "nota": "abre el banco"}, "BLOQUEADO", "denylist"),
        ]
        recent: list[datetime] = []
        for action, verdict, reason in samples:
            got = judge(action, recent)
            if got != (verdict, reason):
                raise SystemExit(f"fallo {action} -> {got}")
            audit(action, verdict, reason)
        audit_text = (control_dir() / "audit.jsonl").read_text(encoding="utf-8")
        if "sudo reboot" in audit_text or "paypal.com" in audit_text:
            raise SystemExit("la auditoria guardo texto")
        burst: list[datetime] = []
        for _ in range(MAX_PER_MINUTE):
            assert judge({"agent": "grok", "action": "wait", "seconds": 0}, burst)[0] == "SECO"
        assert judge({"agent": "grok", "action": "wait", "seconds": 0}, burst) == ("BLOQUEADO", "ritmo")
        (control_dir() / "STOP").write_text("1", encoding="utf-8")
        assert judge({"agent": "grok", "action": "wait"}, []) == ("BLOQUEADO", "stop")
        (control_dir() / "STOP").unlink()
        (control_dir() / "session.json").write_text(
            json.dumps({"started": stamp(now() - timedelta(seconds=SESSION_SECONDS + 5))}),
            encoding="utf-8",
        )
        assert judge({"agent": "grok", "action": "wait"}, []) == ("BLOQUEADO", "sesion")
        folder = Path(tmp) / "ej"
        folder.mkdir()
        sample = folder / "acciones.jsonl"
        sample.write_text(json.dumps({"agent": "grok", "action": "move", "x": 1, "y": 1}) + "\n", encoding="utf-8")
        (control_dir() / "session.json").unlink()
        assert run_actions(sample, dry=True, libre=False) == 0

        class Fake:
            def __init__(self):
                self.calls = []
            def move(self, x, y):
                self.calls.append(("move", x, y))
            def click(self, x, y):
                self.calls.append(("click", x, y))
            def double_click(self, x, y):
                self.calls.append(("double", x, y))
            def scroll(self, dy):
                self.calls.append(("scroll", dy))
            def wait(self, seconds):
                self.calls.append(("wait", seconds))
            def write(self, text):
                self.calls.append(("write", len(text)))
            def hotkey(self, keys):
                self.calls.append(("hotkey", tuple(keys)))
            def shot(self, path):
                self.calls.append(("shot",))
            def open_url(self, url):
                self.calls.append(("url", url))
            def open_app(self, app):
                self.calls.append(("app", app))

        write_lock("jarvis", 10)
        (control_dir() / "session.json").unlink()
        jarvis_scroll = {"agent": "jarvis", "action": "scroll", "dy": 1}
        assert lane(jarvis_scroll) == "supervisado"
        assert needs_confirm(jarvis_scroll, True) is True
        recent = []
        assert judge(jarvis_scroll, recent) == ("SECO", "supervisado")
        pending = begin_pending(jarvis_scroll)
        saved = pending["code"]
        assert answer_of(pending, "no") is None
        assert answer_of(pending, saved) == "codigo"
        assert answer_of(pending, saved) is None
        fake = Fake()
        assert finish(jarvis_scroll, "codigo", fake) == "HECHO"
        assert fake.calls == [("scroll", 1)]
        blocked = {"agent": "jarvis", "action": "open_url", "url": "https://paypal.com/checkout"}
        assert finish(blocked, "tecla", fake) == "BLOQUEADO"
        assert len(fake.calls) == 1
        pending = begin_pending(jarvis_scroll)
        assert note_gesture(True) == "anotado"
        assert consume_decision(pending) == "cancelar"                    # un gesto (o un archivo falso) no confirma
        assert consume_decision(pending) is None
        assert finish(jarvis_scroll, "gesto", fake) == "BLOQUEADO"
        assert finish(jarvis_scroll, "tecla", fake) == "BLOQUEADO"
        assert len(fake.calls) == 1
        pending = begin_pending(jarvis_scroll)
        assert pending["code"] not in (control_dir() / "pendiente.json").read_text(encoding="utf-8")
        assert answer_of(pending, "s") is None
        typed = {"agent": "jarvis", "action": "type", "text": "nota ficticia"}
        pending = begin_pending(typed)
        assert answer_of(pending, pending["code"]) == "codigo"
        assert finish(typed, "codigo", fake) == "HECHO"
        assert fake.calls[-1] == ("write", 13)
        if "nota ficticia" in (control_dir() / "audit.jsonl").read_text(encoding="utf-8"):
            raise SystemExit("la auditoria guardo texto")
        assert not (control_dir() / "clicks").exists()

        class Mover:
            def __init__(self):
                self.calls = []
            def move(self, x, y):
                self.calls.append(("move", x, y))
            def scroll(self, dy):
                self.calls.append(("scroll", dy))
            def wait(self, seconds):
                self.calls.append(("wait", seconds))
            def shot(self, path):
                self.calls.append(("shot",))
            def click(self, x, y):
                self.calls.append(("click", x, y))
            def double_click(self, x, y):
                self.calls.append(("double", x, y))
            def write(self, text):
                self.calls.append(("write", len(text)))
            def hotkey(self, keys):
                self.calls.append(("hotkey", tuple(keys)))
            def open_url(self, url):
                self.calls.append(("url", url))
            def open_app(self, app):
                self.calls.append(("app", app))

        ordenes = [
            {"agent": "jarvis", "action": "move", "x": 720, "y": 450},
            {"agent": "chatgpt", "action": "screenshot"},
            {"agent": "grok", "action": "scroll", "dy": -3},
            {"agent": "claude", "action": "wait", "seconds": 1},
        ]
        banco = {"agent": "claude", "action": "open_url", "url": "https://www.paypal.com/checkout"}
        assert needs_confirm(ordenes[2], True) is True
        assert grant_once(banco) is False
        mover = Mover()
        (control_dir() / "session.json").unlink(missing_ok=True)
        sueltas = folder / "sueltas.jsonl"
        sueltas.write_text("".join(json.dumps(item) + "\n" for item in ordenes), encoding="utf-8")
        assert run_actions(sueltas, dry=True, libre=False, pointer=mover) == 2
        assert mover.calls == []
        for item, esperado in zip(ordenes, [("move", 720, 450), ("shot",), ("scroll", -3), ("wait", 1.0)]):
            release_lock("yullian")
            (control_dir() / "ritmo.json").unlink(missing_ok=True)
            assert take_lock(item["agent"], 5) == 0
            (control_dir() / "session.json").unlink(missing_ok=True)
            una = folder / f"{item['agent']}.jsonl"
            una.write_text(json.dumps(item) + "\n", encoding="utf-8")
            antes = len(mover.calls)
            assert run_actions(una, dry=True, libre=False, pointer=mover) == 0
            assert len(mover.calls) == antes
            assert run_actions(una, dry=False, libre=True, pointer=mover) == 3
            assert len(mover.calls) == antes
            assert grant_once(item) is True
            assert grant_once(item) is False
            assert action_key({"agent": "grok", "action": "type", "text": "una nota"}) != action_key(
                {"agent": "grok", "action": "type", "text": "otra nota"}
            )
            assert run_actions(una, dry=False, libre=False, pointer=mover) == 0
            assert mover.calls[-1] == esperado
            assert run_actions(una, dry=False, libre=False, pointer=mover) == 3
            assert mover.calls[-1] == esperado
        antes = len(mover.calls)
        release_lock("yullian")
        assert take_lock("claude", 5) == 0
        (control_dir() / "session.json").unlink(missing_ok=True)
        mala = folder / "banco.jsonl"
        mala.write_text(json.dumps(banco) + "\n", encoding="utf-8")
        grants = _grants()
        grants.append({"key": action_key(banco), "used": False})
        _save_grants(grants)
        assert run_actions(mala, dry=False, libre=False, pointer=mover) == 3
        assert len(mover.calls) == antes
        assert consume_grant(banco) is None

        # Revisión del 9 oct: banco pegado a otras palabras, atajos con teclas de más.
        for url in ("https://www.1firstbank.com/pr/es", "https://www.bancopopular.com", "https://www.orientalbank.com",
                    "https://www.mibanco.pr", "https://venmo.com", "https://www.zellepay.com", "https://pagos.ejemplo.com"):
            assert denial({"agent": "claude", "action": "open_url", "url": url}) == "denylist", url
        assert denial({"agent": "claude", "action": "type", "text": "abre ath-movil"}) == "denylist"
        for keys in (["cmd", "shift", "q"], ["cmd", "alt", "q"], ["ctrl", "cmd", "q"], ["cmd", "alt", "backspace"]):
            assert denial({"agent": "claude", "action": "hotkey", "keys": keys}) == "atajo", keys
        for item in ordenes:
            assert denial(item) is None, item

        # Un permiso escrito a mano, vencido o reusado no mueve el puntero.
        release_lock("yullian")
        assert take_lock("grok", 5) == 0
        scroll = ordenes[2]
        una = folder / "falsa.jsonl"
        una.write_text(json.dumps(scroll) + "\n", encoding="utf-8")
        (control_dir() / "ritmo.json").unlink(missing_ok=True)
        _save_grants([{"key": action_key(scroll), "used": False}])
        antes = len(mover.calls)
        assert run_actions(una, dry=False, libre=False, pointer=mover) == 3
        assert len(mover.calls) == antes
        assert grant_once(scroll) is True
        grants = _grants()
        grants[0]["expires"] = stamp(now() + timedelta(days=30))          # alargar a mano rompe la firma
        _save_grants(grants)
        assert consume_grant(scroll) is None
        _save_grants([])
        assert grant_once(scroll, hours=1) is True
        grants = _grants()
        assert consume_grant(scroll) == "codigo"
        _save_grants(grants)                                               # volver a poner el mismo permiso
        assert consume_grant(scroll) is None
        assert grant_once(scroll, hours=25) is False                       # más de 24 h no
        assert grant_once(scroll, hours=1) is True
        grants = _grants()
        grants[0]["expires"] = stamp(now() - timedelta(seconds=1))
        secret = _grant_key(create=False)
        grants[0]["sig"] = _sign(secret, grants[0]["key"], grants[0]["expires"], grants[0]["nonce"])
        _save_grants(grants)
        assert consume_grant(scroll) is None                               # vencido, aunque esté bien firmado

        # Sin --dry-run, con permiso válido pero con el turno de OTRO agente: cero movimientos.
        release_lock("yullian")
        assert take_lock("claude", 5) == 0
        _save_grants([])
        assert grant_once(scroll) is True
        antes = len(mover.calls)
        assert run_actions(una, dry=False, libre=False, pointer=mover) == 2
        assert len(mover.calls) == antes
        assert consume_grant(scroll) == "codigo"                           # el permiso no se gastó con el rechazo

        # --otorgar: sin terminal o sin el código, no se otorga nada.
        _save_grants([])
        assert otorgar(sueltas, tty=False) == 2 and _grants() == []
        assert otorgar(sueltas, tty=True, ask=lambda _p: "000000") == 3 and _grants() == []
        shown = {}

        def owner_types(prompt):
            shown["code"] = prompt.rstrip(": ").split()[-1]
            return shown["code"]

        assert otorgar(sueltas, tty=True, ask=owner_types) == 0 and len(_grants()) == 4
        mixta = folder / "mixta.jsonl"
        mixta.write_text(json.dumps(banco) + "\n", encoding="utf-8")
        assert otorgar(mixta, tty=True, ask=owner_types) == 3

        # La sesión se revisa otra vez justo antes de mover.
        release_lock("yullian")
        assert take_lock("jarvis", 5) == 0
        (control_dir() / "session.json").write_text(
            json.dumps({"started": stamp(now() - timedelta(seconds=SESSION_SECONDS + 5))}), encoding="utf-8")
        antes = len(mover.calls)
        assert finish(ordenes[0], "codigo", mover) == "BLOQUEADO"
        assert len(mover.calls) == antes
        (control_dir() / "session.json").unlink()

        # El tope de ritmo sigue entre corridas.
        release_lock("yullian")
        assert take_lock("claude", 5) == 0
        espera = folder / "espera.jsonl"
        espera.write_text(json.dumps({"agent": "claude", "action": "wait", "seconds": 0}) + "\n", encoding="utf-8")
        save_rate([now()] * MAX_PER_MINUTE)
        assert run_actions(espera, dry=True, libre=False) == 3
        assert "ritmo" in (control_dir() / "audit.jsonl").read_text(encoding="utf-8").splitlines()[-1]
    print("SELFTEST OK")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Ejecutor local. Jarvis siempre pide confirmación.")
    parser.add_argument("--take-lock", metavar="AGENTE")
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--release-lock", metavar="NOMBRE")
    parser.add_argument("--lock-status", action="store_true")
    parser.add_argument("--status", action="store_true", help="Consulta STOP, sesión y turno sin mover el mouse.")
    parser.add_argument("--start-session", action="store_true", help="Abre 10 minutos de sesión con confirmación local; no concede permisos.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--libre", action="store_true", help="Solo agentes que no sean Jarvis, y solo la lista permitida.")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--otorgar", action="store_true",
                        help="El dueño aprueba las órdenes del archivo una vez, con un código. No mueve el mouse.")
    parser.add_argument("--horas", type=float, default=GRANT_HOURS, help=f"Vencimiento de esos permisos (máx. {MAX_GRANT_HOURS}).")
    parser.add_argument("--automatic", action="store_true", help="Ejecuta una vez las órdenes ya aprobadas, coordinando turnos; nunca pide ni concede permisos.")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--autonomo", action="store_true",
                        help="Modo autónomo 24/7 (opcional). Solo lista segura; STOP y denylist siguen valiendo.")
    args = parser.parse_args(argv)
    if args.autonomo:
        os.environ["JARVIS_AUTONOMO"] = "1"
    if args.status:
        print("STOP activo" if stopped() else "STOP desactivado")
        print(session_status())
        return lock_status()
    if args.start_session:
        return start_session()
    if args.self_test:
        return self_test()
    if args.take_lock:
        return take_lock(args.take_lock, args.minutes)
    if args.release_lock:
        return release_lock(args.release_lock)
    if args.lock_status:
        return lock_status()
    if args.autonomo and args.file is None:
        try:
            pointer = MacPointer(failsafe=False)
        except Exception as exc:
            print(f"No hay control de mouse en esta máquina ({type(exc).__name__}).")
            return 2
        return run_autonomo(pointer)
    if args.file is None:
        print("Falta --file. Nada se ejecutó.")
        return 2
    if args.otorgar:
        return otorgar(args.file, args.horas)
    if args.dry_run:
        return run_actions(args.file, dry=True, libre=False)
    try:
        pointer = MacPointer(failsafe=not autonomo())
    except Exception as exc:
        print(f"No hay control de mouse en esta máquina ({type(exc).__name__}). Usa --dry-run.")
        return 2
    return run_actions(args.file, dry=False, libre=args.libre, pointer=pointer, automatic=args.automatic)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
