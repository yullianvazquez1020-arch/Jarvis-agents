"""Jarvis desktop adapter (opt-in, OFF by default: DESKTOP_API_ENABLED=false).

What it is: a small authenticated API under /desktop/v1/ for the owner's LOCAL desktop companion (desktop/app.py),
so he can ask Jarvis things by voice and see panels on his monitors.

First version = READ-ONLY by design, enforced in the backend:
  * The model only sees READ_TOOLS, and run() refuses any other tool before a handler runs.
  * Every tool and panel of this channel runs inside main._WRITE_BLOCK: a business write fails in kv_set itself.
  * No capability to approve money, select real mode, send messages, run /commands or touch the system.
    Text that looks like a code, a /command or an approval is answered without reaching any parser.
Identity: the server decides who is talking. A device is paired with a short one-time code that the owner
approves with /emparejar CODE in his private Telegram chat; the device then claims a token shown once.
Only a SHA-256 of the token is stored. /dispositivos lists and revokes devices.
Sessions: each device has its own conversation history ("desk:<id>"); it is never mixed with Telegram's.
Idempotency: request_id per device is stored before any work; a retry returns the same result, a different
text with the same id is refused, and nothing is replayed after a restart.
"""
import asyncio, datetime as dt, hashlib, json, os, re, secrets, time, unicodedata

core = None
KEY = "jarvis:desktop"
TURNS_KEY = "jarvis:desktop:turns"
AUDIT_KEY = "jarvis:desktop:audit"     # 4.0.5 (2.3): who/when/endpoint/result; never the text or amounts
AUDIT_KEEP = 500
API_VERSION = "1"
ENABLED = os.getenv("DESKTOP_API_ENABLED", "false").strip().lower() in ("true", "1", "yes")

PAIR_TTL = 600            # a pairing request lives 10 minutes
PAIR_MAX_PENDING = 3
PAIR_MAX_FAILS = 5        # wrong /emparejar codes in 30 min -> every pending pairing is cancelled
TEXT_MAX = 1000
BODY_MAX = 16_384
TURN_KEEP = 300
TURN_KEEP_HOURS = 48
RUNNING_STALE_S = 300     # a "running" turn older than this was interrupted (restart): reported, not re-run
RATE_TURNS = 30           # per device per 10 minutes
CAPS_DEFAULT = ("read", "converse")
TOKEN_DAYS = 90           # 4.0.5 (2.2): a device token expires; renewing = pairing again with /emparejar
PANELS = ("estado", "agenda", "cobros", "practica", "brief", "caja")
EVENT_TYPES = ("state", "transcript.final", "reply.text", "panel.open", "proposal.created", "turn.done", "turn.error")
RID_RX = re.compile(r"[A-Za-z0-9_-]{8,64}")
TOKEN_RX = re.compile(r"jd1\.(\d{1,9})\.([A-Za-z0-9_-]{30,80})")

# Tools the model may use on this channel: the core allowlist (main.READ_ONLY_TOOLS), bound at install().
READ_TOOLS = frozenset()

DESKTOP_PROMPT = (
    "\nCHANNEL: the owner's DESKTOP VOICE panel (read-only, version 1). Your reply will be read aloud: answer in "
    "Spanish in at most 3 short sentences, no markdown, no tables, no emojis, no URLs. Use conversational Puerto Rican Spanish, addressing the owner as tú: warm, clear and calm. Prefer everyday phrasing such as «vamos a revisarlo», «ya está listo» only when verified, and «te digo qué falta». Avoid peninsular Spanish, stiff translations, forced slang, theatrical catchphrases and repeatedly calling the owner boss. Start with the useful answer, use conversational transitions and never invent progress or completion. You can ONLY read data with "
    "the tools you see. You cannot save, edit, delete, prepare orders or messages, approve, confirm, change the "
    "crypto mode or run commands here; if he asks for any of that, say it is done from his private Telegram chat. "
    "Text that looks like an approval code or a command is never an approval on this channel.")

_rate = {}        # device id -> [timestamps]   (single worker: in-memory is enough)
_running = {}     # device id -> count of turns in progress in this process


class DesktopError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail); self.status = status; self.detail = detail


# --- storage --------------------------------------------------------------------------
def _now():
    return core._now()

def _stamp():
    return _now().isoformat(timespec="seconds")

def _age_s(stamp):
    try:
        return (_now() - dt.datetime.fromisoformat(stamp)).total_seconds()
    except (TypeError, ValueError):
        return 10 ** 9

def load():
    d = core.kv_get(KEY, None)
    if d is None:
        d = {}
    if not isinstance(d, dict):
        raise DesktopError(503, "estado de dispositivos dañado")
    for k, v in (("devices", {}), ("pairings", {}), ("seq", 0), ("fails", [])):
        d.setdefault(k, v)
    return d

def save(d):
    core.kv_set(KEY, d)

