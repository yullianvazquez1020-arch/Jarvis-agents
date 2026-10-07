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
                hist.append({"at": core._now().isoformat(timespec="seconds"), "session": str(session)[:40],
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
    core.phase_a_local = local_answer
    core.DEFAULT_PROFILE = DEFAULT_PROFILE
