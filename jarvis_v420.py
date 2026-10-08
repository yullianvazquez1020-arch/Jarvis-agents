# jarvis_v420.py — Jarvis 4.2.0 additive cut. Does not replace the orchestrator,
# does not raise the money gate, and does not send messages or move money.
"""Local day-to-day rules, sealed history status, decision profile, monetization
proposals, anomaly lockout, Twilio drafts, and early cash-flow alerts."""

from __future__ import annotations

import datetime
import hashlib
import os
import re
import secrets

CUT = "4.2.0"
STATE_KEY = "jarvis:v420"
BOOT_KEY = "jarvis:v420:boot"
DRAFTS_KEY = "jarvis:v420:drafts"
PROFILE_KEY = "jarvis:profile"
HISTORY_KEY = "jarvis:history"
NEVER_DELEGATE = {"coinbase", "amazon"}
HARD_ORDER = 100.0
HARD_DAY = 300.0
COMPUTE_DEFAULT = 6

DEFAULT_PROFILE = {
    "metas": ["cash flow del canal y de la tienda", "no perder dinero"],
    "debilidades": ["gastos impulsivos"],
    "fortalezas": ["construye Jarvis y cierra ventas"],
    "techo_usd": HARD_ORDER,
    "beneficio": "proponer solo lo que deja al dueño mejor de lo que está",
    "urgente": {"cash-flow": False, "camara": False, "emergencia": False},
}

LEAK_RX = re.compile(
    r"\b(contrase[nñ]a|password|api[_ ]?key|token secreto|c[oó]digo de (un solo uso|confirmaci[oó]n)|"
    r"seed phrase|clave privada|n[uú]mero de tarjeta|saldo completo|dump financiero)\b",
    re.I,
)
SECRET_RX = re.compile(
    r"(?i)(sk-[a-z0-9]{8,}|xox[baprs]-[a-z0-9-]{8,}|AKIA[0-9A-Z]{16}|"
    r"\b\d{6}\b|(?:bearer|token|password|clave)\s*[:=]\s*\S+)"
)


def env_int(name, default, lo, hi):
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        n = int(raw)
    except ValueError:
        return default
    return min(hi, max(lo, n))


def compute_budget():
    return env_int("JARVIS_COMPUTE_BUDGET", COMPUTE_DEFAULT, 1, 24)


def short_model():
    return os.getenv("JARVIS_SHORT_MODEL", "").strip()


def twilio_configured():
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    own = os.getenv("TWILIO_FROM", "").strip()
    return bool(sid and token and own and token.lower() not in {"", "change-me", "test"})


def redact(text, core=None):
    raw = str(text or "")
    if core is not None and hasattr(core, "_redact_secrets"):
        raw = core._redact_secrets(raw)[0]
    return SECRET_RX.sub("[redactado]", raw)[:2000]


def _load(core):
    d = core.kv_get(STATE_KEY, {})
    if not isinstance(d, dict):
        d = {}
    d.setdefault("compute", {})
    d.setdefault("proposals", [])
    d.setdefault("alerts", [])
    d.setdefault("channel_2fa", {})
    return d


def _save(core, d):
    core.kv_set(STATE_KEY, d)


def profile(core):
    p = core.kv_get(PROFILE_KEY, DEFAULT_PROFILE)
    if not isinstance(p, dict):
        p = dict(DEFAULT_PROFILE)
    out = dict(DEFAULT_PROFILE)
    out.update(p)
    try:
        cap = float(out.get("techo_usd", HARD_ORDER))
    except (TypeError, ValueError):
        cap = HARD_ORDER
    out["techo_usd"] = min(HARD_ORDER, max(0.0, cap))
    urgent = out.get("urgente") if isinstance(out.get("urgente"), dict) else {}
    out["urgente"] = {k: bool(urgent.get(k)) for k in DEFAULT_PROFILE["urgente"]}
    return out