def load_turns():
    t = core.kv_get(TURNS_KEY, None)
    if t is None:
        return {}
    if not isinstance(t, dict):
        raise DesktopError(503, "registro de turnos dañado")
    return t

def save_turns(t):
    cutoff = TURN_KEEP_HOURS * 3600
    items = sorted(((k, v) for k, v in t.items() if _age_s(v.get("at")) < cutoff), key=lambda kv: kv[1].get("at", ""))
    core.kv_set(TURNS_KEY, dict(items[-TURN_KEEP:]))

def _h(s):
    return hashlib.sha256(str(s).encode()).hexdigest()


# --- pairing ----------------------------------------------------------------------------
def _clean_name(name):
    name = "".join(ch for ch in str(name or "") if ch.isprintable()).strip()[:40]
    return name or "Mac"

def _prune_pairings(d):
    d["pairings"] = {k: p for k, p in d["pairings"].items() if _age_s(p.get("created")) < PAIR_TTL}

def pairing_start(device_name):
    """Unauthenticated, but it grants nothing: the owner must type the code in his private Telegram chat."""
    with core._data_lock:
        d = load(); _prune_pairings(d)
        if len(d["pairings"]) >= PAIR_MAX_PENDING:
            raise DesktopError(429, "hay demasiadas solicitudes de emparejamiento pendientes; espera 10 minutos")
        code = f"{secrets.randbelow(10 ** 6):06d}"; salt = secrets.token_hex(8)
        pid = secrets.token_hex(8); claim = secrets.token_urlsafe(24)
        d["pairings"][pid] = {"name": _clean_name(device_name), "salt": salt, "code_hash": _h(f"{salt}|{code}"),
                              "claim_hash": _h(claim), "status": "pending", "created": _stamp()}
        save(d)
    return {"pairing_id": pid, "claim_secret": claim, "code": code, "expires_in": PAIR_TTL,
            "instructions": f"En tu chat privado de Telegram con Jarvis escribe: /emparejar {code}"}

def pairing_approve(code):
    """Owner-only Telegram command /emparejar CODE (the router enforces his private chat)."""
    code = re.sub(r"\D", "", str(code or ""))
    with core._data_lock:
        d = load(); _prune_pairings(d)
        d["fails"] = [f for f in d["fails"] if _age_s(f) < 1800]
        if len(d["fails"]) >= PAIR_MAX_FAILS:
            save(d)
            return "⛔ Demasiados códigos incorrectos. Espera 30 minutos y empieza otra vez desde la Mac."
        match = None
        for pid, p in d["pairings"].items():
            if p["status"] == "pending" and len(code) == 6 and secrets.compare_digest(p["code_hash"], _h(f"{p['salt']}|{code}")):
                match = (pid, p)
        if not match:
            d["fails"].append(_stamp())
            if len(d["fails"]) >= PAIR_MAX_FAILS:
                d["pairings"] = {}
            save(d)
            return "⚠️ Ese código no corresponde a ninguna solicitud vigente. No aprobé nada."
        pid, p = match
        p["status"] = "approved"; p["approved_at"] = _stamp(); save(d)
    return (f"✅ Aprobé el dispositivo «{p['name']}» con permisos de solo lectura y conversación. Vuelve a la "
            "Mac: se conectará sola. /dispositivos para verlo o revocarlo.")

def pairing_claim(pid, claim_secret):
    with core._data_lock:
        d = load(); _prune_pairings(d)
        p = d["pairings"].get(str(pid or ""))
        if not p or not secrets.compare_digest(p["claim_hash"], _h(claim_secret or "")):
            save(d)
            raise DesktopError(404, "solicitud no encontrada o vencida")
        if p["status"] != "approved":
            return {"status": "pending"}
        d["seq"] += 1; dev_id = str(d["seq"]); secret = secrets.token_urlsafe(32)
        for old in d["devices"].values():          # pairing again renews: the previous token of that device dies
            if old["name"] == p["name"] and not old.get("revoked"):
                old["revoked"] = True; old["revoked_at"] = _stamp(); old["replaced_by"] = dev_id
        expires = (_now() + dt.timedelta(days=TOKEN_DAYS)).isoformat(timespec="seconds")
        d["devices"][dev_id] = {"id": dev_id, "name": p["name"], "token_hash": _h(secret), "caps": list(CAPS_DEFAULT),
                                "created": _stamp(), "expires": expires, "last_seen": None, "revoked": False}
        del d["pairings"][pid]
        save(d)
    return {"status": "approved", "device_id": dev_id, "token": f"jd1.{dev_id}.{secret}",
            "caps": list(CAPS_DEFAULT), "expires": expires,
            "note": f"Este token se muestra una sola vez y vence en {TOKEN_DAYS} días."}

