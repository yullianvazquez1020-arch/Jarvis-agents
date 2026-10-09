# jarvis_learn.py — Jarvis 4.2.2: aprendizaje acotado. Aditivo sobre 4.2.0/4.2.1; no reescribe el orquestador.
# No hay conciencia, voluntad, meta de poder ni permiso para actuar sin el gate. Una regla determinista:
# leer trabajos YA cobrados (ingreso registrado y vinculado al pago) y dejar UNA propuesta sin ejecutar.
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
COMMANDS = {"/aprender", "/meta"}
PHRASES = {"aprender": "/aprender", "que repetir": "/aprender"}
NO_FACTS = "No hay trabajo cobrado. No aprendo de proyecciones ni de metas."
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
            facts.append({"job_id": job["id"], "amount": total.quantize(Decimal(".01")), "date": last.isoformat(),
                          "trade": _text_field(job, "trade", "oficio"),
                          "zone": _text_field(job, "zone", "zona", "location")})
    facts.sort(key=lambda f: (f["date"], f["job_id"]))
    return facts[-MAX_FACTS:]


def fact_line(f):
    parts = [f"trabajo {f['job_id']}: {brief._usd(f['amount'])} ya cobrado"]
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
    parts.append("importes ya cobrados " + ", ".join(brief._usd(f["amount"]) for f in facts))
    parts.append("trabajos " + ", ".join("#" + str(f["job_id"]) for f in facts))
    return "; ".join(parts) + "."


def build(facts):
    """-> (texto de salida, propuesta revisada por consult_before_propose o None si fue rechazada)."""
    line = pattern_line(facts)
    checked = v.consult_before_propose(core, "Repetir solo lo ya cobrado: " + line)
    if not checked["ok"]:
        return checked["text"], None
    text = "\n".join(["HECHOS"] + ["- " + fact_line(f) for f in facts] + [
        "PROPUESTA — no ejecutada",
        "Repetir solo lo ya cobrado: " + line,
        "No visito, no cobro, no publico y no opero."])
    return text, checked


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
    facts = paid_facts()
    if not facts:
        return NO_FACTS
    with core._data_lock:
        left, _used = v._budget_left(v._load(core), core._today().isoformat())
    if left <= 0:
        return EXHAUSTED
    text, checked = build(facts)
    if checked is None:
        return text                       # rechazada: no se guarda ninguna versión editada
    problem = _save_proposal(checked, facts, once_per_day=False)
    return problem or text


def learn_daily():
    """Desde scheduler_cycle, ya dentro del claim jarvis:v420:cycle:{day}. No se envía ni es urgente.
    Un fallo aquí no tumba el resto del ciclo (aviso de flujo); una instancia vieja sí se detiene."""
    try:
        facts = paid_facts()
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
    facts = paid_facts()
    if not facts:
        return ["6) APRENDIZAJE", NO_FACTS]
    text, _checked = build(facts)
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


def _meta_reply(arg):
    try:
        return goal_command(arg)
    except ValueError as exc:
        return "⚠️ " + str(exc)


def install(j):
    global core
    core = j
    j._extensions.COMMANDS.update(COMMANDS)
    brief.REPLIES["/aprender"] = lambda arg: learn_command()
    brief.REPLIES["/meta"] = _meta_reply
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
    j.HELP_TEXT += ("\n4.2.2: /aprender — propuesta (no ejecutada) con trabajos ya cobrados · "
                    "/meta [N|borrar] — meta semanal para comparar, no es ingreso")
