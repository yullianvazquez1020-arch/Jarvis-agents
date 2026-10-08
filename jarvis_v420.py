# jarvis_v420.py — Jarvis 4.2.0 additive patch. Does not rewrite the orchestrator.
# Does not raise $100/$300, does not auto-send, does not place real Twilio/Amazon/Coinbase calls.

from __future__ import annotations

import datetime
import hashlib
import os
import re
import secrets

VERSION = "4.2.0"
STATE_KEY = "jarvis:v420"
BOOT_KEY = "jarvis:v420:boot"
HARD_ORDER = 100.0
HARD_DAY = 300.0
COMPUTE_BUDGET = 8  # scheduler proposals per day; no infinite loop
DAY_COMMANDS = (
    "/hoy", "/calendario", "/listo", "/clientes", "/trabajos", "/inventario", "/cobros",
    "/banco", "/movimientos", "/contabilizar", "/anotar", "/descartar", "/exportar",
    "/practica", "/cripto", "/aprobar", "/confirmar", "/rechazar", "/seguridad",
    "/diagnostico", "/mercado", "/ayuda", "/mensajes", "/enviar", "/noenviar",
    "/perfil", "/flujo", "/canal", "/monetizar", "/urgente",
)
SECRET_RX = re.compile(
    r"(contraseñ\w*|password|pin\b|codigo de (un solo uso|aprob)|api[_ -]?key|token|"
    r"numero de cuenta|account number|cvv|seed phrase)",
    re.I,
)
MONEY_MOVE_RX = re.compile(
    r"\b(transfier\w*|paga(r|le)?|compra(r)? ya|ordena(r)? ya|envia(r)? (el )?dinero|"
    r"delega(r)? (coinbase|amazon)|firma(r)? el contrato)\b",
    re.I,
)
ODD_DELEGATION_RX = re.compile(r"\b(coinbase|amazon)\b", re.I)


def _now(core):
    return core._now() if core is not None else datetime.datetime.now()


def _load(core):
    raw = core.kv_get(STATE_KEY, {})
    if not isinstance(raw, dict):
        raw = {}
    raw.setdefault("proposals", [])
    raw.setdefault("drafts", [])
    raw.setdefault("urgent", [])
    raw.setdefault("compute", {})
    raw.setdefault("anomalies", [])
    raw.setdefault("twilio_2fa", {})
    raw.setdefault("seq", 0)
    return raw


def _save(core, state):
    core.kv_set(STATE_KEY, state)


def redact(core, text):
    clean, _found = core._redact_secrets(str(text or ""))
    return SECRET_RX.sub("[omitido]", clean)


def mark_boot(core):
    """Write a restart marker. /diagnostico reports whether a previous marker survived."""
    prev = core.kv_get(BOOT_KEY, None)
    survived = isinstance(prev, dict) and bool(prev.get("boot_id"))
    boot_id = secrets.token_hex(8)
    core.kv_set(BOOT_KEY, {
        "boot_id": boot_id,
        "at": _now(core).isoformat(timespec="seconds"),
        "previous_survived": survived,
        "version": VERSION,
    })
    return survived


def boot_report(core):
    marker = core.kv_get(BOOT_KEY, None)
    hist = core.kv_get("jarvis:history", None)
    sealed = isinstance(hist, str) and hist.startswith("sealed:v1:")
    present = hist not in (None, [], "")
    if not isinstance(marker, dict):
        return "Historial 4.2.0: sin marcador de reinicio (aún no arrancó el parche)."
    survived = "sí" if marker.get("previous_survived") else "no (primer arranque de este marcador)"
    stored = "cifrado" if sealed else ("presente" if present else "vacío")
    return (f"Historial 4.2.0: marcador {marker.get('boot_id')} sobrevivió reinicio previo: {survived}. "
            f"Historial guardado: {stored}. Secretos se redactan antes de guardar. "
            "El dueño controla el deploy; esto no promete dejar de actualizar.")