def _expires(dev):
    if dev.get("expires"):
        return dev["expires"]
    try:   # devices paired before 4.0.5: 90 days from their creation
        return (dt.datetime.fromisoformat(dev["created"]) + dt.timedelta(days=TOKEN_DAYS)).isoformat(timespec="seconds")
    except (KeyError, TypeError, ValueError):
        return "2000-01-01T00:00:00-04:00"

def _expired(dev):
    return _now() >= dt.datetime.fromisoformat(_expires(dev))

def devices_text(arg=""):
    """/dispositivos [revocar N]"""
    words = str(arg or "").lower().split()
    with core._data_lock:
        d = load()
        if words[:1] == ["revocar"] and len(words) > 1:
            dev = d["devices"].get(re.sub(r"\D", "", words[1]))
            if not dev:
                return "⚠️ Ese dispositivo no existe."
            dev["revoked"] = True; dev["revoked_at"] = _stamp(); save(d)
            return f"🚫 Revoqué «{dev['name']}» (#{dev['id']}). Deja de funcionar desde ya."
    if not d["devices"]:
        return ("🖥️ No hay dispositivos emparejados." +
                ("" if ENABLED else "\nLa API de escritorio está apagada (DESKTOP_API_ENABLED=false)."))
    lines = ["🖥️ Dispositivos de escritorio:"]
    for dev in d["devices"].values():
        st = ("revocado" if dev.get("revoked") else "VENCIDO (empareja de nuevo)" if _expired(dev) else "activo")
        seen = (dev.get("last_seen") or "nunca")[:16].replace("T", " ")
        lines.append(f"• #{dev['id']} {dev['name']} · {st} · alta {dev['created'][:10]} · último uso {seen} · "
                     f"vence {_expires(dev)[:10]} · permisos: {', '.join(dev['caps'])}")
    lines.append("Revocar: /dispositivos revocar N" + ("" if ENABLED else "\n(API apagada: DESKTOP_API_ENABLED=false)"))
    recent = audit_lines()
    if recent:
        lines += ["", "Últimos accesos (sin contenido):"] + recent
    return "\n".join(lines)


# --- audit (4.0.5, 2.3) ---------------------------------------------------------------------
def audit(device, endpoint, status, kind=""):
    """One line per request. Only device id, time, endpoint, HTTP result and the kind of turn
    (refuse/panel/ai). Never the question, the answer or any amount. Never breaks the request."""
    try:
        with core._data_lock:
            a = core.kv_get(AUDIT_KEY, [])
            a = a if isinstance(a, list) else []
            a.append({"at": _stamp(), "device": str(device or "-")[:12], "endpoint": endpoint[:40],
                      "result": int(status), "kind": str(kind)[:10]})
            core.kv_set(AUDIT_KEY, a[-AUDIT_KEEP:])
    except Exception as e:
        core.logger.warning("desktop audit not saved: %s", type(e).__name__)

def audit_lines(n=8):
    a = core.kv_get(AUDIT_KEY, [])
    a = a if isinstance(a, list) else []
    return [f"• {x['at'][5:16].replace('T', ' ')} #{x['device']} {x['endpoint']} → {x['result']}"
            + (f" ({x['kind']})" if x.get("kind") else "") for x in a[-n:][::-1]]

def _device_hint(authorization):
    m = TOKEN_RX.fullmatch((authorization or "").replace("Bearer ", "", 1).strip())
    return m.group(1) if m else "-"


# --- authentication -----------------------------------------------------------------------
def authenticate(authorization, cap):
    if not ENABLED:
        raise DesktopError(404, "Not Found")
    m = TOKEN_RX.fullmatch((authorization or "").replace("Bearer ", "", 1).strip())
    if not m:
        raise DesktopError(401, "credencial inválida")
    dev_id, secret = m.groups()
    d = load()
    dev = d["devices"].get(dev_id)
    if not dev or dev.get("revoked") or not secrets.compare_digest(dev["token_hash"], _h(secret)):
        raise DesktopError(401, "credencial inválida o revocada")
    if _expired(dev):
        raise DesktopError(401, "el emparejamiento venció; empareja otra vez con /emparejar")
    if cap not in dev.get("caps", []):
        raise DesktopError(403, f"este dispositivo no tiene permiso '{cap}'")
    if _age_s(dev.get("last_seen")) > 300:   # at most one write every 5 minutes per device
        with core._data_lock:
            d = load(); d["devices"][dev_id]["last_seen"] = _stamp(); save(d)
    return dev


# --- read-only execution ---------------------------------------------------------------------
async def _read_only(fn, *args):
    """Run fn in a thread with every business write blocked at the storage layer."""
    token = core._WRITE_BLOCK.set("escritorio")
    try:
        return await asyncio.to_thread(fn, *args)
    finally:
        core._WRITE_BLOCK.reset(token)

_EMOJI_RX = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")

