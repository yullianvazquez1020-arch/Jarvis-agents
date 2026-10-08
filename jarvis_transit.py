# jarvis_transit.py — cifrado en tránsito = TLS. No cifra el cuerpo a mano.
# Render termina HTTPS. Esto impide que la app hable en claro si alguien se salta el proxy.
#
# 4.1.0 revisado:
#  * Middleware ASGI puro (no BaseHTTPMiddleware): no envuelve la respuesta en otra tarea, así las tareas en
#    segundo plano del webhook de Telegram corren igual que antes.
#  * Solo se rechaza el tráfico que el proxy de Render marca como HTTP (X-Forwarded-Proto: http). Una petición
#    sin esa cabecera no pasó por el proxy público: es el chequeo de salud de Render o una prueba local.
#  * /health y / (GET y HEAD) nunca se rechazan por el host: Render manda su chequeo de salud con el Host de
#    onrender.com o del dominio propio, y si falla 15 minutos cancela el deploy; si falla 60 s reinicia.

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

PUBLIC_HOST = os.getenv("PUBLIC_HOST", "").strip().lower()  # ej. jarvis-agents.onrender.com
HEALTH_PATHS = ("/health", "/")
_SECURITY_HEADERS = [
    (b"strict-transport-security", b"max-age=31536000; includeSubDomains"),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"no-referrer"),
]


def _local(host: str) -> bool:
    host = (host or "").split(":")[0].lower()
    return host in ("127.0.0.1", "localhost", "::1")


def _headers(scope) -> dict:
    out = {}
    for k, v in scope.get("headers") or []:
        out.setdefault(k.decode("latin-1").lower(), v.decode("latin-1"))
    return out


def decide(method: str, path: str, host: str, forwarded_proto: str, public_host: str = None) -> str:
    """'' = pasa; si no, el motivo del 400. Función pura para poder probarla."""
    public_host = PUBLIC_HOST if public_host is None else public_host
    if _local(host):
        return ""
    proto = (forwarded_proto or "").split(",")[0].strip().lower()
    if proto and proto != "https":
        return "HTTPS obligatorio"
    is_health = method in ("GET", "HEAD") and path in HEALTH_PATHS
    if public_host and not is_health and (host or "").split(":")[0].lower() != public_host:
        return "host no permitido"
    return ""


class TransitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        h = _headers(scope)
        host = h.get("host", "")
        why = decide(scope.get("method", "GET"), scope.get("path", ""), host, h.get("x-forwarded-proto", ""))
        if why:
            body = json.dumps({"error": why}).encode()
            await send({"type": "http.response.start", "status": 400,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode())]})
            await send({"type": "http.response.body", "body": body})
            return
        if _local(host):
            return await self.app(scope, receive, send)

        async def send_with_headers(message):
            if message.get("type") == "http.response.start":
                have = {k.lower() for k, _ in message.get("headers") or []}
                message = dict(message, headers=list(message.get("headers") or [])
                               + [(k, v) for k, v in _SECURITY_HEADERS if k not in have])
            await send(message)

        return await self.app(scope, receive, send_with_headers)


def install_transit(app) -> None:
    app.add_middleware(TransitMiddleware)


def webhook_url() -> str:
    """URL única del webhook. Telegram no entrega por HTTP."""
    if not PUBLIC_HOST:
        raise RuntimeError("Falta PUBLIC_HOST")
    return f"https://{PUBLIC_HOST}/telegram"


def url_es_https(url: str) -> str:
    """'' si sirve; si no, el motivo. Misma regla que los agentes externos."""
    u = urlsplit(url or "")
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        return "solo https://host/ruta, sin usuario ni clave en la URL"
    return ""


def mount_gemini_if_ready() -> None:
    """Attach the reviewer to the current process. Never change uvicorn main:app for this."""
    import sys
    core = sys.modules.get("main")
    if core is None or not hasattr(core, "app"):
        return
    try:
        import jarvis_gemini_boot
        jarvis_gemini_boot.mount(core)
    except Exception as exc:
        core.GEMINI_STATUS = f"apagado ({type(exc).__name__})"


mount_gemini_if_ready()
