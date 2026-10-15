"""Puente del display con el mouse autónomo de la Mac (desktop/mac/autonomo.py). Sin botones manuales.

- estado(): solo lectura (sesión abierta por el dueño, agente, vencimiento, STOP).
- encargar(): Jarvis deja UNA orden de investigación en siguiente.json. Solo si el dueño abrió la sesión
  en su Terminal, no hay STOP y la orden pasa la lista permitida. El ejecutor de la Mac la valida otra vez
  (app al frente, esquina de parada, topes) antes de mover nada.
Nunca: bancos/pagos, mensajes/correo, Terminal, Finder, Ajustes, borrar, contraseñas, atajos.
Lo financiero o de mensajes sigue necesitando /confirmar en Jarvis; aquí ni se intenta.
"""
import importlib.util
import json
import os
import threading
from pathlib import Path

_spec = importlib.util.spec_from_file_location("autonomo", Path(__file__).parent / "mac" / "autonomo.py")
auto = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(auto)
ae = auto.ae

INVESTIGACION = {"scroll", "screenshot", "wait", "open_url", "open_app", "move", "click", "double_click", "type"}


LATIDO_MAX_S = 20    # el agente launchd (agent_executor --autonomo) escribe su latido cada ~1 s


def agente_vivo() -> bool:
    """True si el LaunchAgent com.jarvis.mouse-autonomo está corriendo (latido reciente en autonomo.json)."""
    try:
        data = json.loads((ae.control_dir() / "autonomo.json").read_text(encoding="utf-8"))
        edad = (ae.now() - ae.parse_stamp(data["latido"])).total_seconds()
        return 0 <= edad <= LATIDO_MAX_S
    except (OSError, ValueError, KeyError, TypeError):
        return False


def estado():
    s = auto.read_session()
    return {"disponible": True, "stop": bool(ae.stopped()), "sesion": bool(s), "launchd": agente_vivo(),
            "agente": s["agent"] if s else None, "vence": s["expires"] if s else None,
            "apps": sorted(ae.ALLOW_APPS),
            "parada": "esquina superior izquierda · Ctrl+C · ~/.jarvis-control/STOP",
            "nota": "La sesión solo la abre el dueño en su Terminal (python3 desktop/mac/autonomo.py). "
                    "El puntero solo se mueve en Notes y Safari. Outlook, Slack y el correo no."}


def precheck(action, session):
    """Mismas reglas que el ejecutor, salvo lo que solo se sabe en la Mac (pantalla y app al frente)."""
    if not isinstance(action, dict) or str(action.get("action") or "") not in INVESTIGACION:
        return "accion"
    if action.get("agent") != session["agent"]:
        return "agente"
    why = ae.denial(action)
    if why:
        return why
    kind = action["action"]
    if kind == "open_url" and not ae.allowed_host(ae.host_of(str(action.get("url") or ""))):
        return "url"
    if kind == "open_app" and ae.norm(action.get("app") or "") not in ae.ALLOW_APPS:
        return "app"
    if kind == "type":
        t = str(action.get("text") or "")
        if not t or len(t) > auto.MAX_TEXT:
            return "texto"
    if kind in {"move", "click", "double_click"}:
        try:
            x, y = int(action["x"]), int(action["y"])
        except (KeyError, TypeError, ValueError):
            return "coordenadas"
        if x <= auto.CORNER and y <= auto.CORNER:
            return "coordenadas"
    return None


_ORDEN_LOCK = threading.Lock()


def encargar(action):
    if ae.stopped():
        return {"ok": False, "motivo": "STOP activo"}
    s = auto.read_session()
    if not s:
        # Antes: sin la sesión de autonomo.py el pedido moría aquí, aunque el dueño hubiera instalado el
        # LaunchAgent (que lee entrada.jsonl, no siguiente.json). Ahora va a ese agente si está vivo; el
        # agente vuelve a validar STOP, denylist, ritmo, turno y app al frente (solo Notes y Safari).
        if not agente_vivo():
            return {"ok": False, "motivo": "agente del mouse apagado: bash desktop/mac/instalar_mouse_autonomo.sh instalar"}
        action = dict(action or {}); action["agent"] = ae.AUTO_AGENT
        why = precheck(action, {"agent": ae.AUTO_AGENT})
        if why:
            return {"ok": False, "motivo": why}
        folder = ae.control_dir() / "autonomo"; folder.mkdir(parents=True, exist_ok=True)
        with _ORDEN_LOCK, (folder / "entrada.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(action) + "\n")
        return {"ok": True, "orden": action["action"], "via": "launchd"}
    action = dict(action or {}); action.setdefault("agent", s["agent"])
    why = precheck(action, s)
    if why:
        return {"ok": False, "motivo": why}
    path = auto.auto_dir() / "siguiente.json"
    with _ORDEN_LOCK:                                    # servidor con hilos: una sola orden, publicada atómica
        if path.exists():
            return {"ok": False, "motivo": "ya hay una orden pendiente"}
        tmp = path.with_name(f".siguiente.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps(action), encoding="utf-8")
        os.replace(tmp, path)
    return {"ok": True, "orden": action["action"]}
