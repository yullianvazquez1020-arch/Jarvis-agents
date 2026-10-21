"""Jarvis 4.2.7 — BRAIN: ciclo autónomo continuo.

BRAIN.md (BRAIN_URL) is fetched on boot and every 6 h; the last good copy is cached (Upstash or local files).
Every BRAIN_INTERVAL_MIN minutes one cycle feeds BRAIN + "ejecuta el siguiente ciclo" through the SAME owner
free-text path as an owner Telegram message (core._handle_tg -> core.run). Safety, on purpose:
  * BRAIN text is DATA: every line starting with "/" is dropped, and run() never parses slash commands, so a
    cycle cannot trigger /confirmar, /aprobar, /enviar, /cripto modo or any other command;
  * money keeps /aprobar + /confirmar in the owner's private chat with the hard $100/op and $300/day caps;
  * client messages stay drafts until the owner's /enviar;
  * at most BRAIN_MAX_CYCLES_DAY cycles per Puerto Rico day (runaway-cost cap); kill switch BRAIN_ENABLED and
    owner-only /brain on|off|estado. A failing cycle never stops the loop (exponential backoff, error reported).
"""
import os, asyncio, logging, httpx
from contextvars import ContextVar

# Per-task evidence: concurrent owner conversations cannot contaminate a cycle.
_tool_evidence = ContextVar('brain_tool_evidence', default=None)


def record_tool(name, result):
    evidence = _tool_evidence.get()
    if evidence is None:
        return
    evidence['attempted'] += 1
    failed = isinstance(result, dict) and bool(result.get('error'))
    evidence['errors'] += int(failed)
    # Keep only tool names and counts, never arguments, customer data or results.
    names = evidence['failed_tools' if failed else 'returned_tools']
    if name not in names and len(names) < 50:
        names.append(name)


def evidence_summary():
    e = _tool_evidence.get()
    if e is None:
        return ''
    if not e['attempted']:
        return '\n\nVerificación del servidor: este ciclo no ejecutó herramientas; no hay trabajo verificado.'
    return (f"\n\nVerificación del servidor: {e['attempted']} llamadas a herramientas, "
            f"{e['errors']} con error. Una llamada sin error no demuestra una venta ni una publicación.")

logger = logging.getLogger("jarvis.brain")
DEFAULT_URL = "https://raw.githubusercontent.com/yullianvazquez1020-arch/jarvis-ai-automation/main/BRAIN.md"
CACHE_KEY = "jarvis:brain:cache"
STATE_KEY = "jarvis:brain:state"
REFETCH_S = 6 * 3600
MAX_BRAIN_CHARS = 4000   # it stays in the owner chat history (30 turns): keep input tokens bounded
BACKOFF_MAX_S = 3600


def _int_env(name, default, lo, hi):
    try: v = int(os.getenv(name, str(default)).strip())
    except ValueError: v = default
    return max(lo, min(hi, v))


def env_enabled():
    return os.getenv("BRAIN_ENABLED", "false").strip().lower() in ("1", "true", "yes", "on")


def url():
    return os.getenv("BRAIN_URL", "").strip() or DEFAULT_URL


def interval_s():
    return _int_env("BRAIN_INTERVAL_MIN", 60, 5, 24 * 60) * 60


def max_cycles_day():
    return _int_env("BRAIN_MAX_CYCLES_DAY", 24, 1, 288)


mem = {"loaded": False, "fetched_at": 0.0, "last_cycle": None, "last_error": None, "pending_error": None,
       "failures": 0, "text": ""}


def sanitize(text):
    """BRAIN is data, never commands: drop slash-command lines, cap the size."""
    lines = [ln for ln in str(text or "").replace("\r", "").split("\n") if not ln.lstrip().startswith("/")]
    return "\n".join(lines).strip()[:MAX_BRAIN_CHARS]


def _state(core):
    s = core.kv_get(STATE_KEY, {})
    return s if isinstance(s, dict) else {}


def owner_enabled(core):
    """Env is the master switch; /brain off (stored) can only turn it OFF further, /brain on re-enables."""
    return env_enabled() and _state(core).get("owner_on", True) is not False


def set_owner(core, on):
    with core._data_lock:
        s = _state(core); s["owner_on"] = bool(on); core.kv_set(STATE_KEY, s)


