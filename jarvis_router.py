"""Jarvis · enrutador de modelos de SOLO TEXTO (librería estándar, sin dependencias).

Qué hace
- Texto sensible (clientes, facturas, teléfonos, correos, direcciones, credenciales) -> SOLO Ollama local.
  Si Ollama no responde: RouterError. Nunca se envía a la nube.
- Tareas simples -> Ollama local; si falla, APIs compatibles con OpenAI en el orden de JARVIS_API_ORDER.
- Tareas complejas -> APIs (DeepSeek, Qwen DashScope intl., Kimi); si todas fallan, Ollama como último recurso.

Qué NO hace
- No ejecuta herramientas ni acciones. Devuelve texto y nada más: pagos, mensajes, /confirmar y aprobaciones
  siguen pasando por los controles de Jarvis. Se activa solo con JARVIS_ROUTER_ENABLED=1 (lo decide el dueño).

Secretos
- Claves solo por variables de entorno (DEEPSEEK_API_KEY, DASHSCOPE_API_KEY, MOONSHOT_API_KEY).
- Los logs y errores llevan nombres de backend, tipos de error y nombres de variables; nunca claves ni prompts.
- No sigue redirecciones (una redirección podría reenviar la cabecera Authorization a otro host).
- Ollama tiene que estar en loopback (127.0.0.1, localhost o ::1) y se llama sin proxy.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urlsplit

log = logging.getLogger("jarvis.router")

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_LOCAL_MODEL = "qwen3:4b-instruct"
DEFAULT_ORDER = "deepseek,qwen,kimi"
MAX_RESPONSE_BYTES = 2_000_000
MAX_PROMPT_CHARS = 60_000


@dataclass(frozen=True)
class Provider:
    name: str
    base_url: str
    model: str
    key_env: str


# Fixed endpoints (requirement 3). The model names can be configured; the URLs cannot.
BASE_URLS = {
    "deepseek": "https://api.deepseek.com",
    "qwen": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    "kimi": "https://api.moonshot.ai/v1",
}
_MODEL_ENV = {
    "deepseek": ("DEEPSEEK_MODEL", "deepseek-flash"),
    "qwen": ("QWEN_MODEL", "qwen-flash"),
    "kimi": ("KIMI_MODEL", "kimi-k2-0711-preview"),  # confirm the exact name with Moonshot before enabling
}
_KEY_ENV = {"deepseek": "DEEPSEEK_API_KEY", "qwen": "DASHSCOPE_API_KEY", "kimi": "MOONSHOT_API_KEY"}

SENSITIVE = re.compile(
    r"("
    r"\bclientes?\b|\bcustomers?\b|\bclients?\b|factura|invoice|recibo|receipt|tarjeta|card number|"
    r"cuenta bancaria|bank account|n[uú]mero de cuenta|account number|routing|\biban\b|\bswift\b|"
    r"\bssn\b|seguro social|social security|direcci[oó]n|\baddress\b|\bcalle\b|\bavenida\b|\burb\.?\s|"
    r"tel[eé]fono|\bphone\b|celular|\bm[oó]vil\b|correo|e-?mail|"
    r"contrase[nñ]a|password|passcode|\bclave\b|\btoken\b|secret|api[ _-]?key|credencial|credential|"
    r"\bpin\b|\botp\b|c[oó]digo de verificaci[oó]n|verification code|"
    r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+|"                                  # email address
    r"(?<!\d)(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)|"  # NANP phone (PR 787/939)
    r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)|"                               # SSN shape
    r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)|"                            # card or account number
    r"\bsk-[A-Za-z0-9_-]{8,}|\b[A-Za-z0-9_\-]{32,}\b"                # key-looking strings
    r")",
    re.I,
)
COMPLEX = re.compile(
    r"(c[oó]digo|\bcode\b|programa|script|analiza|an[aá]lisis|analy[sz]e|\bplan\b|estrategia|strategy|"
    r"resume este documento|resumen|summari[sz]e|traduce|translate|refactor|investiga|research|compara)",
    re.I,
)


class RouterError(RuntimeError):
    """Router failure. Its message never includes keys or the prompt."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        return None  # urllib turns this into an HTTPError: do not follow


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def _env_float(name: str, default: float, low: float, high: float) -> float:
    try:
        return min(high, max(low, float(_env(name, str(default)))))
    except ValueError:
        return default


def enabled() -> bool:
    """JARVIS_ROUTER_ENABLED defaults to 0. Only 1, true, yes or on turn it on."""
    return _env("JARVIS_ROUTER_ENABLED", "0").lower() in ("1", "true", "yes", "on")


def ollama_url() -> str:
    return _env("OLLAMA_URL", DEFAULT_OLLAMA_URL).rstrip("/")


def local_model() -> str:
    return _env("JARVIS_LOCAL_MODEL", DEFAULT_LOCAL_MODEL)


def provider(name: str) -> Provider:
    if name not in BASE_URLS:
        raise RouterError(f"Backend desconocido: {name}")
    env, default = _MODEL_ENV[name]
    return Provider(name, BASE_URLS[name], _env(env, default), _KEY_ENV[name])


def api_order() -> list[str]:
    out = []
    for name in _env("JARVIS_API_ORDER", DEFAULT_ORDER).lower().split(","):
        name = name.strip()
        if not name:
            continue
        if name not in BASE_URLS:
            log.warning("router: JARVIS_API_ORDER ignora un nombre desconocido")
            continue
        if name not in out:
            out.append(name)
    return out