def set_profile_field(core, field, value):
    p = profile(core)
    field = (field or "").strip().lower()
    if field in ("meta", "metas"):
        p["metas"] = (p.get("metas") or [])[-7:] + [redact(value, core)[:180]]
    elif field in ("debilidad", "debilidades"):
        p["debilidades"] = (p.get("debilidades") or [])[-7:] + [redact(value, core)[:180]]
    elif field in ("fortaleza", "fortalezas"):
        p["fortalezas"] = (p.get("fortalezas") or [])[-7:] + [redact(value, core)[:180]]
    elif field in ("techo", "techo_usd"):
        try:
            cap = float(value)
        except (TypeError, ValueError):
            return "Techo inválido. No subo el tope de $100."
        if cap > HARD_ORDER:
            return "No subo el techo por encima de $100. El money gate no se mueve."
        p["techo_usd"] = cap
    elif field == "beneficio":
        p["beneficio"] = redact(value, core)[:240]
    else:
        return "Campos: meta, debilidad, fortaleza, techo, beneficio."
    core.kv_set(PROFILE_KEY, p)
    return "Perfil actualizado. No mueve dinero."


def profile_text(core):
    p = profile(core)
    return ("Perfil de decisión (solo para proponer):\n"
            f"• Metas: {'; '.join(p.get('metas') or ['—'])}\n"
            f"• Debilidades: {'; '.join(p.get('debilidades') or ['—'])}\n"
            f"• Fortalezas: {'; '.join(p.get('fortalezas') or ['—'])}\n"
            f"• Beneficio del dueño: {p.get('beneficio')}\n"
            f"• Techo ${p['techo_usd']:.0f} (no puede pasar $100). Nada se ejecuta solo.")


def consult(core, kind, amount=0):
    """Consulted before any proposal. Never authorizes money outside the gate."""
    p = profile(core)
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount > p["techo_usd"] or amount > HARD_ORDER:
        return {"allow_propose": False, "execute": False,
                "reason": "pasa el techo del perfil o el tope de $100; no lo propongo como acción"}
    if kind in NEVER_DELEGATE:
        return {"allow_propose": False, "execute": False,
                "reason": "Coinbase y Amazon no se delegan"}
    return {"allow_propose": True, "execute": False,
            "reason": p.get("beneficio") or "solo si deja al dueño mejor",
            "techo_usd": p["techo_usd"]}


def leak_refusal(text):
    if LEAK_RX.search(str(text or "")):
        return ("No suelto contraseñas, códigos ni datos financieros, aunque la petición parezca del dueño. "
                "El dinero sigue fuera de este proceso.")
    return None


def local_reply(core, text):
    """Day-to-day rules. None means the existing path (short model only if configured)."""
    refused = leak_refusal(text)
    if refused:
        return refused
    t = re.sub(r"\s+", " ", str(text or "").strip().lower())
    if t in ("/perfil", "mi perfil", "perfil de decision", "perfil de decisión"):
        return profile_text(core)
    if t in ("/flujo", "flujo de caja", "cash flow", "como va el cash flow"):
        return cashflow_text(core)
    if t in ("/monetizar", "monetizar", "ideas de cash flow"):
        return monetization_text(core)
    return None


def choose_model(history):
    """Short model only after local rules miss. Empty env keeps the existing model."""
    model = short_model()
    if not model:
        return None
    return model


def boot(core):
    prev = core.kv_get(BOOT_KEY, {})
    if not isinstance(prev, dict):
        prev = {}
    now = core._now().isoformat(timespec="seconds") if hasattr(core, "_now") else datetime.datetime.now().isoformat(timespec="seconds")
    core.kv_set(BOOT_KEY, {"at": now, "previous": prev.get("at"), "cut": CUT})
    return prev.get("at")


def history_status(core):
    hist = core.kv_get(HISTORY_KEY, [])
    n = len(hist) if isinstance(hist, list) else 0
    boot = core.kv_get(BOOT_KEY, {})
    previous = boot.get("previous") if isinstance(boot, dict) else None
    survived = bool(previous) and n > 0
    seal = "sin comprobar"
    if hasattr(core, "_seal_status"):
        try:
            seal = core._seal_status()
        except Exception:
            seal = "no pude leerlo"
    if survived:
        persist = f"sobrevivió el reinicio ({n} mensajes redactados; arranque anterior {previous})"
    elif n:
        persist = f"{n} mensajes guardados; aún no hay reinicio que comprobar"
    else:
        persist = "vacío; se guarda cifrado si DATA_ENCRYPTION_KEY está puesta, si no en el almacén actual"
    return f"Historial: {persist}. Sellado: {seal}."


