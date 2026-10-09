# jarvis_brief.py — Jarvis 4.2.1: brief comercial ISLAFIX. Aditivo; no reescribe el orquestador.
# Solo lectura y sin tokens: no envía, no publica, no aprueba, no confirma, no crea clientes ni ingresos,
# no cambia precios y no llama a proveedores de pago. Los borradores salen en el texto y no se guardan.
# Solo el chat privado del dueño. No sube $100/$300 y no toca el money gate ni /confirmar.

from __future__ import annotations

import asyncio
import datetime as dt
import math
import re
import unicodedata
from decimal import Decimal

VERSION = "4.2.1"
EXPECTED_BUSINESS = "ISLAFIX PRO LLC"
PROFILE_KEY = "jarvis:profile"
GOAL_FIELD = "meta_semanal_usd"          # lo escribe solo el dueño; aquí solo se lee
COMMANDS = {"/brief"}
DENY_TEXT = "Este comando requiere tu chat privado."
# Frase completa (normalizada) -> comando. Otros cortes pueden añadir frases; writes=True no corre en voz.
PHRASES = {"brief": "/brief", "brief de hoy": "/brief", "caja y cobros": "/brief"}
WRITING_PHRASE_COMMANDS: set = set()
REPLIES = {}                             # comando -> función sync(arg) -> texto, para frases y voz
MAX_ITEMS = 10
CREDIT_TYPES = ("CREDITCARD", "CREDITLINE", "LOAN")

core = None


