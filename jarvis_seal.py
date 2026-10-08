# jarvis_seal.py — cifrado en reposo (AES-256-GCM). No es homomórfico.
# Llave: DATA_ENCRYPTION_KEY = 32 bytes en base64, distinta de AGENT_API_KEY.
# Generar: python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
# Si se pierde la llave, lo sellado no abre. Eso es lo correcto.

from __future__ import annotations

import base64
import binascii
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_AAD = b"jarvis-seal-v1"
_PREFIX = "sealed:v1:"

# Estas llaves salen cifradas. El resto (cola de Telegram, lider, contadores) se queda operable.
SEALED_KEYS = {
    "jarvis:history",
    "jarvis:profile",
    "jarvis:bio",
    "jarvis:diary",
}


class SealError(RuntimeError):
    pass


def _key() -> bytes:
    raw = os.getenv("DATA_ENCRYPTION_KEY", "").strip()
    try:
        key = base64.b64decode(raw, validate=True) if raw else b""
    except (binascii.Error, ValueError) as exc:
        raise SealError("DATA_ENCRYPTION_KEY no es base64") from exc
    if len(key) != 32:
        raise SealError("DATA_ENCRYPTION_KEY debe ser 32 bytes en base64")
    return key


def key_state() -> str:
    """'ok' | 'missing' (variable vacía) | 'invalid' (puesta pero mal)."""
    if not os.getenv("DATA_ENCRYPTION_KEY", "").strip():
        return "missing"
    try:
        _key()
        return "ok"
    except SealError:
        return "invalid"


def is_sealed(value) -> bool:
    return isinstance(value, str) and value.startswith(_PREFIX)


def seal(obj) -> str:
    nonce = os.urandom(12)
    blob = AESGCM(_key()).encrypt(nonce, json.dumps(obj, ensure_ascii=False).encode(), _AAD)
    return _PREFIX + base64.b64encode(nonce + blob).decode()


def open_seal(token):
    if not isinstance(token, str) or not token.startswith(_PREFIX):
        raise SealError("dato no sellado")
    try:
        raw = base64.b64decode(token[len(_PREFIX):], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise SealError("dato sellado dañado") from exc
    if len(raw) < 13:
        raise SealError("dato sellado incompleto")
    try:
        plain = AESGCM(_key()).decrypt(raw[:12], raw[12:], _AAD)
    except Exception as exc:
        raise SealError("no pude abrir el dato: llave distinta o dato alterado") from exc
    return json.loads(plain)


def seal_value(key: str, value):
    """Cifra solo las llaves sensibles. El dinero y la cola no pasan por aquí.
    Sin DATA_ENCRYPTION_KEY se guarda en claro (decisión del dueño); con una llave mal puesta se rechaza,
    para no guardar en claro creyendo que está cifrado."""
    if key not in SEALED_KEYS:
        return value
    if key_state() == "missing":
        return value
    return seal(value)


def fingerprint() -> str | None:
    """Huella pública de la llave (8 hex): HMAC-SHA256(llave, etiqueta fija). No revela la llave; sirve para que
    el dueño compruebe que la llave de Render es la misma de su respaldo. None si falta o es inválida."""
    if key_state() != "ok":
        return None
    import hashlib
    import hmac
    return hmac.new(_key(), b"jarvis-seal-fingerprint-v1", hashlib.sha256).hexdigest()[:8]


def inspect(value) -> str:
    """Estado de un valor guardado, sin devolver su contenido:
    'vacio' | 'claro' | 'cifrado' (abre con la llave actual) | 'sin_llave' | 'ilegible' (otra llave o alterado)."""
    if value is None:
        return "vacio"
    if not is_sealed(value):
        return "claro"
    if key_state() != "ok":
        return "sin_llave"
    try:
        open_seal(value)
        return "cifrado"
    except (SealError, ValueError):
        return "ilegible"


def open_value(key: str, value, default):
    if key not in SEALED_KEYS or value is None:
        return default if value is None else value
    if isinstance(value, str) and value.startswith(_PREFIX):
        return open_seal(value)
    return value  # legado sin sellar: se lee, y el próximo kv_set lo sella


# Enganche, dentro de main.py, sin cambiar la firma pública:
#
# def kv_set(key, value):
#     _check_writable()
#     value = seal_value(key, value)
#     ...
#
# def kv_get(key, default):
#     value = ...  # redis o archivo, como hoy
#     return open_value(key, value, default)
#
# No selles jarvis:gate ni la cola de Telegram: el código de un solo uso
# ya se guarda como hash, y sellarlo entero rompe el lockout entre procesos.