def _books(core):
    if hasattr(core, "finances_summary"):
        try:
            return core.finances_summary()
        except Exception:
            return {}
    return {}


def _bills_due(core):
    if not hasattr(core, "_pload"):
        return []
    try:
        personal = core._pload()
    except Exception:
        return []
    today = core._today() if hasattr(core, "_today") else datetime.date.today()
    month = today.strftime("%Y-%m")
    due = []
    for bill in personal.get("bills") or []:
        if month in (bill.get("paid") or []):
            continue
        try:
            day = int(bill.get("day") or 0)
            amount = float(bill.get("amount") or 0)
        except (TypeError, ValueError):
            continue
        if 1 <= day <= 31 and day >= today.day:
            due.append({"name": bill.get("name") or "gasto", "day": day, "amount": amount})
    return due


def cashflow_text(core):
    books = _books(core)
    net = books.get("net_profit")
    due = _bills_due(core)
    upcoming = sum(b["amount"] for b in due)
    lines = ["Cash flow (libros existentes, no muevo dinero):"]
    if net is None:
        lines.append("• Libros: sin resumen todavía. Revisa /banco semana y /cobros.")
    else:
        lines.append(f"• Neto USD en libros: {net}. Otras monedas no se convierten.")
    if due:
        lines.append("• Por vencer este mes: " + ", ".join(f"{b['name']} día {b['day']} ${b['amount']:.0f}" for b in due[:6]))
        if net is not None and upcoming > max(0, net):
            lines.append("• Alerta temprana: lo que vence pasa el neto de libros. No pagué nada.")
    else:
        lines.append("• Sin gastos pendientes en el perfil de cuentas de este mes.")
    lines.append("• YouTube y Amazon siguen en construcción; esto no compra ni publica.")
    return "\n".join(lines)


def monetization_text(core):
    decision = consult(core, "cashflow", 0)
    books = _books(core)
    ideas = [
        "YouTube: un video corto del trabajo ya hecho, costo de cómputo dentro del presupuesto diario, beneficio = audiencia. No publico solo.",
        "Amazon: ficha de un producto que ya está en inventario, sin precio dinámico. No compro ni delego Amazon.",
        "Libros: cobrar lo ya anotado en /cobros antes de gastar. No muevo dinero fuera del gate.",
    ]
    if books.get("net_profit", 0) < 0:
        ideas.insert(0, "Los libros van en negativo: primero cobrar, no abrir gasto nuevo.")
    d = _load(core)
    d["proposals"] = (d["proposals"] + [{
        "at": datetime.datetime.now().isoformat(timespec="seconds"),
        "execute": False,
        "decision": decision["reason"],
        "ideas": len(ideas),
    }])[-20:]
    _save(core, d)
    return ("Propuesta de cash flow (no ejecuto nada):\n- " + "\n- ".join(ideas)
            + f"\nCriterio: {decision['reason']}. Costo-beneficio antes de cada paso. Tú decides el deploy y el /enviar.")


def anomaly(core, kind, detail, amount=0):
    """Odd spend or odd delegation reuses the gate lockout and audit. Does not raise limits."""
    odd = kind in NEVER_DELEGATE or kind in {"odd-spend", "odd-delegation"}
    try:
        amount = float(amount or 0)
    except (TypeError, ValueError):
        amount = 0
    if amount > HARD_ORDER or amount > HARD_DAY:
        odd = True
    if not odd:
        return {"locked": False, "reason": "patrón encaja"}
    if hasattr(core, "_gload") and hasattr(core, "_gsave") and hasattr(core, "gate_audit"):
        g = core._gload()
        until = (core._now() + datetime.timedelta(minutes=getattr(core, "GATE_LOCK_MIN", 30))).isoformat(timespec="seconds")
        g["locked_until"] = until
        core.gate_audit(g, "v420-apagado", kind, "lockout", redact(detail, core)[:180])
        core._gsave(g)
    return {"locked": True, "reason": "patrón no encaja; reusé el lockout del gate", "execute": False}


