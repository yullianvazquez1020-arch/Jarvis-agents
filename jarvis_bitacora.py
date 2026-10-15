"""Bitácora compartida Friday <-> Jarvis.

Anillo persistente (últimas MAX entradas) en el KV de Jarvis (Redis si está configurado, si no archivo local).
Guarda los mensajes que Jarvis envía por Telegram y las notas de trabajo que Friday (Grok Bot) publica.
Llave sellada (cifrada) en jarvis_seal. Solo lectura/registro: no ejecuta acciones.
"""
import threading

KEY = "jarvis:bitacora"
MAX = 500
MAX_TEXTO = 4000
KINDS = ("telegram", "documento", "friday")
_lock = threading.Lock()
_kv_get = None
_kv_set = None
_now = None
_redact = lambda t: t


def configurar(kv_get, kv_set, now, redact=None):
    global _kv_get, _kv_set, _now, _redact
    _kv_get, _kv_set, _now = kv_get, kv_set, now
    if redact:
        _redact = redact


def _cargar():
    data = _kv_get(KEY, []) if _kv_get else []
    return data if isinstance(data, list) else []


def registrar(kind, text, chat=None, fuente="jarvis"):
    if kind not in KINDS:
        raise ValueError("tipo inválido")
    text = _redact(str(text or "").strip())[:MAX_TEXTO]
    if not text:
        raise ValueError("texto vacío")
    with _lock:
        rows = _cargar()
        seq = (rows[-1].get("seq", 0) if rows else 0) + 1
        row = {"seq": seq, "ts": _now().isoformat(timespec="seconds"), "chat": None if chat is None else str(chat),
               "kind": kind, "fuente": fuente, "text": text}
        rows = (rows + [row])[-MAX:]
        _kv_set(KEY, rows)
    return row


def registrar_seguro(kind, text, chat=None, fuente="jarvis"):
    """Nunca rompe un envío: si el registro falla, se ignora."""
    try:
        return registrar(kind, text, chat, fuente)
    except Exception:
        return None


def leer(limit=10, fuente=None):
    try:
        limit = max(1, min(int(limit), MAX))
    except (TypeError, ValueError):
        limit = 10
    rows = _cargar()
    if fuente:
        rows = [r for r in rows if r.get("fuente") == fuente]
    return rows[-limit:]   # orden cronológico, el más nuevo al final