def _norm(text):
    t = unicodedata.normalize("NFKD", str(text or "").casefold())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[¿?¡!.,;:«»\"']+", " ", t)
    t = re.sub(r"^\s*(oye\s+)?jarvis\b", " ", t)
    t = re.sub(r"\s+jarvis\s*$", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def phrase_command(text):
    """Solo cuando TODO el mensaje es la frase: no secuestra pedidos normales."""
    if not isinstance(text, str) or "/" in text or len(text) > 80:
        return None
    return PHRASES.get(_norm(text))


def is_brief_phrase(text):
    return phrase_command(text) == "/brief"


def _usd(value):
    return f"${float(value):,.2f}"


def _clean(text, limit=60):
    """Texto guardado por terceros (nombre de una solicitud): una línea, corto, sin comandos."""
    t = re.sub(r"\s+", " ", str(text or "")).strip().replace("/", " ")
    return core._redact_secrets(t)[0][:limit] or "cliente"


def _more(rows, where):
    """Nunca esconder en silencio lo que no cabe."""
    extra = len(rows) - MAX_ITEMS
    return [f"… y {extra} más (ver {where})."] if extra > 0 else []


def _date(value):
    try:
        return dt.date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def business_check():
    """-> texto de parada, o None si el negocio guardado es ISLAFIX PRO LLC."""
    name = str(getattr(core, "BUSINESS_NAME", "") or "").strip()
    if _norm(name) != _norm(EXPECTED_BUSINESS):
        shown = name[:60] or "vacío"
        return (f"El negocio guardado («{shown}») no coincide con {EXPECTED_BUSINESS}. "
                "Me detengo: no armo el brief ni doy de alta otro negocio. Revisa BUSINESS_NAME en Render.")
    return None


def weekly_goal():
    """Meta semanal numérica guardada por el dueño, o None. Nunca un valor por defecto."""
    try:
        prof = core.kv_get(PROFILE_KEY, {})
    except Exception:
        return None
    raw = prof.get(GOAL_FIELD) if isinstance(prof, dict) else None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    if not math.isfinite(raw) or raw <= 0:
        return None
    return Decimal(str(raw)).quantize(Decimal(".01"))


def week_bounds(today=None):
    today = today or core._today()
    monday = today - dt.timedelta(days=today.weekday())
    return monday, today


def collected_this_week():
    """USD ya registrados de lunes a hoy (America/Puerto_Rico). Sin futuros, sin fecha, sin otras monedas."""
    monday, today = week_bounds()
    total, count = Decimal(0), 0
    with core._data_lock:
        income = core._bload()["income"]
    for x in income:
        if str(x.get("currency", "USD")).upper() != "USD":
            continue
        when = _date(x.get("date"))
        if when is None or not monday <= when <= today:
            continue
        try:
            amount = Decimal(str(x.get("amount")))
        except Exception:
            continue
        if amount.is_finite() and amount > 0:
            total += amount
            count += 1
    return total.quantize(Decimal(".01")), count


# --- 1. Caja ---------------------------------------------------------------------------------------------------
def section_cash(report):
    lines = ["1) CAJA"]
    chosen = report.get("selected")
    observed = report.get("observed") or []
    if chosen:
        tag = ""
        if chosen.get("stale"):
            tag = f" — SALDO VIEJO ({chosen['stale_days']} días)"
        if chosen.get("future_date"):
            tag = " — FECHA FUTURA, no válida"
        if str(chosen.get("type", "")).upper() in CREDIT_TYPES:
            tag += " — cuenta de crédito: no es caja"
        lines.append(f"Saldo observado: {_usd(chosen['balance'])} al {chosen['date']} "
                     f"({chosen.get('name') or 'cuenta'}, clave {chosen['account']}){tag}.")
    elif observed:
        lines.append("Hay más de una cuenta importada; no las sumo. Elige una con /caja CLAVE:")
        for a in observed[:MAX_ITEMS]:
            lines.append(f"• {a.get('name') or 'cuenta'} {_usd(a['balance'])} al {a['date']} (clave {a['account']})")
        lines += _more(observed, "/caja")
    else:
        lines.append("Saldo observado: sin saldo observado.")
    rec = report["recorded"]
    lines.append(f"Registrado en libros hasta hoy (USD): ingresos {_usd(rec['income'])}, gastos {_usd(rec['expenses'])}. "
                 "No es saldo bancario.")
    p = report.get("projection")
    if p:
        lines.append(f"Proyección condicional a 7 días ({p['date']}): {_usd(p['opening_observed'])} "
                     f"+ cobros futuros {_usd(p['collections'])} − pagos futuros {_usd(p['payments'])} "
                     f"= {_usd(p['end_balance'])}, solo si se cobran. Sin esos cobros: {_usd(p['without_collections'])}.")
    else:
        lines.append("Proyección a 7 días: bloqueada; no estimo. Falta: " + "; ".join(report.get("missing") or ["datos"]) + ".")
    future_in = report.get("incoming") or []
    future_out = report.get("outgoing") or []
    if future_in or future_out:
        parts = []
        if future_in:
            parts.append("cobros por vencer " + ", ".join(f"trabajo #{x['id']} {_usd(x['amount'])} el {x['date']}"
                                                         for x in future_in[:MAX_ITEMS])
                         + (f" y {len(future_in) - MAX_ITEMS} más" if len(future_in) > MAX_ITEMS else ""))
        if future_out:
            parts.append("pagos por vencer " + ", ".join(f"cuenta #{x['id']} {_usd(x['amount'])} el {x['date']}"
                                                        for x in future_out[:MAX_ITEMS])
                         + (f" y {len(future_out) - MAX_ITEMS} más" if len(future_out) > MAX_ITEMS else ""))
        lines.append("Futuro, no disponible todavía: " + "; ".join(parts) + ".")
    else:
        lines.append("Futuro: nada registrado con importe en los próximos 7 días.")
    return lines


# --- 2 y 3. Solicitudes, seguimientos y borradores ------------------------------------------------------------
def followup_items():
    """Solicitudes nuevas de ISLAFIX y seguimientos vencidos, con ids reales. Solo lectura."""
    items, notes = [], []
    bw = core._business_workflows
    with core._data_lock:
        reqs = [r for r in bw.load()["requests"] if r.get("status") == "pending"
                and _norm(r.get("business")) == _norm(EXPECTED_BUSINESS)]
        clients = core._cload()
        overdue = core.overdue_jobs()          # exige due_date: un trabajo sin fecha no está «vencido»
    notes += _more(reqs, "/solicitudes") + _more(overdue, "/cobros")
    for r in reqs[:MAX_ITEMS]:
        items.append({"kind": "solicitud", "id": r["id"], "who": _clean(r.get("name")),
                      "line": f"Solicitud #{r['id']} de {_clean(r.get('name'))}, recibida {str(r.get('created', ''))[:10]}"})
    for j in overdue[:MAX_ITEMS]:
        items.append({"kind": "cobro", "id": j["id"], "who": _clean(j.get("client_name")), "job": j,
                      "line": f"Trabajo #{j['id']} «{_clean(j.get('title'), 80)}»: saldo {_usd(j['balance'])}, venció {j['due_date']}"})
    try:
        ops = core._growth.growth_opportunities()["opportunities"]
    except Exception as exc:
        ops = []
        notes.append(f"Cotizaciones viejas: no pude leerlas ({type(exc).__name__}).")
    by_id = {j["id"]: j for j in clients["jobs"]}
    quotes = [o for o in ops if o.get("kind") == "quote"]
    notes += _more(quotes, "/seguimientos")
    for op in quotes[:MAX_ITEMS]:
        j = by_id.get(op["id"])
        if not j:
            continue
        items.append({"kind": "cotizacion", "id": j["id"], "who": _clean(j.get("client_name")), "job": j,
                      "line": f"Cotización #{j['id']} «{_clean(j.get('title'), 80)}»: {op.get('reason', 'sin respuesta')}"})
    return items, notes


def draft_for(item):
    """Plantilla fija. Precio solo si ya está guardado en el trabajo. No se guarda ni se envía."""
    biz = EXPECTED_BUSINESS
    who = item["who"]
    if item["kind"] == "solicitud":
        body = (f"Hola {who}, le saluda {biz}. Recibimos su consulta. "
                "¿Qué día y hora le conviene para coordinar una evaluación?")
    elif item["kind"] == "cobro":
        j = item["job"]
        body = (f"Hola {who}, le saluda {biz}. El trabajo «{_clean(j.get('title'), 80)}» tiene un saldo registrado de "
                f"{_usd(j['balance'])} con vencimiento {j['due_date']}. ¿Nos confirma la fecha prevista de pago? Gracias.")
    else:
        j = item["job"]
        price = f" por {_usd(j['price'])}" if float(j.get("price") or 0) > 0 else ""
        body = (f"Hola {who}, le saluda {biz}. Damos seguimiento a la cotización «{_clean(j.get('title'), 80)}»{price}. "
                "¿Tiene alguna pregunta o desea coordinar?")
    return body


def section_followups(items, notes):
    lines = ["2) SOLICITUDES Y SEGUIMIENTOS VENCIDOS"]
    if not items:
        lines.append("ninguna")
    lines += ["• " + it["line"] for it in items]
    if not core._business_workflows.request_enabled():
        lines.append("Receptor de solicitudes públicas: apagado.")
    lines += notes
    drafts = ["3) BORRADORES DE RESPUESTA"]
    if not items:
        drafts.append("ninguno")
    for it in items:
        drafts.append(f"[{it['kind']} #{it['id']}] BORRADOR — no enviado\n{draft_for(it)}")
    if items:
        drafts.append("No se guardaron ni se enviaron. Para mandar uno, prepáralo y usa /enviar N.")
    return lines, drafts


# --- 4. Red social -------------------------------------------------------------------------------------------
def section_social():
    return ["4) BORRADOR DE RED — no publicado",
            "BORRADOR — no publicado",
            f"{EXPECTED_BUSINESS}: construcción y mantenimiento en Puerto Rico. "
            "¿Necesitas cotizar un mantenimiento? Escríbenos y coordinamos una evaluación.",
            "Sin fecha programada ni código. Publicar sigue pidiendo /publicarred + /confirmarred."]


# --- 5. Por cobrar y siguiente trabajo -------------------------------------------------------------------------
def section_receivables():
    with core._data_lock:
        d = core._cload()
    clients = {c["id"] for c in d["clients"]}
    due = [j for j in d["jobs"] if j.get("status") not in ("quote", "paid", "cancelled") and float(j.get("balance") or 0) > 0]
    total = sum((Decimal(str(j["balance"])) for j in due), Decimal(0))
    lines = ["5) POR COBRAR",
             f"{len(due)} trabajo(s) con saldo por cobrar: {_usd(total)} ya guardado."]
    open_jobs = sorted([j for j in d["jobs"] if j.get("status") not in ("paid", "cancelled")],
                       key=lambda j: (j.get("due_date") or "9999", j["id"]))
    if not open_jobs:
        lines.append("Siguiente: no hay trabajo abierto.")
        return lines
    j = open_jobs[0]
    missing = []
    if float(j.get("price") or 0) <= 0:
        missing.append("precio")
    if not j.get("due_date"):
        missing.append("fecha")
    if j.get("client_id") not in clients:
        missing.append("cliente")
    if j.get("status") == "quote":
        missing.append("aprobación del cliente")
    what = ("falta " + ", ".join(missing)) if missing else f"datos completos; queda cobrar {_usd(j.get('balance') or 0)}"
    lines.append(f"Siguiente: trabajo #{j['id']} «{_clean(j.get('title'), 80)}» — {what}.")
    return lines


def marker_line():
    got, _count = collected_this_week()
    goal = weekly_goal()
    return f"Cobrado esta semana: {_usd(got)} de {_usd(goal) if goal is not None else 'sin meta'}"


EXTRA_SECTIONS = []     # cortes posteriores añaden funciones de solo lectura -> lista de líneas


def _section(fn, *args):
    """Una sección dañada no tumba el resto del brief. Una instancia vieja o una escritura sí se detienen."""
    try:
        return fn(*args)
    except (core.StaleInstance, core.ReadOnlyViolation):
        raise
    except Exception as exc:
        core.logger.warning("brief section %s failed: %s", getattr(fn, "__name__", "?"), type(exc).__name__)
        return [f"Sección no disponible ({type(exc).__name__}). No estimo ni relleno esa parte."]


def _cash_block():
    return section_cash(core._business_workflows.cash_flow_report())


def _follow_blocks():
    items, notes = followup_items()
    return section_followups(items, notes)


def commercial_brief():
    """Texto del brief. Corre con el bloqueo de escritura del almacenamiento: no puede guardar nada."""
    stop = business_check()
    if stop:
        return stop
    token = core._WRITE_BLOCK.set("brief")
    try:
        cash = _section(_cash_block)
        follow = _section(_follow_blocks)
        if not (isinstance(follow, tuple) and len(follow) == 2):
            follow = (["2) SOLICITUDES Y SEGUIMIENTOS VENCIDOS"] + follow,
                      ["3) BORRADORES DE RESPUESTA", "Sin borradores: la sección 2 no se pudo leer."])
        if cash and not cash[0].startswith("1)"):
            cash = ["1) CAJA"] + cash
        receivables = _section(section_receivables)
        if receivables and not receivables[0].startswith("5)"):
            receivables = ["5) POR COBRAR"] + receivables
        blocks = [cash, follow[0], follow[1], section_social(), receivables]
        for extra in EXTRA_SECTIONS:
            blocks.append(_section(extra))
        marker = marker_line()
    finally:
        core._WRITE_BLOCK.reset(token)
    head = f"📋 Brief comercial {EXPECTED_BUSINESS} — {core._today().isoformat()}"
    tail = "No envié, no publiqué, no aprobé ni cobré nada."
    return "\n\n".join([head] + ["\n".join(b) for b in blocks] + [marker, tail])


REPLIES["/brief"] = lambda arg: commercial_brief()


def _fail(exc, what):
    return f"⚠️ No pude {what} ({type(exc).__name__}). No envié ni publiqué nada."


async def reply_for(cmd, arg=""):
    """Texto para un comando local registrado. StaleInstance sube para que la cola reintente."""
    fn = REPLIES[cmd]
    try:
        return await asyncio.to_thread(fn, arg)
    except core.StaleInstance:
        raise
    except Exception as exc:
        core.logger.warning("local command %s failed: %s", cmd, type(exc).__name__)
        return _fail(exc, "completar " + cmd)


async def command(chat_id, cmd, arg):
    await core._tg_safe_send(chat_id, await reply_for(cmd, arg))


def install(j):
    global core
    core = j
    ext = j._extensions
    old_command = ext.command

    async def routed(chat_id, cmd, arg):
        if cmd in REPLIES:
            return await command(chat_id, cmd, arg)
        return await old_command(chat_id, cmd, arg)

    ext.command = routed
    ext.COMMANDS.update(COMMANDS)

    async def dispatch(chat_id, cmd, arg):
        await j._extensions.command(chat_id, cmd, arg)

    old_route = j._tg_route

    async def tg_route(msg, background):
        chat_id, text, doc, photos, voice = j._tg_fields(msg)
        cmd = None if (doc or photos or voice) else phrase_command(text)
        if cmd:
            if not j.is_owner_private(msg):
                background.add_task(j._tg_safe_send, chat_id, DENY_TEXT)
            else:
                background.add_task(dispatch, chat_id, cmd, "")
            return {"ok": True}
        return await old_route(msg, background)

    j._tg_route = tg_route

    # Voz y /dictado llegan a _handle_tg solo desde el chat privado del dueño (la voz exige is_owner_private).
    old_handle = j._handle_tg

    async def handle_tg(chat_id, text, *, read_only=False):
        cmd = phrase_command(text)
        if not cmd or str(chat_id) != str(j.TG_OWNER):
            return await old_handle(chat_id, text, read_only=read_only)
        if read_only and cmd in WRITING_PHRASE_COMMANDS:
            reply = f"Por voz no guardo nada. Escribe {cmd} en tu chat privado."
        else:
            try:
                reply = await reply_for(cmd, "")
            except j.StaleInstance as exc:
                reply = j._fail_text(exc)
                try:
                    await j._tg_send(chat_id, reply)
                except Exception:
                    pass
                return None
        try:
            await j._tg_send(chat_id, reply)
        except Exception:
            return None
        return reply

    j._handle_tg = handle_tg

    try:
        import jarvis_chat_voice as cv
        old_query = cv.is_voice_query
        cv.is_voice_query = lambda text: phrase_command(text) is not None or old_query(text)
    except Exception as exc:  # la voz es opcional; el comando escrito sigue
        j.logger.warning("brief voice phrase off: %s", type(exc).__name__)

    old_diag = j.diagnostics_text

    async def diagnostics_text():
        text = await old_diag()
        return (text + f"\n• Brief 4.2.1: {getattr(j, 'BRIEF_STATUS', 'cargando')} · "
                f"Aprendizaje 4.2.2: {getattr(j, 'LEARN_STATUS', 'no cargado')} · negocio "
                + ("ISLAFIX PRO LLC" if business_check() is None else "NO coincide (revisa BUSINESS_NAME)"))

    j.diagnostics_text = diagnostics_text
    j.commercial_brief = commercial_brief
    j.HELP_TEXT += "\n4.2.1: /brief — caja, solicitudes, borradores (no enviados), por cobrar y marcador semanal"