def mark_urgent(core, name, on):
    p = profile(core)
    key = {"cashflow": "cash-flow", "cash-flow": "cash-flow", "camara": "camara", "cámara": "camara",
           "emergencia": "emergencia"}.get((name or "").strip().lower())
    if not key:
        return "Eventos: cash-flow, camara, emergencia."
    p["urgente"][key] = bool(on)
    core.kv_set(PROFILE_KEY, p)
    return f"Urgente {key}: {'marcado' if on else 'apagado'}. Solo entonces armo borrador de llamada; no marco solo."


def _drafts(core):
    rows = core.kv_get(DRAFTS_KEY, [])
    return rows if isinstance(rows, list) else []


def channel_status():
    send = os.getenv("TWILIO_SEND_ENABLED", "").strip().lower() in {"1", "true", "yes"}
    return ("Canal Twilio propio: " + ("credenciales presentes" if twilio_configured() else "no configurado")
            + ". Borrador + /enviar. Autoenvío apagado."
            + (" 2FA del canal requerida." if True else "")
            + (" Envío real sigue desactivado en este corte." if not send else " Envío real no se usa en 4.2.0 igual.")
            + " Telegram sigue en el bot actual.")


def issue_channel_2fa(core):
    code = f"{secrets.randbelow(10 ** 6):06d}"
    salt = secrets.token_hex(8)
    d = _load(core)
    d["channel_2fa"] = {"salt": salt, "hash": hashlib.sha256(f"{salt}|{code}".encode()).hexdigest(),
                        "until": (datetime.datetime.now() + datetime.timedelta(minutes=5)).isoformat(timespec="seconds"),
                        "ok": False}
    _save(core, d)
    return code


def check_channel_2fa(core, code):
    d = _load(core)
    row = d.get("channel_2fa") or {}
    if not row or not re.fullmatch(r"\d{6}", str(code or "")):
        return False
    digest = hashlib.sha256(f"{row.get('salt')}|{code}".encode()).hexdigest()
    if not secrets.compare_digest(digest, row.get("hash") or ""):
        return False
    row["ok"] = True
    row["hash"] = ""
    d["channel_2fa"] = row
    _save(core, d)
    return True


def draft_channel(core, kind, destination, body):
    kind = (kind or "").strip().lower()
    if kind not in {"sms", "whatsapp", "llamada"}:
        return "Canal: sms, whatsapp o llamada."
    if kind == "llamada":
        p = profile(core)
        if not any(p["urgente"].values()):
            return "No armo llamada: ningún evento urgente está marcado por el dueño."
    rows = _drafts(core)
    item = {"id": (rows[-1]["id"] + 1) if rows else 1, "kind": kind,
            "to": redact(destination, core)[:40], "body": redact(body, core)[:500],
            "status": "draft", "sent": False}
    rows.append(item)
    core.kv_set(DRAFTS_KEY, rows[-30:])
    return (f"Borrador {kind} #{item['id']} guardado. No envié nada. "
            "Verifica 2FA con /canal 2fa y luego /enviar c{id}. Telegram no cambia.")


def approve_channel_draft(core, ref):
    """Owner path only. Never calls Twilio in this cut."""
    d = _load(core)
    if not (d.get("channel_2fa") or {}).get("ok"):
        return "Falta 2FA del canal (/canal 2fa CODIGO). No envié."
    rows = _drafts(core)
    for item in rows:
        if f"c{item['id']}" == ref or str(item["id"]) == ref:
            item["status"] = "approved-not-sent"
            core.kv_set(DRAFTS_KEY, rows)
            return (f"Borrador #{item['id']} aprobado por ti. Envío real desactivado en 4.2.0 "
                    "(no hay llamada Twilio). Telegram sigue igual.")
    return "No hay ese borrador de canal."


