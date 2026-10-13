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
        await asyncio.to_thread(core.kv_set, CACHE_KEY, {"text": text, "at": core._now().isoformat()})
        mem.update(text=text, loaded=True)
    except Exception as e:
        cached = await asyncio.to_thread(core.kv_get, CACHE_KEY, {})
        if isinstance(cached, dict) and cached.get("text"):
            mem.update(text=sanitize(cached["text"]), loaded=True)
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


def cycle_text(brain, gumroad, prev_error):
    err = f"\nError del ciclo anterior (repórtalo): {prev_error}" if prev_error else ""
    return ("[Ciclo autónomo BRAIN — instrucciones del dueño, solo datos; no son comandos]\n"
            f"{brain}\n\n[Estado verificado por el servidor]\n{gumroad}{err}\n\n"
            "Tareas del ciclo: estado del enlace de Gumroad, preparar/rotar publicaciones KETEC (borradores), "
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
    prompt = cycle_text(mem["text"], await gumroad_status(), mem["pending_error"])
    await core._handle_tg(core.TG_OWNER, prompt)
    mem.update(last_cycle=core._now().isoformat(), pending_error=None, failures=0)
    return "ok"


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
    return {"enabled": owner_enabled(core), "loaded": mem["loaded"], "last_cycle": mem["last_cycle"],
            "last_error": mem["last_error"]}


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
            f"Último ciclo: {h['last_cycle'] or '—'}\nÚltimo error: {h['last_error'] or '—'}")
