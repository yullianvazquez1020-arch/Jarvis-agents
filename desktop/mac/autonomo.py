#!/usr/bin/env python3
"""Modo AUTÓNOMO del mouse de la Mac (encima de agent_executor.py).

El dueño abre la sesión en su Terminal con un código (nadie más puede). Durante la sesión UN agente
mira la pantalla (pantalla.png + estado.json) y deja su próxima orden en siguiente.json; este proceso
la valida y la ejecuta sin pedir confirmación, SOLO dentro de la lista permitida:
  move, click, double_click, scroll, screenshot, wait, type (texto corto, sin Enter ni secretos),
  open_url (hosts permitidos), open_app (apps permitidas).
En Outlook y Slack: mover, clicar, desplazar y leer; nunca escribir, enviar, responder, borrar ni ajustes.
Nunca: atajos de teclado, bancos/pagos, Mail/Mensajes/WhatsApp/Telegram, Terminal, Finder, Ajustes, borrar,
comandos ni contraseñas; tampoco clics/teclas si la app al frente está bloqueada.
Parada: mouse a la esquina superior izquierda, Ctrl+C, o crear ~/.jarvis-control/STOP.
Tope: 30 min por sesión, 20 acciones/min, 300 pasos. Bitácora sin texto (solo largo y hash).
La Mac no abre puertos: todo es por archivos locales.
"""
from __future__ import annotations

import math
import argparse
import importlib.util
import json
import secrets
import sys
import time
from datetime import timedelta
from pathlib import Path

_spec = importlib.util.spec_from_file_location("agent_executor", Path(__file__).with_name("agent_executor.py"))
ae = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ae)

AUTO_ACTIONS = {"move", "click", "double_click", "scroll", "screenshot", "wait", "type", "open_url", "open_app"}
POINTER_ACTIONS = {"click", "double_click", "type"}
BROWSERS = {"safari"}
MAX_STEPS = 300
MAX_TEXT = 200
POLL_SECONDS = 0.5
CORNER = 5          # px: la esquina superior izquierda es la parada de emergencia, nunca un destino


def auto_dir() -> Path:
    path = ae.control_dir() / "autonomo"
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_path() -> Path:
    # En la carpeta del dueño, NO en la de control: un agente no puede fabricarse una sesión autónoma.
    return ae.owner_dir() / "autonomo.json"


def read_session() -> dict | None:
    path = session_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if ae.now() < ae.parse_stamp(data["expires"]) and data["agent"] in ae.AGENTS:
            return data
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def end_session() -> None:
    session_path().unlink(missing_ok=True)


def start(agent: str, minutes: int, *, ask=None, tty=None) -> int:
    """Solo el dueño, en su Terminal, con un código de un uso."""
    if tty is None:
        tty = sys.stdin.isatty()
    if not tty:
        print("RECHAZADO: el modo autónomo solo lo abre el dueño en su Terminal.")
        return 2
    if agent not in ae.AGENTS:
        print("RECHAZADO: agente desconocido.")
        return 2
    if ae.stopped():
        print("BLOQUEADO: STOP activo. Bórralo tú (rm ~/.jarvis-control/STOP) si quieres seguir.")
        return 3
    minutes = max(1, min(ae.MAX_MINUTES, int(minutes)))
    code = secrets.token_hex(3)
    try:
        answer = (ask or input)(f"Modo AUTÓNOMO para {agent} por {minutes} min. Escribe {code} para aceptar: ")
    except EOFError:
        answer = ""
    if not secrets.compare_digest(str(answer).strip(), code):
        print("CANCELADO.")
        return 3
    if ae.take_lock(agent, minutes) != 0:
        return 3
    moment = ae.now()
    payload = {"agent": agent, "started": ae.stamp(moment), "expires": ae.stamp(moment + timedelta(minutes=minutes))}
    session_path().write_text(json.dumps(payload), encoding="utf-8")
    (auto_dir() / "siguiente.json").unlink(missing_ok=True)
    print(f"Sesión autónoma abierta hasta {payload['expires']}. Parada: esquina superior izquierda, Ctrl+C o STOP.")
    return 0


MAX_SCROLL = 50