def scheduler_cycle(core):
    """One bounded cycle. Stops at the daily compute budget. Never executes."""
    day = core._today().isoformat() if hasattr(core, "_today") else datetime.date.today().isoformat()
    d = _load(core)
    used = int((d.get("compute") or {}).get(day) or 0)
    budget = compute_budget()
    if used >= budget:
        return {"ran": False, "reason": "presupuesto diario de cómputo agotado", "used": used}
    d["compute"] = {day: used + 1}
    _save(core, d)
    alert = cashflow_text(core)
    proposal = monetization_text(core)
    note = None
    if "Alerta temprana" in alert:
        p = profile(core)
        if p["urgente"].get("cash-flow"):
            note = draft_channel(core, "llamada", "dueño", "Alerta de cash flow. No marqué.")
        else:
            note = "Alerta de cash flow en texto. Llamada no armada: el dueño no la marcó urgente."
    return {"ran": True, "used": used + 1, "budget": budget, "alert": alert, "proposal": proposal,
            "call_draft": note, "execute": False}


def command(core, cmd, arg):
    cmd = (cmd or "").lower()
    parts = (arg or "").split(maxsplit=1)
    head = parts[0].lower() if parts else ""
    rest = parts[1] if len(parts) > 1 else ""
    if cmd == "/perfil":
        if not head:
            return profile_text(core)
        return set_profile_field(core, head, rest)
    if cmd == "/flujo":
        return cashflow_text(core)
    if cmd == "/monetizar":
        return monetization_text(core)
    if cmd == "/urgente":
        if not head:
            p = profile(core)
            return "Urgentes: " + ", ".join(f"{k}={'sí' if v else 'no'}" for k, v in p["urgente"].items())
        on = rest.strip().lower() not in {"off", "no", "apagado"}
        return mark_urgent(core, head, on)
    if cmd == "/canal":
        if head in {"", "estado"}:
            return channel_status()
        if head == "2fa" and not rest:
            code = issue_channel_2fa(core)
            return f"Código 2FA del canal (un uso, 5 min): {code}. No lo guardo en claro. No envié nada."
        if head == "2fa":
            return "2FA del canal ok." if check_channel_2fa(core, rest.strip()) else "Código 2FA incorrecto. No envié."
        if head in {"sms", "whatsapp", "llamada"}:
            dest, _, body = rest.partition(" ")
            return draft_channel(core, head, dest, body)
        return "Uso: /canal estado · /canal 2fa · /canal sms|+1... texto · llamada solo si hay urgente marcado."
    return None


def status_lines(core):
    try:
        hist = history_status(core)
    except Exception as exc:
        hist = f"Historial: no pude leerlo ({type(exc).__name__})."
    d = _load(core)
    day = datetime.date.today().isoformat()
    used = int((d.get("compute") or {}).get(day) or 0)
    return [
        f"• 4.2.0: local sin tokens en atajos y reglas; modelo corto {'sí' if short_model() else 'no configurado (sigue el modelo actual)'}",
        f"• {hist}",
        f"• Monetización: propuestas con tope de {compute_budget()} ciclos/día (hoy {used}). No ejecuta. Dueño controla el deploy.",
        f"• {channel_status()}",
        "• Firewall/VPN sin logs: configuración de Render, no código. Actualizar cuando tú lo despliegues; no prometo nunca más actualizar.",
    ]


def install(core):
    core.v420 = _sys_module()
    core.v420_local = lambda text: local_reply(core, text)
    core.v420_model = choose_model
    core.v420_status_lines = lambda: status_lines(core)
    core.v420_cycle = lambda: scheduler_cycle(core)
    core.v420_command = lambda cmd, arg: command(core, cmd, arg)
    core.v420_anomaly = lambda kind, detail, amount=0: anomaly(core, kind, detail, amount)
    core.v420_approve_channel = lambda ref: approve_channel_draft(core, ref)
    try:
        boot(core)
    except Exception:
        pass
    return CUT


def _sys_module():
    import sys
    return sys.modules[__name__]
