# jarvis_phase_a.py — Fase A de Jarvis 4.2.0. No toca el money gate ni /confirmar.
# Historial cifrado, perfil de decisión, atajos locales, borrador Twilio (no envía).

from __future__ import annotations

import datetime
import os
import re

HISTORY_KEY = "jarvis:history"
PROFILE_KEY = "jarvis:profile"
DRAFTS_KEY = "jarvis:call_drafts"
HISTORY_MAX = 40

DEFAULT_PROFILE = {
    "metas": ["cash flow del canal y de la tienda", "no perder dinero"],
    "debilidades": ["gastos impulsivos"],
    "fortalezas": ["construye Jarvis y cierra ventas"],
    "techo_usd": 100,
    "beneficio": "proponer solo lo que deja al dueño mejor de lo que está",
}


def _norm(text):
    import unicodedata
    t = unicodedata.normalize("NFKD", str(text or "").lower())
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = re.sub(r"[¿?¡!.,;:]+", " ", t)
    t = re.sub(r"^\s*(oye\s+)?jarvis\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


PERFIL_RX = re.compile(r"/?perfil|(muestrame |ensename |dame |cual es )?mi perfil")
CASH_RX = re.compile(r"(como (va|esta|anda) (mi |el )?)?(cash ?flow|flujo de (caja|efectivo))( del negocio)?( hoy)?")
CALL_RX = re.compile(r"/?llam(ar|a|ale|alo|ala)\b")
NOT_A_CALL_RX = re.compile(r"\b(recuerd\w*|recordatorio|agenda\w*|anota\w*|apunta\w*|manana|hoy|a las|el lunes|"
                           r"el martes|el miercoles|el jueves|el viernes|el sabado|el domingo)\b")


def smalltalk(text, now):
    """Exact, stateless answers only: never consume an action or infer approval."""
    t = _norm(text)
    t = re.sub(r"\s+jarvis$", "", t).strip()
    t = re.sub(r"^(hola|buenos dias|buenas tardes|buenas noches) jarvis(?= como estas$)", r"\1", t)
    if re.fullmatch(r"(hola|buenos dias|buenas tardes|buenas noches)( como estas)?|como estas", t):
        return "Hola. Estoy aquí para ayudarte. Dime qué necesitas."
    if t in ("gracias", "muchas gracias", "mil gracias"):
        return "Con gusto."
    if t in ("adios", "hasta luego", "hasta manana"):
        return "Hasta luego. Aquí estaré cuando me necesites."
    if t in ("que hora es", "dime la hora", "hora"):
        return f"Son las {now.strftime('%H:%M')} en Puerto Rico."
    if t in ("que dia es hoy", "que fecha es hoy", "dime la fecha", "fecha de hoy"):
        return f"Hoy es {now.strftime('%d/%m/%Y')} en Puerto Rico."
    if t in ("que puedes hacer", "como te uso"):
        return ("Puedes consultar /hoy, /clientes, /trabajos, /inventario, /cobros y /banco semana. "
                "Envía /ayuda para ver los comandos. Las acciones por voz requieren revisar el dictado; "
                "el dinero conserva sus aprobaciones.")
    return None


def install(core):
    from fastapi import Header, HTTPException

    @core.app.get("/fase-a")
    async def fase_a(x_api_key: str = Header(...)):
        if not core._key_ok(x_api_key, core.API_KEY):
            raise HTTPException(401, "Bad API key")
        prof = core.kv_get(PROFILE_KEY, DEFAULT_PROFILE)
        hist = core.kv_get(HISTORY_KEY, [])
        return {
            "version": core.VERSION,
            "perfil": prof if isinstance(prof, dict) else DEFAULT_PROFILE,
            "historial": len(hist) if isinstance(hist, list) else 0,
            "twilio": bool(os.getenv("TWILIO_AUTH_TOKEN", "").strip()),
            "nota": "los borradores no se envían; hace falta /enviar",
        }

    def remember(session, role, text):
        clean, _ = core._redact_secrets(str(text or "")[:2000])
        try:
            with core._data_lock:
                hist = core.kv_get(HISTORY_KEY, [])
                if not isinstance(hist, list):
                    hist = []
                hist.append({"at": core._now().isoformat(timespec="seconds"), "session": str(session)[:128],
                             "role": role, "text": clean})
                core.kv_set(HISTORY_KEY, hist[-HISTORY_MAX:])
        except Exception:
            return

    def local_answer(text):
        """Atajos sin tokens. Revisado: solo responden si TODO el mensaje es esa pregunta, para no secuestrar
        pedidos normales ('anota 50 de cash para gasolina' debe llegar a la IA y quedar anotado)."""
        t = _norm(text)
        if PERFIL_RX.fullmatch(t):
            p = core.kv_get(PROFILE_KEY, DEFAULT_PROFILE)
            if not isinstance(p, dict):
                p = DEFAULT_PROFILE
            return ("Perfil: metas " + "; ".join(p.get("metas", []))
                    + f". Techo ${p.get('techo_usd', 100)}. Nada se ejecuta solo.")
        if CASH_RX.fullmatch(t):
            return "Cash flow: revisa /banco semana y /cobros. Si falta para un gasto, te aviso. No muevo dinero."
        if CALL_RX.match(t) and not NOT_A_CALL_RX.search(t):
            return "La llamada no está cableada a /enviar. No marqué ni guardé un borrador."
        return None

    core.phase_a_remember = remember
    def remember_turn(session, user_text, reply):
        """One atomic storage write: never leave half of a newly saved turn."""
        session = str(session)
        if len(session) > 128:
            return
        at = core._now().isoformat(timespec="seconds")
        rows = [{"at": at, "session": session, "role": role,
                 "text": core._redact_secrets(str(text or ""))[0][:2000]}
                for role, text in (("user", user_text), ("assistant", reply))]
        with core._data_lock:
            hist = core.kv_get(HISTORY_KEY, [])
            if not isinstance(hist, list):
                hist = []
            core.kv_set(HISTORY_KEY, (hist + rows)[-HISTORY_MAX:])

    core.phase_a_remember_turn = remember_turn
    def restore(session):
        """Restore complete plain-text turns only, never tools or unfinished requests."""
        session = str(session)
        if len(session) > 128:
            return []
        with core._data_lock:
            hist = core.kv_get(HISTORY_KEY, [])
        if not isinstance(hist, list):
            return []
        turns = []
        pending = None
        for row in hist[-HISTORY_MAX:]:
            if not isinstance(row, dict) or row.get("session") != session:
                continue
            text = row.get("text")
            if not isinstance(text, str) or not text.strip():
                continue
            text = core._redact_secrets(text[:2000])[0]
            if row.get("role") == "user":
                pending = {"role": "user", "content": text}
            elif row.get("role") == "assistant" and pending is not None:
                turns.extend([pending, {"role": "assistant", "content": text}])
                pending = None
        return turns[-20:]

    core.phase_a_restore = restore
    core.phase_a_local = local_answer
    core.phase_a_smalltalk = lambda text: smalltalk(text, core._now())
    core.DEFAULT_PROFILE = DEFAULT_PROFILE
