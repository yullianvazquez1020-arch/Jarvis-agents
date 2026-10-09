# jarvis_learn.py — Jarvis 4.2.2: aprendizaje acotado. Aditivo sobre 4.2.0/4.2.1; no reescribe el orquestador.
# No hay conciencia, voluntad, meta de poder ni permiso para actuar sin el gate. Una regla determinista:
# leer trabajos con FINALIZACIÓN CONFIRMADA por el dueño (/terminado N) y PAGADOS COMPLETOS (ingreso
# registrado y vinculado) y dejar UNA propuesta sin ejecutar. status="paid" no basta: main.py lo pone solo
# cuando el saldo llega a cero, y eso no demuestra que el trabajo terminó. Un pago recibido sin esa
# confirmación (adelanto, abono o pago completo) se muestra aparte, no es ganancia y nunca justifica repetir.
# Sin tokens. No escribe libros, no crea clientes, trabajos ni ingresos, no envía, no publica y no llama a
# Coinbase ni a Amazon. No sube $100/$300 ni toca techo_usd. Solo el chat privado del dueño.

from __future__ import annotations

import datetime as dt
import math
import re
from decimal import Decimal

import jarvis_brief as brief
import jarvis_v420 as v

VERSION = "4.2.2"
KIND = "aprender"
COMMANDS = {"/aprender", "/meta", "/terminado"}
PHRASES = {"aprender": "/aprender", "que repetir": "/aprender"}
NO_FACTS = ("No hay trabajo con finalización confirmada y pagado completo. No aprendo de pagos recibidos, "
            "proyecciones ni metas.")
COMPLETION_FIELD = "completion"          # {"confirmed": True, "at": ..., "by": "owner"}; solo lo escribe /terminado
NOT_PROFIT = "Cobrado no es ganancia: no descuenta costos, materiales ni gastos."
STATUS_ES = {"quote": "cotización", "confirmed": "confirmado", "in_progress": "en proceso",
             "delivered": "entregado", "invoiced": "facturado", "paid": "pagado", "cancelled": "cancelado"}
EXHAUSTED = "Presupuesto diario de cómputo agotado. No hay otro ciclo hoy."
GOAL_FIELD = brief.GOAL_FIELD            # meta_semanal_usd en jarvis:profile
GOAL_MAX = Decimal("100000000")
GOAL_RX = re.compile(r"\$?\s*(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?")
GOAL_WORDS_RX = re.compile(r"poderos|concien|conscien|millonari|millon|infinit|todo")
MAX_FACTS = 10

core = None


# --- hechos: solo trabajos con ingreso cobrado, registrado y vinculado ----------------------------------------
def _text_field(job, *names):
    for name in names:
        value = job.get(name)
        if isinstance(value, str) and value.strip():
            return re.sub(r"\s+", " ", value).strip()[:60]
    return ""


def paid_facts():
    """Trabajos cuyo pago guardó income_id y ese ingreso existe en los libros (USD, con fecha hasta hoy,
    vinculado al mismo trabajo). Nada inventado: si un campo falta, se omite."""
    today = core._today()
    with core._data_lock:
        jobs = core._cload()["jobs"]
        income = {x.get("id"): x for x in core._bload()["income"]}
    facts = []
    for job in jobs:
        total, last = Decimal(0), None
        for pay in job.get("payments") or []:
            inc = income.get(pay.get("income_id")) if isinstance(pay, dict) else None
            if not inc or inc.get("job_id") != job.get("id"):
                continue
            if str(inc.get("currency", "USD")).upper() != "USD":
                continue
            when = brief._date(inc.get("date"))
            if when is None or when > today:
                continue
            try:
                amount = Decimal(str(inc.get("amount")))
            except Exception:
                continue
            if not amount.is_finite() or amount <= 0:
                continue
            total += amount
            last = max(last, when) if last else when
        if total > 0:
            try:
                balance = float(job["balance"])
                price = float(job["price"])
                if not math.isfinite(balance) or not math.isfinite(price):
                    raise ValueError("non-finite job amount")
            except (KeyError, TypeError, ValueError):
                balance, price = -1.0, 0.0          # dato dañado: nunca cuenta como terminado
            facts.append({"job_id": job["id"], "amount": total.quantize(Decimal(".01")), "date": last.isoformat(),
                          "trade": _text_field(job, "trade", "oficio"),
                          "zone": _text_field(job, "zone", "zona", "location"),
                          "status": str(job.get("status") or ""), "balance": balance,
                          "confirmed": completion_confirmed(job),
                          "receipts_verified": price > 0 and total >= Decimal(str(price)),
                          # Base de una propuesta: finalización confirmada por el dueño + saldo cero + precio.
                          # status="paid" no cuenta: se asigna solo al llegar el saldo a cero.
                          "finished": completion_confirmed(job) and balance == 0 and price > 0
                                      and total >= Decimal(str(price))
                                      and job.get("status") not in ("cancelled", "quote")})
    facts.sort(key=lambda f: (f["date"], f["job_id"]))
    return facts


