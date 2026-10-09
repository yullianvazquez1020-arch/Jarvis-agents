#!/usr/bin/env python3
"""Ejecutor local de la Mac. Jarvis solo propone; nada corre sin confirmación.

La denylist no se confirma. No hay WhatsApp ni mensajes a clientes.
"""
from __future__ import annotations

import argparse
import hashlib
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
MAX_LINE = 4000
APP_NAME = re.compile(r"^[A-Za-z0-9 ._-]{1,40}$")

DENY_RE = re.compile(
    r"\b(bank|banco|popular|stripe|checkout|paypal|coinbase|firstbank|"
    r"equifax|experian|transunion|annualcreditreport|creditkarma)\b|ath\s*movil|"
    r"\b\d{3}-\d{2}-\d{4}\b"
)
SECRET_RE = re.compile(r"\b(sudo|curl|password|contrasena|clave)\b|\brm\s+-")
DENY_APPS = {
    "terminal", "iterm", "finder", "system settings", "system preferences",
    "ajustes", "llavero", "keychain access", "keychain", "mail", "mail.app",
    "mensajes", "messages", "whatsapp", "telegram",
}
DANGEROUS = {
    frozenset({"command", "backspace"}),
    frozenset({"command", "q"}),
    frozenset({"command", "alt", "escape"}),
    frozenset({"command", "space"}),
    frozenset({"command", "enter"}),
}
FREE_ACTIONS = {"scroll", "screenshot", "wait", "move"}
ALLOW_HOSTS = {"github.com", "jarvis-agents.onrender.com", "127.0.0.1", "localhost"}
ALLOW_APPS = {"notes", "safari"}
KEY_ALIAS = {
    "cmd": "command", "meta": "command", "option": "alt",
    "delete": "backspace", "return": "enter", "spacebar": "space",
}


def control_dir() -> Path:
    raw = os.environ.get("JARVIS_CONTROL_DIR", "").strip()
    path = Path(raw) if raw else Path.home() / ".jarvis-control"
    path.mkdir(parents=True, exist_ok=True)
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


def session_open() -> bool:
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


def hotkey_set(keys) -> frozenset[str]:
    if not isinstance(keys, list) or not keys:
        return frozenset()
    return frozenset(KEY_ALIAS.get(str(key).lower(), str(key).lower()) for key in keys)


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


def denial(action: dict) -> str | None:
    kind = str(action.get("action") or "")
    folded = norm(" ".join(_textos(action)))
    if DENY_RE.search(folded):
        return "denylist"
    if kind == "type":
        text = str(action.get("text") or "")
        if SECRET_RE.search(norm(text)):
            return "denylist"
        if "\n" in text or "\r" in text or action.get("enter") is True:
            return "enter"
    if kind == "hotkey" and hotkey_set(action.get("keys")) in DANGEROUS:
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


def action_key(action: dict) -> str:
    text = str(action.get("text") or "")
    keys = sorted(hotkey_set(action.get("keys")))
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


def _grants() -> list[dict]:
    path = control_dir() / "usos.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    grants = data.get("grants") if isinstance(data, dict) else None
    return grants if isinstance(grants, list) else []


def _save_grants(grants: list[dict]) -> None:
    _write_json("usos.json", {"grants": grants})


def grant_once(action: dict) -> bool:
    if denial(action) or action.get("agent") not in AGENTS:
        return False
    key = action_key(action)
    grants = _grants()
    if any(item.get("key") == key and item.get("used") is not True for item in grants):
        return False
    grants.append({"key": key, "used": False})
    _save_grants(grants)
    return True


def consume_grant(action: dict) -> str | None:
    if denial(action):
        return None
    key = action_key(action)
    grants = _grants()
    for grant in grants:
        if grant.get("key") == key and grant.get("used") is not True:
            grant["used"] = True
            _save_grants(grants)
            return "codigo"
    return None


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
        "expires": stamp(now() + timedelta(seconds=CONFIRM_SECONDS)),
    }
    _write_json("pendiente.json", {"pending": pending, "action": action})
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
    burn(pending)
    return "gesto" if data.get("ok") is True else "cancelar"