def speakable(text, limit=600):
    """Text safe to read aloud: no secrets, URLs, markdown or emojis."""
    t = core._redact_secrets(str(text or ""))[0]
    t = re.sub(r"https?://\S+", "", t)
    t = _EMOJI_RX.sub("", t)
    t = re.sub(r"[*_`#>|•]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit]

def _lines(text):
    return [ln for ln in core._redact_secrets(str(text or ""))[0].splitlines()][:60]

def _panel_estado():
    ms = core.crypto_mode_state()
    st = core._sched_state
    lines = [f"Jarvis {core.VERSION}", f"Datos: {core.storage_mode()}",
             f"IA: {'configurada' if core.AI_READY else 'sin ANTHROPIC_API_KEY válida'}",
             f"Modo cripto: {core.MODE_SHORT[ms['effective']]}",
             f"Programador: último ciclo {str(st.get('last_tick') or '—')[11:16] or '—'}"]
    speak = (f"Estoy en línea, versión {core.VERSION}. Modo cripto "
             f"{'práctica' if ms['effective'] == 'practice' else 'real'}.")
    return {"title": "Estado", "lines": lines, "speak": speak, "sensitive": False}

def _panel_agenda():
    u = core.upcoming(7)
    lines = _lines(core.brief_text())
    ev = u.get("events", [])
    if ev:
        lines += ["", "Próximos 7 días:"] + ["• " + core._ev_line(v) for v in ev[:15]]
    n_rem = len([r for r in u["reminders"] if str(r.get("due", ""))[:10] == core._today().isoformat()])
    n_ev = len([v for v in ev if str(v.get("date", ""))[:10] == core._today().isoformat()])
    speak = (f"Hoy tienes {n_rem} recordatorio{'s' if n_rem != 1 else ''} y {n_ev} evento{'s' if n_ev != 1 else ''}. "
             f"En los próximos 7 días hay {len(ev)} en el calendario. Está todo en pantalla.")
    return {"title": "Agenda", "lines": lines, "speak": speak, "sensitive": False}

def _panel_cobros():
    lines = _lines(core.collections_text())
    jobs = [j for j in core._cload()["jobs"] if float(j.get("balance", 0)) > 0
            and j["status"] not in ("quote", "paid", "cancelled")]
    total = sum(float(j["balance"]) for j in jobs)
    speak = (f"Tienes {core._bank_usd(total)} por cobrar en {len(jobs)} trabajo{'s' if len(jobs) != 1 else ''}. "
             "El detalle está en pantalla." if jobs else "No hay nada pendiente por cobrar.")
    return {"title": "Cobros", "lines": lines, "speak": speak, "sensitive": True}

def _panel_practica():
    ms = core.crypto_mode_state()
    lines = [f"Modo activo: {core.MODE_LABEL[ms['effective']]}", ""]
    lines += _lines(core.paper_status_text())
    try:
        s = core._simload()
        lines += ["", f"Cuenta de práctica manual: efectivo {core._bank_usd(s['cash'])}"]
        lines += [f"• {p.split('-')[0]}: {round(pos['qty'], 8)} (costo {core._bank_usd(pos['cost'])})"
                  for p, pos in s["positions"].items()]
    except ValueError as e:
        lines += ["", f"Cuenta de práctica manual: {e}"]
    speak = "Abrí el panel de práctica. Todo es dinero simulado." if ms["effective"] == "practice" else \
        "Abrí el panel de práctica. Ojo: el modo activo es real; aquí solo se muestra."
    return {"title": "Práctica (simulado)", "lines": lines, "speak": speak, "sensitive": True}

def _panel_brief():
    module = getattr(core, "_brief", None)
    if module is None:
        raise DesktopError(503, "Brief comercial no disponible en esta versión")
    text = module.commercial_brief()
    return {"title": "Brief comercial · mismo informe de Telegram", "lines": _lines(text),
            "speak": "Aquí tienes el brief comercial de ISLAFIX, con los mismos datos que consultas en Telegram. Te dejé el detalle en pantalla.", "sensitive": True}


def _panel_caja():
    module = getattr(core, "_business_workflows", None)
    if module is None:
        raise DesktopError(503, "Caja no disponible en esta versión")
    text = module.cash_text()
    return {"title": "Caja · mismo informe de Telegram", "lines": _lines(text),
            "speak": "Te abrí la caja. El informe separa el saldo observado, lo registrado y las proyecciones; un cobro pendiente todavía no es dinero disponible.", "sensitive": True}


_PANEL_FN = {"estado": _panel_estado, "agenda": _panel_agenda, "cobros": _panel_cobros, "practica": _panel_practica,
             "brief": _panel_brief, "caja": _panel_caja}

async def panel(name):
    if name not in _PANEL_FN:
        raise DesktopError(404, "panel desconocido")
    p = await _read_only(_PANEL_FN[name])
    return {"panel": name, **p, "speak": speakable(p["speak"]), "as_of": _stamp()}


# --- turns ----------------------------------------------------------------------------------
def _norm(text):
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[¿?¡!.,;:]", " ", t)).strip()

# 4.0.5 (1.3): same list as desktop/intents.py. Anything that sounds like an action is answered here, without AI
# and without reaching any parser; this API has no route for /aprobar, /confirmar, /enviar, /anotar, /ejecutar
# or delegate, and none of those tools is in READ_ONLY_TOOLS.
ACTION_MSG = ("Eso no se hace por voz ni desde el panel. Confirmar, aprobar, rechazar, enviar, anotar, ejecutar, "
              "restaurar, borrar o mover dinero se hace solo en tu chat privado de Telegram.")
_REFUSE = (
    (re.compile(r"^\s*/"), "Por voz no ejecuto comandos. Escríbelo en tu chat privado de Telegram."),
    (re.compile(r"\d{6}|\d{3}\s\d{3}"), "Por voz no recibo códigos. Las confirmaciones solo valen en tu chat privado de Telegram."),
    (re.compile(r"\b(confirm\w*|aprob\w*|aprueb\w*|rechaz\w*|modo real|activa real|envi\w*|anot\w*|apunt\w*|"
                r"ejecut\w*|restaur\w*|borr\w*|elimin\w*|autoriz\w*|transfier\w*|transferenc\w*|retir\w*)\b"),
     ACTION_MSG),
    (re.compile(r"^(jarvis )?(compra|comprame|compre|vende|vendeme|venda|paga|pagale|manda|mandale)\b"), ACTION_MSG),
)
_PANEL_INTENT = (
    ("brief", re.compile(r"\b(brief|resumen comercial|informe comercial)\b")),
    ("caja", re.compile(r"\b(caja|flujo de efectivo)\b")),
    ("cobros", re.compile(r"\b(cobros?|por cobrar|me deben|cuentas por cobrar)\b")),
    ("agenda", re.compile(r"\b(agenda|calendario|que tengo hoy|mis citas)\b")),
    ("practica", re.compile(r"\b(practica|simulador|simulado)\b")),
    ("estado", re.compile(r"\b(como estas|estado del sistema|estado de jarvis|diagnostico)\b")),
)

def classify(text):
    """-> ("refuse", reply) | ("panel", name) | ("ai", None). Deterministic, zero tokens."""
    n = _norm(text)
    for rx, reply in _REFUSE:
        if rx.search(n):
            return "refuse", reply
    if len(n.split()) <= 8:
        for name, rx in _PANEL_INTENT:
            if rx.search(n):
                return "panel", name
    return "ai", None

def _public(rec, rid):
    out = {k: rec.get(k) for k in ("state", "reply", "speak", "events", "sensitive", "llm_used", "at", "done_at", "kind")}
    out["request_id"] = rid
    if out["state"] == "running" and _age_s(rec.get("at")) > RUNNING_STALE_S:
        out["state"] = "uncertain"
        out["reply"] = "Este turno se interrumpió (reinicio). No lo repetí; pregúntame otra vez si lo necesitas."
    return out

def turn_get(dev, rid):
    if not RID_RX.fullmatch(str(rid or "")):
        raise DesktopError(400, "request_id inválido")
    rec = load_turns().get(f"{dev['id']}:{rid}")
    if not rec:
        raise DesktopError(404, "turno no encontrado")
    return _public(rec, rid)

def _rate_ok(dev_id):
    now = time.monotonic()
    q = [t for t in _rate.get(dev_id, []) if now - t < 600]
    if len(q) >= RATE_TURNS:
        _rate[dev_id] = q; return False
    q.append(now); _rate[dev_id] = q; return True

async def turn(dev, rid, text):
    if not RID_RX.fullmatch(str(rid or "")):
        raise DesktopError(400, "request_id inválido (8 a 64 letras, números, - o _)")
    if not isinstance(text, str) or not text.strip() or len(text) > TEXT_MAX:
        raise DesktopError(400, f"texto vacío o de más de {TEXT_MAX} caracteres")
    clean = core._redact_secrets(text.strip())[0]
    key = f"{dev['id']}:{rid}"; digest = _h(clean)
    with core._data_lock:
        turns = load_turns(); rec = turns.get(key)
        if rec:
            if rec["hash"] != digest:
                raise DesktopError(409, "ese request_id ya se usó con otro texto")
            return _public(rec, rid)          # retry of the same request: same answer, nothing runs again
        if _running.get(dev["id"], 0) >= 1:
            raise DesktopError(429, "ya hay una consulta en curso; espera la respuesta")
        if not _rate_ok(dev["id"]):
            raise DesktopError(429, "demasiadas consultas seguidas; espera unos minutos")
        turns[key] = {"hash": digest, "state": "running", "at": _stamp(), "device": dev["id"]}
        save_turns(turns)                     # durable BEFORE any work
    _running[dev["id"]] = _running.get(dev["id"], 0) + 1
    events, sensitive, llm, kind_seen = [], False, False, "?"
    try:
        kind, arg = classify(clean); kind_seen = kind
        if kind == "refuse":
            reply = arg
        elif kind == "panel":
            p = await panel(arg)
            reply = p["speak"]; sensitive = p["sensitive"]
            events.append({"type": "panel.open", "panel": arg})
        elif not core.AI_READY:
            reply = core.AI_OFF_MSG
        else:
            llm = True
            reply = await core.run(f"desk:{dev['id']}", clean, allowed_tools=READ_TOOLS,
                                   extra_system=DESKTOP_PROMPT, read_only="escritorio")
            sensitive = bool(re.search(r"\$\s?\d|\d+[.,]\d{2}|\d+\s*d[oó]lar", reply, re.I))
        state = "done"
    except Exception as e:
        reply = core._fail_text(e); state = "error"
        events = []
        core.logger.warning("desktop turn failed: %s", type(e).__name__)
    finally:
        _running[dev["id"]] = max(0, _running.get(dev["id"], 1) - 1)
    reply = core._redact_secrets(str(reply))[0]
    events = [{"type": "reply.text"}] + events + [{"type": "turn.done" if state == "done" else "turn.error"}]
    rec = {"hash": digest, "state": state, "at": turns[key]["at"], "done_at": _stamp(), "device": dev["id"], "kind": kind_seen,
           "reply": reply, "speak": speakable(reply), "events": events, "sensitive": sensitive, "llm_used": llm}
    with core._data_lock:
        t = load_turns(); t[key] = rec; save_turns(t)
    return _public(rec, rid)


def status_info(dev):
    """4.0.5 (3.1): what the top bar of screen 1 shows. Configuration only: no balances, no amounts."""
    ms = core.crypto_mode_state()
    return {"api": API_VERSION, "jarvis_version": core.VERSION, "device": {"id": dev["id"], "name": dev["name"],
            "caps": dev["caps"], "expires": _expires(dev)}, "ai_configured": core.AI_READY,
            "storage": core.storage_mode(), "crypto_mode": ms["effective"], "crypto_mode_selected": ms["selected"],
            "coinbase_connected": bool(core.CB_ON), "real_trading_active": ms["effective"] == "real" and bool(core.CB_TRADING),
            "panels": list(PANELS), "events": list(EVENT_TYPES), "time": _stamp()}


# --- HUD (4.0.5, 3.2): second-monitor cards, read-only, each with the time of its data --------------
HUD_CARDS = ("cobros", "vencidos", "agenda", "balances", "stock", "mensajes", "practica")
BANK_STALE_DAYS = 3

def _card(cid, title, lines, as_of, value="", stale=False, sensitive=False, detail=None):
    return {"id": cid, "title": title, "value": str(value), "lines": [str(x)[:200] for x in lines][:8],
            "as_of": as_of, "stale": bool(stale), "sensitive": bool(sensitive), "detail": detail}

def _hud_cards():
    now = _stamp(); today = core._today(); tomorrow = today + dt.timedelta(days=1)
    cards = []
    jobs = [x for x in core._cload()["jobs"] if float(x.get("balance", 0)) > 0
            and x["status"] not in ("quote", "paid", "cancelled")]
    cards.append(_card("cobros", "Cobros pendientes", [f"{x['client_name']} — {x['title']}: {core._bank_usd(x['balance'])}"
                       for x in sorted(jobs, key=lambda x: x.get("due_date") or "9999")[:6]], now,
                       core._bank_usd(sum(float(x["balance"]) for x in jobs)) if jobs else "Nada pendiente",
                       sensitive=True, detail="cobros"))
    late = core.overdue_jobs()
    cards.append(_card("vencidos", "Trabajos vencidos", [f"#{x['id']} {x['client_name']} — {x['title']} (venció {x.get('due_date')})"
                       for x in late[:6]], now, f"{len(late)}" if late else "Ninguno", detail=None))
    u = core.upcoming(1)
    ev = [v for v in u.get("events", []) if v["date"] in (today.isoformat(), tomorrow.isoformat())]
    rem = [r for r in u["reminders"] if str(r.get("due", ""))[:10] in (today.isoformat(), tomorrow.isoformat())]
    lines = [("Hoy " if v["date"] == today.isoformat() else "Mañana ") + core._ev_line(v, with_date=False) for v in ev[:5]]
    lines += [("Hoy " if str(r["due"])[:10] == today.isoformat() else "Mañana ") + f"{str(r['due'])[11:16]} {r['text']}"
              for r in rem[:5]]
    cards.append(_card("agenda", "Agenda hoy y mañana", lines, now, f"{len(ev) + len(rem)}" if lines else "Libre",
                       detail="agenda"))
    k = core._kload(); bl = []; stale = False; oldest = None
    for a in k["accounts"].values():
        if a.get("balance") is None:
            continue
        days = (today - dt.date.fromisoformat(a["balance_date"])).days
        stale = stale or days > BANK_STALE_DAYS; oldest = min(oldest or a["balance_date"], a["balance_date"])
        bl.append(f"{a['name']}: {core._bank_usd(a['balance'])} (dato del {a['balance_date']}"
                  + (f", hace {days} días" if days > BANK_STALE_DAYS else "") + ")")
    cards.append(_card("balances", "Balances del banco", bl or ["Sin datos: mándale a Jarvis el archivo del banco"],
                       oldest or now, f"{len(bl)} cuenta(s)" if bl else "Sin datos", stale=stale, sensitive=True))
    low = core.list_inventory(low_only=True)["items"]
    cards.append(_card("stock", "Stock bajo", [f"{x['name']}: {x['quantity']} {x['unit']} (mínimo {x['min_stock']})"
                       for x in low[:6]], now, f"{len(low)}" if low else "Todo bien"))
    drafts = [x for x in core._oload()["drafts"] if x["status"] == "pending"]
    cards.append(_card("mensajes", "Mensajes esperando /enviar", [f"#{x['id']} {x.get('client_name') or x.get('to', '')}"
                       f" ({x.get('channel', '')})" for x in drafts[:6]], now, f"{len(drafts)}" if drafts else "Ninguno"))
    ps = core.paper_status(); ms = core.crypto_mode_state()
    cards.append(_card("practica", "Práctica cripto (simulada)",
                       [f"Capital simulado {core._bank_usd(ps['equity'])} ({ps['pnl_pct']:+.2f}%)",
                        f"Modo activo: {'PRÁCTICA' if ms['effective'] == 'practice' else 'REAL'}"],
                       ps.get("last_run") or ps.get("started") or now, core._bank_usd(ps["equity"]), detail="practica"))
    return cards

def _hud_open_jobs():
    """Read-only projection: stored stage and dates, never a guessed completion percentage."""
    rows = [j for j in core._cload().get("jobs", []) if j.get("status") not in ("paid", "cancelled")]
    rows.sort(key=lambda j: (str(j.get("due_date") or "9999"), str(j.get("id") or "")))
    fields = ("id", "title", "client_name", "status", "created", "updated", "due_date")
    return {"jobs": [{k: j.get(k) for k in fields} for j in rows[:20]], "jobs_count": len(rows)}

async def hud():
    cards = await _read_only(_hud_cards)
    jobs = await _read_only(_hud_open_jobs)
    return core._redact_any({"cards": cards, "as_of": _stamp(), **jobs})


# --- alerts (4.0.5, 3.3): what deserves a side-strip notice now. Read-only: the Telegram engine keeps its own
# "already notified" state; the Mac shows each key once. -------------------------------------------------
def _alerts():
    now = _now(); today = core._today(); out = []
    for r in core._pload()["reminders"]:
        if r.get("done") or not r.get("due"):
            continue
        try:
            due = core._due_dt(r["due"])
        except Exception:
            continue
        if now - dt.timedelta(hours=12) <= due <= now + dt.timedelta(minutes=15):
            out.append({"key": f"rem:{r['id']}:{r['due']}", "kind": "recordatorio", "text": f"Recordatorio: {r['text']}",
                        "when": str(r["due"])})
    for b in core.upcoming(1)["bills"]:
        out.append({"key": f"bill:{b['id']}:{b['month']}", "kind": "cuenta",
                    "text": f"Cuenta {'vencida' if b['overdue'] else 'por vencer'}: {b['name']}", "when": b["due"]})
    for v in core.list_events(today.isoformat(), 1, include_done=False)["events"]:
        if v["date"] != today.isoformat() or not v.get("time"):
            continue
        try:
            start = dt.datetime.fromisoformat(f"{v['date']}T{v['time']}").replace(tzinfo=core.TZ)
        except ValueError:
            continue
        if now <= start <= now + dt.timedelta(minutes=60):
            out.append({"key": f"ev:{v['id']}:{v['date']}", "kind": "evento", "text": f"En menos de 1 hora: {v['title']}",
                        "when": f"{v['date']} {v['time']}"})
    for x in core.list_inventory(low_only=True)["items"]:
        out.append({"key": f"stock:{x['id']}:{today.isoformat()}", "kind": "stock",
                    "text": f"Stock bajo: {x['name']}", "when": today.isoformat()})
    return core._redact_any(out[:20])

async def pulse(dev):
    st = await asyncio.to_thread(status_info, dev)
    st["alerts"] = await _read_only(_alerts)
    return st


# --- install ----------------------------------------------------------------------------------
def install(j):
    global core, READ_TOOLS
    core = j
    READ_TOOLS = j.READ_ONLY_TOOLS

    async def _body(request):
        raw = await request.body()
        if len(raw) > BODY_MAX:
            raise DesktopError(413, "solicitud demasiado grande")
        try:
            data = json.loads(raw or b"{}")
        except ValueError:
            raise DesktopError(400, "JSON inválido") from None
        if not isinstance(data, dict):
            raise DesktopError(400, "JSON inválido")
        return data

    def _http(e):
        if isinstance(e, DesktopError):
            return j.HTTPException(e.status, e.detail)
        if isinstance(e, j.StaleInstance):
            return j.HTTPException(503, "Jarvis se está reiniciando; reintenta")
        core.logger.warning("desktop api error: %s", type(e).__name__)
        return j.HTTPException(500, "error interno")

    async def _audited(endpoint, authorization, work, success_too=True):
        """Run one route; audit device, endpoint and result (never content). The pulse heartbeat is audited
        only when it fails, so the log keeps the meaningful accesses."""
        status, kind = 200, ""
        try:
            out = await work()
            kind = out.get("kind", "") if isinstance(out, dict) else ""
            return out
        except Exception as e:
            http = _http(e); status = http.status_code
            raise http
        finally:
            if ENABLED and (success_too or status != 200):
                await asyncio.to_thread(audit, _device_hint(authorization), endpoint, status, kind)

    @j.app.post("/desktop/v1/pair/start")
    async def desk_pair_start(request: j.Request):
        async def work():
            if not ENABLED:
                raise DesktopError(404, "Not Found")
            data = await _body(request)
            return await asyncio.to_thread(pairing_start, data.get("device_name"))
        return await _audited("pair/start", None, work)

    @j.app.post("/desktop/v1/pair/claim")
    async def desk_pair_claim(request: j.Request):
        async def work():
            if not ENABLED:
                raise DesktopError(404, "Not Found")
            data = await _body(request)
            return await asyncio.to_thread(pairing_claim, data.get("pairing_id"), data.get("claim_secret"))
        out = await _audited("pair/claim", None, work)
        return out

    @j.app.get("/desktop/v1/status")
    async def desk_status(authorization: str = j.Header(None)):
        async def work():
            dev = await asyncio.to_thread(authenticate, authorization, "read")
            return await asyncio.to_thread(status_info, dev)
        return await _audited("status", authorization, work)

    @j.app.post("/desktop/v1/panel")
    async def desk_panel(request: j.Request, authorization: str = j.Header(None)):
        async def work():
            await asyncio.to_thread(authenticate, authorization, "read")
            data = await _body(request)
            return await panel(str(data.get("name", "")))
        return await _audited("panel", authorization, work)

    @j.app.post("/desktop/v1/hud")
    async def desk_hud(authorization: str = j.Header(None)):
        async def work():
            await asyncio.to_thread(authenticate, authorization, "read")
            return await hud()
        return await _audited("hud", authorization, work)

    @j.app.post("/desktop/v1/pulse")
    async def desk_pulse(authorization: str = j.Header(None)):
        async def work():
            dev = await asyncio.to_thread(authenticate, authorization, "read")
            return await pulse(dev)
        return await _audited("pulse", authorization, work, success_too=False)

    @j.app.post("/desktop/v1/turns")
    async def desk_turn(request: j.Request, authorization: str = j.Header(None)):
        async def work():
            dev = await asyncio.to_thread(authenticate, authorization, "converse")
            data = await _body(request)
            return await turn(dev, data.get("request_id"), data.get("text"))
        return await _audited("turns", authorization, work)

    @j.app.post("/desktop/v1/turns/get")
    async def desk_turn_get(request: j.Request, authorization: str = j.Header(None)):
        async def work():
            dev = await asyncio.to_thread(authenticate, authorization, "converse")
            data = await _body(request)
            return await asyncio.to_thread(turn_get, dev, data.get("request_id"))
        return await _audited("turns/get", authorization, work)

    # Owner-only Telegram commands, through the existing private-chat router of the extensions.
    ext = j._extensions
    old_cmd = ext.command
    async def command(chat_id, cmd, arg):
        if cmd == "/emparejar":
            if not ENABLED:
                reply = "La API de escritorio está apagada (DESKTOP_API_ENABLED=false). No aprobé nada."
            else:
                try:
                    reply = await asyncio.to_thread(pairing_approve, arg)
                except Exception as e:
                    reply = f"⚠️ No pude aprobarlo ({type(e).__name__})."
            return await j._tg_safe_send(chat_id, reply)
        if cmd == "/dispositivos":
            try:
                reply = await asyncio.to_thread(devices_text, arg)
            except Exception as e:
                reply = f"⚠️ No pude leer los dispositivos ({type(e).__name__})."
            return await j._tg_safe_send(chat_id, reply)
        return await old_cmd(chat_id, cmd, arg)
    ext.command = command
    ext.COMMANDS.update({"/emparejar", "/dispositivos"})
    j.HELP_TEXT += "\nEscritorio: /emparejar CÓDIGO · /dispositivos [revocar N]"