def completion_confirmed(job):
    row = job.get(COMPLETION_FIELD)
    return isinstance(row, dict) and row.get("confirmed") is True and row.get("by") == "owner"


def split_facts():
    """-> (terminados y pagados, pagos de trabajos abiertos). Solo los primeros sirven para proponer."""
    facts = paid_facts()
    done = [f for f in facts if f["finished"]][-MAX_FACTS:]
    open_rx = [f for f in facts if not f["finished"]][-MAX_FACTS:]
    return done, open_rx


def receipts_lines(open_rx):
    if not open_rx:
        return []
    lines = ["PAGOS RECIBIDOS SIN FINALIZACIÓN O COBRO COMPLETO VERIFICADOS — no son ganancia ni se repiten"]
    for f in open_rx:
        state = STATUS_ES.get(f["status"], f["status"] or "sin estado")
        if f["balance"] > 0:
            detail = f"saldo pendiente {brief._usd(f['balance'])}"
        elif f["balance"] < 0:
            detail = "datos del trabajo dañados"
        else:
            detail = "saldo $0.00"
            if not f["receipts_verified"]:
                detail += "; cobro completo no respaldado por ingresos vinculados"
        done = "finalización confirmada" if f["confirmed"] else f"finalización no confirmada (/terminado {f['job_id']})"
        lines.append(f"- trabajo {f['job_id']}: {brief._usd(f['amount'])} recibido; estado {state}, {detail}; {done}")
    return lines


def fact_line(f):
    parts = [f"trabajo {f['job_id']} (finalización confirmada y pagado): {brief._usd(f['amount'])} cobrado"]
    if f["trade"]:
        parts.append(f"oficio {f['trade']}")
    if f["zone"]:
        parts.append(f"zona {f['zone']}")
    return ", ".join(parts)


def pattern_line(facts):
    """Una línea con los mismos campos; un campo ausente no se rellena."""
    trades = sorted({f["trade"] for f in facts if f["trade"]})
    zones = sorted({f["zone"] for f in facts if f["zone"]})
    parts = []
    if trades:
        parts.append("oficio " + ", ".join(trades))
    if zones:
        parts.append("zona " + ", ".join(zones))
    parts.append("importes cobrados " + ", ".join(brief._usd(f["amount"]) for f in facts))
    parts.append("trabajos " + ", ".join("#" + str(f["job_id"]) for f in facts))
    return "; ".join(parts) + "."


def build(facts, open_rx=()):
    """facts: solo trabajos con finalización confirmada y pagados. -> (texto, propuesta revisada o None si fue rechazada)."""
    line = pattern_line(facts)
    checked = v.consult_before_propose(core, "Repetir solo trabajos con finalización confirmada y pagados: " + line)
    if not checked["ok"]:
        return checked["text"], None
    text = "\n".join(["HECHOS"] + ["- " + fact_line(f) for f in facts] + receipts_lines(open_rx) + [
        "PROPUESTA — no ejecutada",
        "Repetir solo trabajos con finalización confirmada y pagados: " + line,
        NOT_PROFIT,
        "No visito, no cobro, no publico y no opero."])
    return text, checked


def no_facts_text(open_rx):
    return "\n".join([NO_FACTS] + receipts_lines(open_rx) + ([NOT_PROFIT] if open_rx else []))