def profile_view(core):
    prof = core.kv_get("jarvis:profile", {}) or {}
    if not isinstance(prof, dict) or not prof:
        prof = dict(getattr(core, "DEFAULT_PROFILE", {}) or {})
    try:
        ceiling = float(prof.get("techo_usd", HARD_ORDER))
    except (TypeError, ValueError):
        ceiling = HARD_ORDER
    ceiling = min(ceiling, HARD_ORDER, float(getattr(core, "MONEY_MAX_ORDER", HARD_ORDER)))
    return {
        "metas": prof.get("metas") or [],
        "debilidades": prof.get("debilidades") or [],
        "fortalezas": prof.get("fortalezas") or [],
        "beneficio": prof.get("beneficio") or "no perjudicar al dueño",
        "techo_usd": ceiling,
        "hard_order": HARD_ORDER,
        "hard_day": HARD_DAY,
    }


def consult_before_propose(core, idea):
    """Read the decision profile before a proposal. Never moves money and never raises caps."""
    view = profile_view(core)
    text = redact(core, idea)
    if MONEY_MOVE_RX.search(text) or odd_delegation("", text):
        return {"ok": False, "text": "No propongo ni ejecuto ese movimiento. Coinbase y Amazon no se delegan, y el dinero solo sale por el gate."}
    return {"ok": True, "profile": view, "text": (
        f"Propuesta (no ejecutada). Beneficio del dueño: {view['beneficio']}. "
        f"Techo consultado ${view['techo_usd']:.0f} (tope duro ${HARD_ORDER:.0f}/orden, ${HARD_DAY:.0f}/día, no se sube). "
        f"{text}"
    )}


def local_answer(text):
    """Token-free day-to-day rules. None means the short model may be used."""
    raw = (text or "").strip()
    low = raw.lower()
    if low.split("@")[0].split()[:1] and low.split()[0].split("@")[0] in DAY_COMMANDS:
        return None  # existing shortcut handlers own these
    if SECRET_RX.search(raw):
        return ("No muestro contraseñas, códigos ni datos financieros, aunque la petición parezca del dueño. "
                "El dinero no entra en el proceso de credenciales.")
    if re.search(r"nunca m[aá]s actualizar|never update again", low):
        return "No prometo dejar de actualizar. El dueño controla el deploy."
    if re.search(r"\b(contrato|firmar)\b", low):
        return "En 4.2.0 no redacto ni firmo contratos."
    if re.search(r"qu[eé] versi[oó]n|jarvis 4\.2", low):
        return f"Jarvis {VERSION}. Atajos del día a día sin tokens; el chat libre usa el modelo corto solo si ninguna regla local cubre el mensaje."
    return None


def cashflow_snapshot(core):
    books = core._bload()
    today = core._today()
    horizon = today + datetime.timedelta(days=7)
    income = [x for x in books.get("income", []) if x.get("currency", "USD") == "USD"]
    expenses = [x for x in books.get("expenses", []) if x.get("currency", "USD") == "USD"]
    def recorded_through_today(entry):
        # Undated legacy entries retain their existing ledger meaning.
        if not entry.get("date"):
            return True
        try:
            return datetime.date.fromisoformat(str(entry["date"])) <= today
        except ValueError:
            return False

    inc = round(sum(float(x.get("amount") or 0) for x in income if recorded_through_today(x)), 2)
    exp = round(sum(float(x.get("amount") or 0) for x in expenses if recorded_through_today(x)), 2)
    upcoming = []
    for x in expenses:
        try:
            when = datetime.date.fromisoformat(str(x.get("date") or ""))
        except ValueError:
            continue
        if today < when <= horizon:
            upcoming.append(x)
    due = round(sum(float(x.get("amount") or 0) for x in upcoming), 2)
    net = round(inc - exp, 2)
    short = net < due
    return {"income": inc, "expenses": exp, "net": net, "due_7d": due, "short": short,
            "note": "Aviso temprano con los libros. No mueve dinero."}