def status() -> dict:
    """Safe for diagnostics: only booleans and names, never values."""
    return {
        "enabled": enabled(),
        "local_model": local_model(),
        "api_order": api_order(),
        "keys_present": {n: bool(_env(_KEY_ENV[n])) for n in BASE_URLS},
    }


def is_sensitive(text: str | None) -> bool:
    return bool(text) and bool(SENSITIVE.search(text))


def classify(text: str) -> str:
    if is_sensitive(text):
        return "local"
    if len(text) > 1500 or COMPLEX.search(text):
        return "api"
    return "local"


def _is_loopback(url: str) -> bool:
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme not in ("http", "https") or not host:
        return False
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _post(url: str, payload: dict, headers: dict, timeout: float, *, use_proxy: bool) -> dict:
    handlers = [_NoRedirect()]
    if not use_proxy:
        handlers.append(urllib.request.ProxyHandler({}))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json", **headers}, method="POST")
    with opener.open(req, timeout=timeout) as r:
        raw = r.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise RouterError("Respuesta demasiado grande")
    return json.loads(raw.decode("utf-8"))


_THINK = re.compile(r"<think>.*?</think>\s*", re.S | re.I)


def _clean(text) -> str:
    if not isinstance(text, str):
        raise RouterError("Respuesta sin texto")
    text = _THINK.sub("", text).strip()
    if not text:
        raise RouterError("Respuesta vacía")
    return text


def ask_ollama(messages: list, max_tokens: int | None = None, timeout: float | None = None) -> tuple[str, int]:
    url = ollama_url()
    if not _is_loopback(url):
        raise RouterError("OLLAMA_URL debe apuntar a esta máquina (127.0.0.1, localhost o ::1)")
    payload = {"model": local_model(), "messages": messages, "stream": False}
    if max_tokens:
        payload["options"] = {"num_predict": int(max_tokens)}
    data = _post(f"{url}/api/chat", payload, {},
                 timeout or _env_float("JARVIS_LOCAL_TIMEOUT", 120, 5, 600), use_proxy=False)
    tokens = int(data.get("prompt_eval_count") or 0) + int(data.get("eval_count") or 0)
    return _clean((data.get("message") or {}).get("content")), tokens


def ask_api(name: str, messages: list, max_tokens: int | None = None, timeout: float | None = None) -> tuple[str, int]:
    p = provider(name)
    key = _env(p.key_env)
    if not key:
        raise RouterError(f"{name}: falta la variable {p.key_env}")
    payload = {"model": p.model, "messages": messages, "stream": False}
    if max_tokens:
        payload["max_tokens"] = int(max_tokens)
    data = _post(f"{p.base_url}/chat/completions", payload, {"Authorization": f"Bearer {key}"},
                 timeout or _env_float("JARVIS_API_TIMEOUT", 60, 5, 300), use_proxy=True)
    choices = data.get("choices") or []
    if not choices:
        raise RouterError(f"{name}: respuesta sin opciones")
    tokens = int((data.get("usage") or {}).get("total_tokens") or 0)
    return _clean((choices[0].get("message") or {}).get("content")), tokens


def _why(exc: BaseException) -> str:
    """Short reason with no response body, no URL and no key."""
    if isinstance(exc, urllib.error.HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, RouterError):
        return str(exc)
    return type(exc).__name__


def route(prompt: str, system: str | None = None, force: str | None = None,
          max_tokens: int | None = None) -> dict:
    """Return {'text', 'backend', 'tokens'}. Text only: the caller decides what to do with it."""
    if not isinstance(prompt, str) or not prompt.strip():
        raise RouterError("Prompt vacío")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise RouterError("Prompt demasiado largo")
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": prompt}]
    sensitive = is_sensitive(prompt) or is_sensitive(system)
    target = "local" if sensitive else (force if force in ("local", "api") else classify(prompt))
    failures: list[str] = []

    def local():
        text, tokens = ask_ollama(messages, max_tokens)
        return {"text": text, "backend": f"ollama:{local_model()}", "tokens": tokens}

    if target == "local":
        try:
            return local()
        except Exception as e:  # noqa: BLE001 - every failure gets the same treatment
            log.warning("router: ollama falló (%s)", type(e).__name__)
            if sensitive:
                raise RouterError("Datos sensibles y Ollama no responde; no se envían a APIs externas.") from None
            failures.append(f"ollama:{_why(e)}")
    for name in api_order():
        try:
            text, tokens = ask_api(name, messages, max_tokens)
            return {"text": text, "backend": f"{name}:{provider(name).model}", "tokens": tokens}
        except Exception as e:  # noqa: BLE001
            log.warning("router: %s falló (%s)", name, type(e).__name__)
            failures.append(f"{name}:{_why(e)}")
    if target == "api":
        try:
            return local()
        except Exception as e:  # noqa: BLE001
            log.warning("router: ollama falló (%s)", type(e).__name__)
            failures.append(f"ollama:{_why(e)}")
    raise RouterError("Ningún backend disponible: " + "; ".join(failures))


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    try:
        out = route(" ".join(sys.argv[1:]) or "Di hola en una frase.")
        print(f"[{out['backend']}] {out['text']}")
    except RouterError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