def validate(action: dict, session: dict, size: tuple[int, int], front: str, ctx: dict | None = None) -> str | None:
    """None = se puede ejecutar. Si no, el motivo (sin repetir el texto de la orden)."""
    if not isinstance(action, dict):
        return "formato"
    kind = str(action.get("action") or "")
    if kind not in AUTO_ACTIONS:
        return "accion"            # incluye hotkey: nunca en autónomo
    if action.get("agent") != session["agent"]:
        return "agente"
    why = ae.denial(action)
    if why:
        return why
    if kind in {"move", "click", "double_click"}:
        try:
            x, y = int(action["x"]), int(action["y"])
        except (KeyError, TypeError, ValueError):
            return "coordenadas"
        if not (0 <= x < size[0] and 0 <= y < size[1]) or (x <= CORNER and y <= CORNER):
            return "coordenadas"
    if kind == "scroll":                       # números válidos antes de ejecutar: una orden mala se rechaza, no activa STOP
        dy = action.get("dy", 0)
        if isinstance(dy, bool) or not isinstance(dy, (int, float, str)):
            return "desplazamiento"
        try:
            dyf = float(dy)
        except (TypeError, ValueError):
            return "desplazamiento"
        if not math.isfinite(dyf) or dyf != int(dyf) or abs(dyf) > MAX_SCROLL:
            return "desplazamiento"
        action["dy"] = int(dyf)                    # normalizado: perform() recibe exactamente lo validado
    if kind == "wait":
        sec = action.get("seconds", 0)
        if isinstance(sec, bool) or not isinstance(sec, (int, float, str)):
            return "espera"
        try:
            secf = float(sec)
        except (TypeError, ValueError):
            return "espera"
        if not math.isfinite(secf) or not 0 <= secf <= 10:
            return "espera"
        action["seconds"] = secf
    if kind == "type":
        text = str(action.get("text") or "")
        if not text or len(text) > MAX_TEXT:
            return "texto"
    if kind == "open_url":
        url = str(action.get("url") or "").strip()
        low = url.lower()
        if not (low.startswith("https://") or low.startswith("http://")) or not ae.allowed_host(ae.host_of(url)):
            return "url"
    if kind == "open_app" and ae.norm(action.get("app") or "") not in ae.ALLOW_APPS:
        return "app"
    if kind in POINTER_ACTIONS or kind == "move":
        if not front:
            return "app_frente_desconocida"
        if ae.norm(front) in ae.DENY_APPS or ae.denied_text(front):
            return "app_frente"
        if ae.norm(front) not in ae.ALLOW_APPS:    # falla cerrado: solo apps verificadas (Mail, Mensajes, etc. nunca)
            return "app_frente"
        if ae.norm(front) in ae.MESSAGING_APPS and kind == "type":
            return "mensajeria_sin_escribir"    # en Outlook/Slack no se redacta nada: ni texto ni Enter
        if ae.norm(front) in BROWSERS:             # el clic solo vale si la página actual es el mismo sitio permitido que abrió esta sesión
            if kind == "type":
                return "texto_en_navegador"
            if kind in {"click", "double_click", "move"}:
                opened = str((ctx or {}).get("opened_host") or "")
                page = str((ctx or {}).get("page_url") or "").strip()
                low = page.lower()
                host = ae.host_of(page)
                if not (low.startswith("https://") or low.startswith("http://")) or not opened or host != opened or not ae.allowed_host(host):
                    return "sitio_no_verificado"
    return None


def confirmar_clic(pointer, front: str, ctx: dict | None, action: dict | None = None) -> str | None:
    """Justo antes de mover o clicar: la app y la página tienen que ser las que se acaban de validar."""
    try:
        ahora = pointer.frontmost() or ""
    except Exception:
        return "app_frente_desconocida"
    if ae.norm(ahora) != ae.norm(front) or ae.norm(ahora) not in ae.ALLOW_APPS:
        return "app_frente"
    if ae.norm(ahora) in ae.MESSAGING_APPS:
        if not action:
            return "ventana_no_verificada"
        return ae.mensajeria_segura(action, pointer, ahora)
    if ae.norm(ahora) not in BROWSERS:
        return None
    try:
        url = pointer.page_url() or ""
    except Exception:
        url = ""
    previa = str((ctx or {}).get("page_url") or "")
    if not url or url != previa:
        return "sitio_no_verificado"
    host = ae.host_of(url)
    if host != str((ctx or {}).get("opened_host") or "") or not ae.allowed_host(host):
        return "sitio_no_verificado"
    return None