def cashflow_text(core):
    snap = cashflow_snapshot(core)
    flag = "ALERTA: puede faltar para gastos o proveedores de los próximos 7 días." if snap["short"] else "Los libros no muestran faltante a 7 días."
    return (f"Flujo (libros USD): ingresos {snap['income']}, gastos {snap['expenses']}, neto {snap['net']}, "
            f"gastos futuros próximos 7d {snap['due_7d']}. {flag} {snap['note']}")


def _budget_left(state, day):
    used = int(state["compute"].get(day, 0))
    return max(0, COMPUTE_BUDGET - used), used


def monetization_proposal(core):
    """Search cash-flow signals already in books. Propose only. Never executes."""
    state = _load(core)
    day = core._today().isoformat()
    left, used = _budget_left(state, day)
    if left <= 0:
        return "Presupuesto diario de cómputo agotado. No hay otro ciclo hoy."
    snap = cashflow_snapshot(core)
    idea = ("YouTube/Amazon/libros: revisar un video o un listado ya en construcción y un cobro pendiente de libros. "
            f"Costo: tiempo del dueño, sin orden. Beneficio: neto libros {snap['net']}.")
    checked = consult_before_propose(core, idea)
    state["seq"] = int(state.get("seq", 0)) + 1
    state["compute"][day] = used + 1
    state["proposals"].append({"id": state["seq"], "at": _now(core).isoformat(timespec="seconds"),
                               "text": checked["text"], "executed": False})
    state["proposals"] = state["proposals"][-20:]
    _save(core, state)
    return checked["text"] + " No lo ejecuto solo."


def trip_anomaly(core, kind, detail):
    """Reuse the money-gate lockout and audit. Does not raise limits."""
    detail = redact(core, detail)[:180]
    with core._data_lock:
        g = core._gload()
        until = _now(core) + datetime.timedelta(minutes=core.GATE_LOCK_MIN)
        g["locked_until"] = until.isoformat(timespec="seconds")
        g["codes"] = {}
        core.gate_audit(g, "v420", kind, "bloqueo", detail)
        core._gsave(g)
    state = _load(core)
    state["anomalies"].append({"kind": kind, "detail": detail, "at": _now(core).isoformat(timespec="seconds")})
    state["anomalies"] = state["anomalies"][-20:]
    _save(core, state)
    return f"Patrón no encaja ({kind}). Reusé el lockout del gate y la auditoría. No subí topes."