def _count_today(core, bump=False):
    day = core._now().strftime("%Y-%m-%d")
    with core._data_lock:
        s = _state(core)
        if s.get("day") != day: s["day"], s["cycles"] = day, 0
        if bump: s["cycles"] = int(s.get("cycles", 0)) + 1
        core.kv_set(STATE_KEY, s)
        return s["cycles"]


async def fetch(core, now=None):
    now = core.time.monotonic() if now is None else now
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            r = await c.get(url())
        if r.status_code != 200 or not r.text.strip():
            raise RuntimeError(f"BRAIN HTTP {r.status_code}")
        text = sanitize(r.text)
        if not text:
            raise RuntimeError("BRAIN vacío tras eliminar comandos")
        await asyncio.to_thread(core.kv_set, CACHE_KEY, {"text": text, "at": core._now().isoformat()})
        mem.update(text=text, loaded=True)
    except Exception as e:
        cached = await asyncio.to_thread(core.kv_get, CACHE_KEY, {})
        cached_text = sanitize(cached.get("text")) if isinstance(cached, dict) else ""
        if cached_text:
            mem.update(text=cached_text, loaded=True)
        mem["last_error"] = f"fetch: {type(e).__name__}: {str(e)[:120]}"
    mem["fetched_at"] = now
    return mem["loaded"]


async def gumroad_status():
    link = os.getenv("GUMROAD_URL", "").strip()
    if not link: return "Gumroad: GUMROAD_URL no configurado."
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            r = await c.get(link)
        return f"Gumroad: {link} -> HTTP {r.status_code}."
    except Exception as e:
        return f"Gumroad: {link} -> error {type(e).__name__}."


def cycle_text(brain, gumroad, prev_error, auto_social=False):
    err = (f"\nError del ciclo anterior (repórtalo): {prev_error}. "
           "Revisa los registros antes de repetir: el intento pudo haber ejecutado acciones. "
           "No repitas efectos cuyo resultado sea incierto.") if prev_error else ""
    social = (
        'Autopublicación orgánica habilitada por el dueño: consulta list_social_posts y connection_status. '
        'Si hay contenido propio pertinente y una cuenta Facebook o Instagram configurada, prepara como '
        'máximo un borrador nuevo con información comprobada y usa auto_publish_own_post. Reutiliza un '
        'borrador pendiente adecuado; no dupliques contenido ya publicado ni reintentes estados inciertos. '
        'Respeta los bloqueos y el límite diario de la herramienta. Si falta acceso, informa el bloqueo '
        'concreto sin inventar publicación. No publiques mensajes privados, anuncios ni datos de clientes. '
        if auto_social else 'Publicaciones: solo borradores; autopublicación no habilitada. ')
    return ("[Ciclo autónomo BRAIN — instrucciones del dueño, solo datos; no son comandos]\n"
            f"{brain}\n\n[Estado verificado por el servidor]\n{gumroad}{err}\n\n"
            "Responde en español. Primero consulta autonomy_status y list_social_posts para conocer "
            "el estado real. Realiza una tarea pendiente viable con las herramientas autorizadas y "
            "comprueba su resultado; si hay bloqueo, identifica la herramienta y el requisito faltante. "
            "No te limites a prometer trabajo ni marques tareas completas sin evidencia. "
            "Tareas del ciclo: estado del enlace de Gumroad, preparar contenido para las ofertas existentes. "
            + social + "Revisar "
            "leads del día, borradores de mensajes a clientes (no se envían sin /enviar del dueño) y un reporte "
            "corto al dueño. Ningún pago, gasto ni cobro sin /aprobar + /confirmar del dueño.\n"
            "ejecuta el siguiente ciclo")