class AutoPointer(ae.MacPointer):
    def size(self) -> tuple[int, int]:
        _x, _y, w, h = self.target_display()
        return int(w), int(h)

    def frontmost(self) -> str:
        if sys.platform != "darwin":
            return ""
        import subprocess
        out = subprocess.run(["osascript", "-e", 'tell application "System Events" to get name of first '
                              'application process whose frontmost is true'], capture_output=True, text=True, timeout=5)
        return out.stdout.strip()

    def page_url(self) -> str:
        """URL actual de Safari. Vacía si no se puede probar (otra pestaña, redirección o fallo)."""
        if sys.platform != "darwin":
            return ""
        import subprocess
        out = subprocess.run(
            ["osascript", "-e", 'tell application "Safari" to get URL of current tab of front window'],
            capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""


def observe(pointer, step: int, last: dict) -> tuple[tuple[int, int], str]:
    """Lo que el agente ve para decidir el próximo clic."""
    folder = auto_dir()
    pointer.shot(folder / "pantalla.png")
    size, front = pointer.size(), pointer.frontmost()
    estado = {"paso": step, "pantalla": "pantalla.png", "ancho": size[0], "alto": size[1],
              "cursor": list(pointer.position()), "app_al_frente": front, "ultimo": last, "at": ae.stamp(ae.now())}
    tmp = folder / "estado.json.tmp"
    tmp.write_text(json.dumps(estado, ensure_ascii=False), encoding="utf-8")
    tmp.replace(folder / "estado.json")
    return size, front


def next_action() -> dict | None:
    path = auto_dir() / "siguiente.json"
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")[: ae.MAX_LINE]
        path.unlink()
        return json.loads(raw)
    except (OSError, ValueError):
        path.unlink(missing_ok=True)
        return {"action": "invalida"}


def run(pointer, *, sleep=time.sleep, max_steps: int = MAX_STEPS) -> int:
    session = read_session()
    if session is None:
        print("Sin sesión autónoma vigente. Ábrela con: python3 autonomo.py --start AGENTE")
        return 2
    agente = session["agent"]
    recent = ae.load_rate()
    last: dict = {"resultado": "inicio"}
    step = 0
    ctx = {"web_ok": False}                        # True solo tras abrir una URL de la lista permitida en esta sesión
    try:
        while step < max_steps:
            if ae.stopped():
                last = {"resultado": "STOP"}; break
            session = read_session()
            if session is None:
                last = {"resultado": "sesion_vencida"}; break
            lock = ae.read_lock()
            if lock is None or lock["agent"] != session["agent"]:
                last = {"resultado": "turno"}; break
            size, front = observe(pointer, step, last)
            if ae.norm(front) in BROWSERS and hasattr(pointer, "page_url"):
                try:
                    ctx["page_url"] = pointer.page_url() or ""
                except Exception:
                    ctx["page_url"] = ""
            else:
                ctx["page_url"] = ""
            action = next_action()
            if action is None:
                sleep(POLL_SECONDS)
                continue
            step += 1
            moment = ae.now()
            recent[:] = [t for t in recent if (moment - t).total_seconds() < 60]
            why = "ritmo" if len(recent) >= ae.MAX_PER_MINUTE else validate(action, session, size, front, ctx)
            safe = action if isinstance(action, dict) else {}
            if not why and str(safe.get("action") or "") in {"click", "double_click", "move"}:
                why = confirmar_clic(pointer, front, ctx, safe)
            if why:
                ae.audit(safe, "BLOQUEADO", f"autonomo:{why}", dry=False)
                last = {"resultado": "BLOQUEADO", "motivo": why, "accion": safe.get("action")}
                continue
            recent.append(moment)
            ae.save_rate(recent)
            ae.perform(action, pointer)
            if action.get("action") == "open_url":
                ctx["opened_host"] = ae.host_of(str(action.get("url") or ""))
                ctx["web_ok"] = True
            elif action.get("action") == "open_app":
                ctx["opened_host"] = ""
                ctx["web_ok"] = False
            ae.audit(action, "HECHO", "autonomo", dry=False)
            last = {"resultado": "HECHO", "accion": action.get("action")}
    except KeyboardInterrupt:
        last = {"resultado": "ctrl_c"}
    except Exception as exc:  # FailSafeException (esquina) u otro: se detiene todo
        (ae.control_dir() / "STOP").touch()
        last = {"resultado": "parada", "motivo": type(exc).__name__}
    end_session()
    actual = ae.read_lock()
    if actual and actual.get("agent") == agente:
        ae.release_lock(agente)
    print(f"Modo autónomo terminado: {last.get('resultado')} ({step} pasos).")
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Modo autónomo del mouse (solo lista permitida).")
    p.add_argument("--start", metavar="AGENTE", help="Abre la sesión autónoma (código en tu Terminal).")
    p.add_argument("--minutes", type=int, default=15)
    p.add_argument("--run", action="store_true", help="Ejecuta la sesión abierta: mira la pantalla y obedece siguiente.json.")
    p.add_argument("--stop", action="store_true", help="Crea STOP y cierra la sesión.")
    a = p.parse_args(argv)
    if a.stop:
        (ae.control_dir() / "STOP").touch(); end_session(); print("STOP activo."); return 0
    if a.start:
        rc = start(a.start, a.minutes)
        if rc or not a.run:
            return rc
    if a.run:
        try:
            pointer = AutoPointer()
        except Exception as exc:
            print(f"No hay control de mouse aquí ({type(exc).__name__}). Instala pyautogui y da permisos.")
            return 2
        return run(pointer)
    p.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
