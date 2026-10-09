# jarvis_ops.py — Jarvis 4.2.3: ruta del día, huecos y piso de ticket.
# Aditivo. No reescribe el orquestador. No envía, no publica, no cobra y no llama a un modelo.
# /piso guarda un número para comparar. No es un ingreso, no sube $100/$300 y no borra trabajos más chicos.

from __future__ import annotations

import math
from decimal import Decimal, ROUND_CEILING

import jarvis_brief as brief
import jarvis_learn as learn

VERSION = "4.2.3"
COMMANDS = {"/ruta", "/huecos", "/piso"}
PHRASES = {"ruta": "/ruta", "ruta de hoy": "/ruta", "huecos": "/huecos"}
FLOOR_FIELD = "ticket_min_usd"
MAX_HOLES = 12
NOT_DONE = "No visito, no cobro, no publico y no opero."

core = None


def ticket_floor():
    """Piso numérico guardado por el dueño, o None. Nunca un valor por defecto."""
    try:
        prof = core.kv_get(brief.PROFILE_KEY, {})
    except Exception:
        return None
    raw = prof.get(FLOOR_FIELD) if isinstance(prof, dict) else None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if not math.isfinite(raw) or raw <= 0:
        return None
    return Decimal(str(raw)).quantize(Decimal(".01"))


def _jobs():
    with core._data_lock:
        data = core._cload()
    clients = {c["id"] for c in data["clients"]}
    jobs = [job for job in data["jobs"] if job.get("status") != "cancelled"]
    return clients, jobs


def missing_of(job, clients):
    missing = []
    if float(job.get("price") or 0) <= 0:
        missing.append("precio")
    if not job.get("due_date"):
        missing.append("fecha")
    if job.get("client_id") not in clients:
        missing.append("cliente")
    if job.get("status") == "quote":
        missing.append("aprobación")
    try:
        balance = Decimal(str(job.get("balance")))
    except Exception:
        balance = None
    priced = Decimal(str(job.get("price") or 0))
    if balance == 0 and priced > 0 and not learn.completion_confirmed(job):
        missing.append("/terminado")
    return missing


def hole_rows():
    clients, jobs = _jobs()
    rows = []
    for job in sorted(jobs, key=lambda item: item["id"]):
        missing = missing_of(job, clients)
        if missing:
            rows.append((job, missing))
    return rows


def hole_lines(limit):
    rows = hole_rows()
    shown = rows[:limit]
    lines = [f"#{job['id']} «{brief._clean(job.get('title'), 60)}»: falta {', '.join(missing)}"
             for job, missing in shown]
    extra = len(rows) - len(shown)
    if extra > 0:
        lines.append(f"… y {extra} más (ver /huecos)")
    return lines or ["Ningún trabajo abierto con datos faltantes."]


def route_lines():
    stop = brief.business_check()
    if stop:
        return [stop]
    got, _count = brief.collected_this_week()
    goal = brief.weekly_goal()
    floor = ticket_floor()
    lines = [brief.marker_line() + ". Cobrado no es ganancia."]
    if goal is None:
        lines.append("Sin meta semanal. /meta N la guarda para comparar; no es un ingreso.")
    else:
        gap = max(Decimal("0.00"), (goal - got).quantize(Decimal(".01")))
        lines.append(f"Falta esta semana: {brief._usd(gap)}.")
        if floor is None:
            lines.append("Sin piso. /piso N lo guarda para comparar; no rechaza un trabajo real más chico.")
        elif gap <= 0:
            lines.append(f"Piso {brief._usd(floor)}: la meta semanal ya está cubierta en los libros.")
        else:
            need = int((gap / floor).to_integral_value(rounding=ROUND_CEILING))
            lines.append(f"Piso {brief._usd(floor)}: {need} cobro(s) de ese tamaño. Un trabajo menor no se borra.")
    return lines


def route_command():
    lines = ["RUTA — no ejecutada", *route_lines(), "HUECOS", *hole_lines(5), NOT_DONE]
    return "\n".join(lines)


def holes_command():
    stop = brief.business_check()
    if stop:
        return stop
    return "\n".join(["HUECOS — no ejecutado", *hole_lines(MAX_HOLES), NOT_DONE])


def brief_section():
    body = route_lines()
    return ["7) RUTA", *body[:3], "Detalle en /ruta. No ejecutada."]


def floor_command(arg):
    arg = str(arg or "").strip()
    if not arg:
        floor = ticket_floor()
        return (f"Piso de ticket: {brief._usd(floor)}. Es para comparar en /ruta; no borra trabajos más chicos."
                if floor is not None else "Piso de ticket: sin piso.")
    if brief._norm(arg) in ("borrar", "quitar", "ninguna"):
        with core._data_lock:
            core._check_writable()
            prof = core.kv_get(brief.PROFILE_KEY, None)
            if not isinstance(prof, dict) or FLOOR_FIELD not in prof:
                return "Piso de ticket: sin piso. No cambié nada."
            prof = dict(prof)
            prof.pop(FLOOR_FIELD, None)
            core.kv_set(brief.PROFILE_KEY, prof)
        return "Piso de ticket borrado. No toqué libros ni topes."
    try:
        value = learn.parse_goal(arg)
    except ValueError as exc:
        return "⚠️ " + str(exc)
    number = int(value) if value == value.to_integral_value() else float(value)
    if not math.isfinite(float(number)):
        return "⚠️ Piso inválido."
    with core._data_lock:
        core._check_writable()
        prof = core.kv_get(brief.PROFILE_KEY, None)
        prof = dict(prof) if isinstance(prof, dict) and prof else dict(getattr(core, "DEFAULT_PROFILE", {}) or {})
        prof[FLOOR_FIELD] = number
        core.kv_set(brief.PROFILE_KEY, prof)
    return (f"Piso guardado: {brief._usd(value)}. Sirve para /ruta. No es un ingreso, no entra en los libros "
            "y no impide anotar un trabajo menor.")


def install(j):
    global core
    core = j
    brief.REPLIES["/ruta"] = lambda arg: route_command()
    brief.REPLIES["/huecos"] = lambda arg: holes_command()
    brief.REPLIES["/piso"] = floor_command
    j._extensions.COMMANDS.update(COMMANDS)
    brief.PHRASES.update(PHRASES)
    brief.EXTRA_SECTIONS.append(brief_section)
    old_diag = j.diagnostics_text

    async def diagnostics_text():
        text = await old_diag()
        return text + f"\n• Operación 4.2.3: {getattr(j, 'OPS_STATUS', 'activo')} · /ruta /huecos /piso"

    j.diagnostics_text = diagnostics_text
    j.OPS_STATUS = "activo"
    j.HELP_TEXT += ("\n4.2.3: /ruta — falta de la semana y huecos, sin ejecutar · "
                    "/huecos — trabajos sin precio, fecha, cliente, aprobación o /terminado · "
                    "/piso [N|borrar] — ticket mínimo para comparar, no es ingreso")