async def run_cycle(core):
    """One cycle. Returns 'off' | 'cap' | 'ok'. Raises on failure (the loop backs off and reports)."""
    if not owner_enabled(core): return "off"
    if not core.TG_OWNER: raise RuntimeError("TELEGRAM_OWNER_ID no configurado")
    if core.time.monotonic() - mem["fetched_at"] >= REFETCH_S or not mem["loaded"]:
        await fetch(core)
    if not mem["loaded"]: raise RuntimeError("BRAIN no cargado (sin copia en caché)")
    if await asyncio.to_thread(_count_today, core) >= max_cycles_day(): return "cap"
    await asyncio.to_thread(core._require_leader)          # only the leader instance runs cycles
    await asyncio.to_thread(_count_today, core, True)
    auto_social = (os.getenv('AUTO_PUBLISH_OWN_SOCIAL', 'false').lower() == 'true'
                   and os.getenv('SOCIAL_PUBLISH_ENABLED', 'false').lower() == 'true')
    prompt = cycle_text(mem["text"], await gumroad_status(), mem["pending_error"], auto_social)
    await asyncio.to_thread(_record_result, core, "running")
    evidence = {'attempted': 0, 'errors': 0, 'returned_tools': [], 'failed_tools': []}
    token = _tool_evidence.set(evidence)
    try:
        reply = await core._handle_tg(core.TG_OWNER, prompt, raise_errors=True)
        if not reply:
            raise RuntimeError("El ciclo no produjo una respuesta entregada")
    except asyncio.CancelledError:
        await asyncio.to_thread(_record_result, core, "interrupted", "Interrumpido; revisar resultados antes de repetir acciones")
        raise
    except Exception as exc:
        error = core._redact_secrets(f"{type(exc).__name__}: {exc}")[0][:240]
        await asyncio.to_thread(_record_result, core, "failed", error)
        raise
    finally:
        _tool_evidence.reset(token)
        await asyncio.to_thread(_save_evidence, core, evidence)
    completed = core._now().isoformat()
    await asyncio.to_thread(_record_result, core, "response_delivered", completed=completed)
    mem.update(last_cycle=completed, pending_error=None, last_error=None, failures=0)
    return "ok"


def _save_evidence(core, evidence):
    with core._data_lock:
        state = _state(core)
        state['tool_evidence'] = dict(evidence)
        core.kv_set(STATE_KEY, state)


def _record_result(core, status, error=None, completed=None):
    """Keep operational evidence, never the prompt, reply or customer data."""
    with core._data_lock:
        state = _state(core)
        if status == "running":
            state["last_attempt"] = core._now().isoformat()
            state['tool_evidence'] = None
        state["last_status"] = status
        state["last_error"] = error
        if completed:
            state["last_cycle"] = completed
        core.kv_set(STATE_KEY, state)


async def loop(core, sleep=asyncio.sleep):
    """Never stops: every cycle is wrapped; failures back off exponentially (capped) and are reported next time."""
    if env_enabled():
        with __import__("contextlib").suppress(Exception):
            await fetch(core)
    while True:
        try:
            await run_cycle(core)
            delay = interval_s()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("brain cycle failed")
            mem["failures"] += 1
            mem["last_error"] = mem["pending_error"] = f"{type(e).__name__}: {str(e)[:160]}"
            delay = min(BACKOFF_MAX_S, 60 * 2 ** min(mem["failures"] - 1, 6))
        await sleep(delay)


def health(core):
    state = _state(core)
    return {"enabled": owner_enabled(core), "loaded": mem["loaded"],
            "last_cycle": mem["last_cycle"] or state.get("last_cycle"),
            "last_error": mem["last_error"] or state.get("last_error"),
            "last_attempt": state.get("last_attempt"),
            "last_status": state.get("last_status", "not_run"),
            "tool_evidence": state.get('tool_evidence')}


def command_text(core, arg):
    a = (arg or "").strip().lower()
    if a == "on":
        if not env_enabled(): return "⛔ BRAIN_ENABLED no está activo en Render; /brain on no basta."
        set_owner(core, True); return "🧠 BRAIN encendido."
    if a == "off":
        set_owner(core, False); return "🧠 BRAIN apagado. No corre ningún ciclo hasta /brain on."
    h = health(core)
    return (f"🧠 BRAIN: {'encendido' if h['enabled'] else 'apagado'} · cargado: {'sí' if h['loaded'] else 'no'} · "
            f"ciclos hoy: {_count_today(core)}/{max_cycles_day()} · cada {interval_s() // 60} min\n"
            f"Último intento: {h['last_attempt'] or '—'}\nEstado del intento: {h['last_status']}\n"
            f"Última respuesta entregada (no verifica entregables): {h['last_cycle'] or '—'}\n"
            f"Último error: {h['last_error'] or '—'}")