def _save_proposal(checked, facts, *, once_per_day):
    """Guarda en jarvis:v420 dentro del tope de 20, cuenta 1 contra COMPUTE_BUDGET. -> None u otro texto."""
    day = core._today().isoformat()
    with core._data_lock:
        state = v._load(core)
        if once_per_day and any(p.get("kind") == KIND and str(p.get("at", ""))[:10] == day
                                for p in state["proposals"]):
            return "ya hay una hoy"
        left, used = v._budget_left(state, day)
        if left <= 0:
            return EXHAUSTED
        state["seq"] = int(state.get("seq", 0)) + 1
        state["compute"][day] = used + 1
        state["proposals"].append({"id": state["seq"], "kind": KIND, "at": v._now(core).isoformat(timespec="seconds"),
                                   "text": checked["text"], "jobs": [f["job_id"] for f in facts],
                                   "executed": False})
        state["proposals"] = state["proposals"][-20:]
        v._save(core, state)
    return None


def learn_command():
    """/aprender: hechos -> una propuesta -> consult_before_propose -> guardar sin ejecutar."""
    facts, open_rx = split_facts()
    if not facts:
        return no_facts_text(open_rx)
    with core._data_lock:
        left, _used = v._budget_left(v._load(core), core._today().isoformat())
    if left <= 0:
        return EXHAUSTED
    text, checked = build(facts, open_rx)
    if checked is None:
        return text                       # rechazada: no se guarda ninguna versión editada
    problem = _save_proposal(checked, facts, once_per_day=False)
    return problem or text


def learn_daily():
    """Desde scheduler_cycle, ya dentro del claim jarvis:v420:cycle:{day}. No se envía ni es urgente.
    Un fallo aquí no tumba el resto del ciclo (aviso de flujo); una instancia vieja sí se detiene."""
    try:
        facts, _open = split_facts()
        if not facts:
            return None
        _text, checked = build(facts)
        if checked is not None:
            _save_proposal(checked, facts, once_per_day=True)
    except core.StaleInstance:
        raise
    except Exception as exc:
        core.logger.warning("learn daily skipped: %s", type(exc).__name__)
    return None


def brief_section():
    """Sexta sección del brief: la misma propuesta, calculada por build(); no guarda ni gasta presupuesto."""
    facts, open_rx = split_facts()
    if not facts:
        return ["6) APRENDIZAJE", no_facts_text(open_rx)]
    text, _checked = build(facts, open_rx)
    return ["6) APRENDIZAJE", text, "No guardada desde el brief. /aprender la guarda como propuesta."]


# --- /meta: un número para comparar, nunca un ingreso -----------------------------------------------------------
def parse_goal(arg):
    raw = str(arg or "").strip()
    norm = brief._norm(raw)
    if GOAL_WORDS_RX.search(norm):
        raise ValueError("La meta es solo un número positivo en dólares. No guardo palabras como meta.")
    m = GOAL_RX.fullmatch(raw)
    if not m:
        raise ValueError("Escribe solo un número positivo, por ejemplo /meta 2500 o /meta 2,500.50.")
    value = Decimal(m.group(1).replace(",", "") + ("." + m.group(2) if m.group(2) else ""))
    if value <= 0 or value > GOAL_MAX:
        raise ValueError("La meta debe ser mayor que 0 y razonable.")
    return value.quantize(Decimal(".01"))


def goal_command(arg):
    arg = str(arg or "").strip()
    if not arg:
        goal = brief.weekly_goal()
        return f"Meta semanal: {brief._usd(goal)}. Es solo para comparar; no es un ingreso." if goal is not None \
            else "Meta semanal: sin meta."
    if brief._norm(arg) in ("borrar", "quitar", "ninguna"):
        with core._data_lock:
            core._check_writable()
            prof = core.kv_get(brief.PROFILE_KEY, None)
            if not isinstance(prof, dict) or GOAL_FIELD not in prof:
                return "Meta semanal: sin meta. No cambié nada."
            prof = dict(prof)
            prof.pop(GOAL_FIELD, None)
            core.kv_set(brief.PROFILE_KEY, prof)
        return "Meta semanal borrada."
    value = parse_goal(arg)
    number = int(value) if value == value.to_integral_value() else float(value)
    if not math.isfinite(float(number)):
        raise ValueError("Meta inválida")
    with core._data_lock:
        core._check_writable()
        prof = core.kv_get(brief.PROFILE_KEY, None)
        prof = dict(prof) if isinstance(prof, dict) and prof else dict(getattr(core, "DEFAULT_PROFILE", {}) or {})
        prof[GOAL_FIELD] = number                 # solo este campo; techo_usd y topes no se tocan
        core.kv_set(brief.PROFILE_KEY, prof)
    return (f"Meta semanal guardada: {brief._usd(value)}. Es un número para comparar en /brief; "
            "no es un ingreso, no entra en los libros ni en el flujo.")