def answer_of(pending: dict, answer: str) -> str | None:
    if answer == "s":
        burn(pending)
        return "tecla"
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
        pointer.hotkey(sorted(hotkey_set(action.get("keys"))))
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


def finish(action: dict, how: str | None, pointer) -> str:
    current = read_lock()
    if how == "cancelar" or how is None:
        clear_pending()
        return "CANCELADO"
    if how not in {"tecla", "codigo", "gesto"} or stopped() or denial(action):
        clear_pending()
        return "BLOQUEADO"
    if current is None or current["agent"] != action.get("agent"):
        clear_pending()
        return "RECHAZADO"
    perform(action, pointer)
    return "HECHO"


class MacPointer:
    """pyautogui solo después de confirmación. FAILSAFE: esquina superior izquierda."""

    def __init__(self):
        import pyautogui
        pyautogui.FAILSAFE = True
        pyautogui.PAUSE = 0.05
        self.pg = pyautogui

    def move(self, x: int, y: int) -> None:
        self.pg.moveTo(x, y)

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
    print(f"Pendiente {pending['action']} de {pending['agent']}. "
          f"Codigo de un solo uso: {pending['code']}. s lo confirma, ✊ cancela. {CONFIRM_SECONDS}s.")
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


def run_actions(path: Path, *, dry: bool, libre: bool, pointer=None) -> int:
    if not path.is_file():
        print("RECHAZADO archivo")
        return 2
    recent: list[datetime] = []
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
        verdict, reason = judge(action, recent)
        if verdict != "SECO":
            audit(action, verdict, reason, dry=dry)
            print(f"{line_no} {verdict} {reason} {action.get('agent')} {action.get('action')}")
            worst = max(worst, 2 if verdict == "RECHAZADO" else 3)
            continue
        if dry:
            audit(action, "SECO", reason, dry=True)
            print(f"{line_no} SECO {reason} {action.get('agent')} {action.get('action')}")
            continue
        how = consume_grant(action)
        if how is None and sys.stdin.isatty():
            pending = begin_pending(action)
            how = wait_confirm(pending)
        elif how is None:
            audit(action, "ESPERA", "confirmacion", dry=False)
            print(f"{line_no} ESPERA confirmacion {action.get('agent')} {action.get('action')}")
            worst = 3
            continue
        result = finish(action, how, pointer)
        audit(action, result, how or "tiempo", dry=False)
        print(f"{line_no} {result} {action.get('agent')} {action.get('action')}")
        if result != "HECHO":
            worst = 3
    return worst


def otorgar(path: Path) -> int:
    if not path.is_file():
        print("RECHAZADO archivo")
        return 2
    worst = 0
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
        if not grant_once(action):
            print(f"{line_no} BLOQUEADO {action.get('agent')} {action.get('action')}")
            worst = 3
            continue
        print(f"{line_no} OTORGADO {action.get('agent')} {action.get('action')}")
    return worst


def self_test() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["JARVIS_CONTROL_DIR"] = tmp
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
        assert consume_decision(pending) == "gesto"
        assert consume_decision(pending) is None
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
    print("SELFTEST OK")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Ejecutor local. Jarvis siempre pide confirmación.")
    parser.add_argument("--take-lock", metavar="AGENTE")
    parser.add_argument("--minutes", type=int, default=10)
    parser.add_argument("--release-lock", metavar="NOMBRE")
    parser.add_argument("--lock-status", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--libre", action="store_true", help="Solo agentes que no sean Jarvis, y solo la lista permitida.")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--otorgar", action="store_true", help="Crea confirmaciones de un uso. No mueve el mouse.")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.take_lock:
        return take_lock(args.take_lock, args.minutes)
    if args.release_lock:
        return release_lock(args.release_lock)
    if args.lock_status:
        return lock_status()
    if args.file is None:
        print("Falta --file. Nada se ejecutó.")
        return 2
    if args.otorgar:
        return otorgar(args.file)
    if args.dry_run:
        return run_actions(args.file, dry=True, libre=False)
    try:
        pointer = MacPointer()
    except Exception as exc:
        print(f"No hay control de mouse en esta máquina ({type(exc).__name__}). Usa --dry-run.")
        return 2
    return run_actions(args.file, dry=False, libre=args.libre, pointer=pointer)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