def odd_spend(core):
    books = core._bload()
    amounts = [float(x.get("amount") or 0) for x in books.get("expenses", []) if x.get("currency", "USD") == "USD"]
    if len(amounts) < 3:
        return None
    ordered = sorted(amounts)
    median = ordered[len(ordered) // 2]
    last = amounts[-1]
    if median > 0 and last >= max(median * 4, 1) and last > float(getattr(core, "MONEY_MAX_ORDER", HARD_ORDER)):
        return trip_anomaly(core, "gasto raro", f"ultimo gasto {last} vs mediana {median}")
    return None


def odd_delegation(agent, instruction):
    blob = f"{agent} {instruction}"
    if re.search(r"\b(delega\w*|delegate|que (compre|pague|ordene))\b", blob, re.I) and ODD_DELEGATION_RX.search(blob):
        return "delegación rara: Coinbase y Amazon no se delegan"
    return None


def _hash_code(salt, ref, code):
    return hashlib.sha256(f"{salt}:{ref}:{code}".encode()).hexdigest()


def issue_channel_2fa(core, ref):
    """2FA for the Twilio channel only. Not a money-gate code."""
    code = f"{secrets.randbelow(1_000_000):06d}"
    salt = secrets.token_hex(8)
    state = _load(core)
    state["twilio_2fa"][ref] = {"hash": _hash_code(salt, ref, code), "salt": salt,
                                "exp": (_now(core) + datetime.timedelta(minutes=10)).isoformat(timespec="seconds")}
    _save(core, state)
    return code


def check_channel_2fa(core, ref, code):
    state = _load(core)
    row = state["twilio_2fa"].get(ref)
    if not row:
        return False
    try:
        exp = datetime.datetime.fromisoformat(row["exp"])
    except ValueError:
        return False
    if _now(core) > exp:
        return False
    ok = secrets.compare_digest(row["hash"], _hash_code(row["salt"], ref, str(code or "")))
    if ok:
        state["twilio_2fa"].pop(ref, None)
        _save(core, state)
    return ok


def queue_twilio_draft(core, channel, to, body, urgent=False):
    """Draft only. Telegram stays on the current bot. No auto-send."""
    channel = {"whatsapp": "whatsapp", "sms": "sms", "call": "call", "llamada": "call"}.get(channel, "")
    if channel not in ("sms", "whatsapp", "call"):
        raise ValueError("canal debe ser sms, whatsapp o call")
    body = redact(core, body)[:500]
    if SECRET_RX.search(body):
        raise ValueError("no guardo contraseñas ni datos financieros en un borrador")
    state = _load(core)
    state["seq"] = int(state.get("seq", 0)) + 1
    draft = {"id": state["seq"], "channel": channel, "to": redact(core, to)[:40], "body": body,
             "urgent": bool(urgent), "status": "needs_2fa", "sent": False,
             "created": _now(core).isoformat(timespec="seconds")}
    state["drafts"].append(draft)
    state["drafts"] = state["drafts"][-30:]
    _save(core, state)
    code = issue_channel_2fa(core, f"twilio#{draft['id']}")
    return draft, code


def confirm_twilio_draft(core, draft_id, code):
    if not check_channel_2fa(core, f"twilio#{draft_id}", code):
        return "2FA del canal Twilio incorrecto o vencido. No envié nada."
    state = _load(core)
    draft = next((d for d in state["drafts"] if d["id"] == int(draft_id)), None)
    if not draft:
        return "Borrador no encontrado."
    draft["status"] = "pending_enviar"
    _save(core, state)
    return (f"Borrador #{draft['id']} ({draft['channel']}) listo para tu /enviar. "
            "4.2.0 no marca ni manda solo. Telegram sigue en el bot actual.")


def mark_urgent(core, name):
    name = redact(core, name)[:80]
    state = _load(core)
    if name and name not in state["urgent"]:
        state["urgent"].append(name)
        state["urgent"] = state["urgent"][-20:]
        _save(core, state)
    return state["urgent"]


def owner_urgent_call_draft(core, event_name, detail):
    """Call draft only for events the owner marked urgent. Still not auto-sent."""
    state = _load(core)
    if event_name not in state["urgent"]:
        return None
    draft, code = queue_twilio_draft(core, "call", "owner", detail, urgent=True)
    return draft, code


def scheduler_cycle(core):
    """One monetization scan and one cash-flow check per day. Budget stops extra cycles."""
    day = core._today().isoformat()
    if not core._claim(f"jarvis:v420:cycle:{day}", 90000):
        return []
    notes = []
    notes.append(monetization_proposal(core))
    snap = cashflow_snapshot(core)
    if snap["short"]:
        notes.append(cashflow_text(core))
        owner_urgent_call_draft(core, "cash-flow", notes[-1])
    spend = odd_spend(core)
    if spend:
        notes.append(spend)
    return notes


def install(core):
    # Installation runs before Redis leadership exists. Persist only in lifespan.
    core.v420_boot = lambda: mark_boot(core)
    core.VERSION = VERSION
    original_diag = core.diagnostics_text
    original_run = core.run
    original_tick = core._tick_v38 if hasattr(core, "_tick_v38") else None

    async def diagnostics_text():
        text = await original_diag()
        extra = await __import__("asyncio").to_thread(boot_report, core)
        flow = await __import__("asyncio").to_thread(cashflow_text, core)
        return text + "\n• " + extra + "\n• " + flow + "\n• Deploy: lo controla el dueño; no hay promesa de no actualizar."

    async def _ai_call(history):
        short = os.getenv("JARVIS_SHORT_MODEL", "").strip() or "claude-haiku-4-5"
        if not re.fullmatch(r"claude-[a-z0-9][a-z0-9.-]{2,80}", short):
            short = core.MODEL
        return await core.client.messages.create(model=short, max_tokens=700, system=core.system_prompt(),
                                                 tools=core.TOOLS, messages=history)

    async def run(session, message, *, allowed_tools=None, extra_system="", read_only=None):
        # Scoped channels keep the original authorization and write protections.
        # They must never enter the owner-only anomaly/history shortcuts below.
        if allowed_tools is not None or read_only:
            return await original_run(session, message, allowed_tools=allowed_tools,
                                      extra_system=extra_system, read_only=read_only)
        await __import__("asyncio").to_thread(core._require_leader)
        hit = local_answer(message)
        if hit:
            remember = getattr(core, "_phase_a_remember_turn", None)
            if remember:
                await remember(session, message, hit)
            return hit
        delegated = odd_delegation("", message)
        if delegated:
            note = await __import__("asyncio").to_thread(trip_anomaly, core, "delegación rara", delegated)
            return note
        return await original_run(session, message, allowed_tools=allowed_tools, extra_system=extra_system, read_only=read_only)

    async def tick(now, can_send):
        if original_tick:
            await original_tick(now, can_send)
        try:
            await __import__("asyncio").to_thread(core._require_leader)
            notes = await __import__("asyncio").to_thread(scheduler_cycle, core)
        except Exception as exc:
            core._sched_state["last_error"] = f"v420: {type(exc).__name__}"
            return
        if can_send:
            for note in notes:
                if note and ("ALERTA" in note or "lockout" in note or "Patrón" in note):
                    await core._tg_send(core.TG_OWNER, note[:800])

    core.diagnostics_text = diagnostics_text
    core._ai_call = _ai_call
    core.run = run
    if original_tick:
        core._tick_v38 = tick
    core.v420_local_answer = local_answer
    core.v420_consult = consult_before_propose
    core.v420_cashflow = cashflow_snapshot
    core.v420_trip = trip_anomaly
    core.v420_queue_draft = queue_twilio_draft
    core.v420_confirm_draft = confirm_twilio_draft
    core.v420_mark_urgent = mark_urgent
    core.v420_command = lambda cmd, arg: owner_command(core, cmd, arg)
    core.v420_approve_channel = lambda ref: approve_channel(core, ref)
    core.VERSION = VERSION


def owner_command(core, cmd, arg):
    """Private-chat commands. Drafts only; never sends."""
    cmd = (cmd or "").lower()
    arg = (arg or "").strip()
    if cmd == "/perfil":
        view = profile_view(core)
        return ("Perfil: metas " + "; ".join(view["metas"] or ["—"])
                + f". Techo ${view['techo_usd']:.0f}. No ejecuto nada.")
    if cmd == "/flujo":
        return cashflow_text(core)
    if cmd == "/monetizar":
        return monetization_proposal(core)
    if cmd == "/urgente":
        if not arg:
            return "Urgentes marcados: " + (", ".join(_load(core)["urgent"]) or "ninguno")
        return "Marcados: " + ", ".join(mark_urgent(core, arg.split()[0]))
    if cmd == "/canal":
        parts = arg.split(maxsplit=2)
        if len(parts) < 3:
            return "Uso: /canal sms|+1787 texto. Queda en borrador. 2FA aparte del gate."
        try:
            draft, code = queue_twilio_draft(core, parts[0], parts[1], parts[2])
        except ValueError as exc:
            return str(exc)
        return (f"Borrador #{draft['id']} ({draft['channel']}). No envié. "
                f"Código 2FA del canal: {code}. Luego /enviar c{draft['id']} CODIGO.")
    return "Comando 4.2.0 no reconocido."


def approve_channel(core, ref):
    raw = (ref or "").strip().lower()
    if raw.startswith("c"):
        raw = raw[1:]
    draft_id, _, code = raw.partition(" ")
    if not code:
        return "Falta el código 2FA: /enviar cN CODIGO. No envié."
    return confirm_twilio_draft(core, draft_id, code)