def complete_command(arg):
    """/terminado N [quitar]: confirmación explícita del dueño. No cambia estado, precio, saldo ni libros."""
    parts = str(arg or "").split()
    if not parts or len(parts) > 2 or not re.fullmatch(r"[0-9]{1,12}", parts[0]):
        return ("Uso: /terminado N — confirma que el trabajo N terminó. /terminado N quitar — la retira. "
                "No cambia estado, precio, saldo ni libros.")
    job_id = int(parts[0])
    undo = len(parts) > 1 and brief._norm(parts[1]) in ("quitar", "deshacer", "no")
    if len(parts) > 1 and not undo:
        return "No entendí. Usa /terminado N o /terminado N quitar."
    with core._data_lock:
        core._check_writable()
        d = core._cload()
        job = next((x for x in d["jobs"] if x["id"] == job_id), None)
        if not job:
            return f"Trabajo #{job_id} no encontrado. No cambié nada."
        if undo:
            if COMPLETION_FIELD not in job:
                return f"Trabajo #{job_id} no tenía finalización confirmada. No cambié nada."
            job.pop(COMPLETION_FIELD, None)
            core._csave(d)
            return f"Finalización del trabajo #{job_id} retirada. /aprender ya no lo usa."
        if job.get("status") in ("quote", "cancelled"):
            return (f"Trabajo #{job_id} está en {STATUS_ES.get(job['status'])}: no lo marco terminado. "
                    "No cambié nada.")
        if completion_confirmed(job):
            return f"Trabajo #{job_id} ya tenía finalización confirmada ({job[COMPLETION_FIELD].get('at', '')})."
        job[COMPLETION_FIELD] = {"confirmed": True, "by": "owner",
                                 "at": core._now().isoformat(timespec="minutes")}
        core._csave(d)
    balance = float(job.get("balance") or 0)
    tail = ("Saldo $0.00: /aprender solo lo usa si los ingresos vinculados respaldan el precio completo." if balance == 0 and float(job.get("price") or 0) > 0
            else f"Saldo pendiente {brief._usd(balance)}: /aprender no lo usa hasta que esté pagado completo.")
    return (f"Trabajo #{job_id} «{brief._clean(job.get('title'), 80)}»: finalización confirmada. "
            f"No cambié estado, precio, saldo ni libros. {tail}")


def _meta_reply(arg):
    try:
        return goal_command(arg)
    except ValueError as exc:
        return "⚠️ " + str(exc)


def install(j):
    global core
    core = j
    # Primero las respuestas, después el registro: un comando nunca queda listado sin su función.
    brief.REPLIES["/aprender"] = lambda arg: learn_command()
    brief.REPLIES["/meta"] = _meta_reply
    brief.REPLIES["/terminado"] = complete_command
    j._extensions.COMMANDS.update(COMMANDS)
    brief.PHRASES.update(PHRASES)
    brief.WRITING_PHRASE_COMMANDS.add("/aprender")
    brief.EXTRA_SECTIONS.append(brief_section)
    j.v422_learn_daily = learn_daily

    # La voz de solo lectura no pasa por local_answer: el rechazo fijo también se da aquí, sin tokens ni escrituras.
    old_handle = j._handle_tg

    async def handle_tg(chat_id, text, *, read_only=False):
        refusal = v.autonomy_refusal(text) if str(chat_id) == str(j.TG_OWNER) else None
        if not refusal:
            return await old_handle(chat_id, text, read_only=read_only)
        try:
            await j._tg_send(chat_id, refusal)
        except Exception:
            return None
        return refusal

    j._handle_tg = handle_tg
    j.HELP_TEXT += ("\n4.2.2: /aprender — propuesta (no ejecutada) con trabajos terminados (confirmados) y pagados · "
                    "/meta [N|borrar] — meta semanal para comparar, no es ingreso · "
                    "/terminado N [quitar] — confirmas que el trabajo terminó (requisito de /aprender)")
