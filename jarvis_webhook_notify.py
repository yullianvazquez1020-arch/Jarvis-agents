"""Aviso a Grok cuando una operación del monitor termina.

Firma Standard Webhooks (la que verifica Grok). Un fallo del POST no tumba el worker.
URL y secreto salen de la automatización jarvis-operacion-terminada; no van en el repo.
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.request
import uuid
from datetime import datetime, timezone

log = logging.getLogger("jarvis.webhook_notify")
STATUSES = {"completed", "failed", "cancelled"}


def _payload(operation_name, result, status, details):
    if status not in STATUSES:
        status = "failed"
    body = {
        "operation": str(operation_name),
        "status": status,
        "result": str(result),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if details:
        body["details"] = details
    return body


def sign_delivery(secret, body, webhook_id, timestamp):
    key = base64.b64decode(secret.removeprefix("whsec_"))
    signed = f"{webhook_id}.{timestamp}.".encode() + body
    digest = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    return f"v1,{digest}"


def notify_operation_done(operation_name, result, status="completed", details=None, opener=None):
    url = (os.environ.get("JARVIS_GROK_WEBHOOK_URL") or "").strip()
    secret = (os.environ.get("JARVIS_WEBHOOK_SECRET") or "").strip()
    if not url or not secret:
        log.info("webhook grok apagado: faltan URL o secreto")
        return False
    raw = json.dumps(
        _payload(operation_name, result, status, details),
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    webhook_id = "msg_" + uuid.uuid4().hex
    timestamp = str(int(time.time()))
    request = urllib.request.Request(
        url,
        data=raw,
        headers={
            "content-type": "application/json",
            "webhook-id": webhook_id,
            "webhook-timestamp": timestamp,
            "webhook-signature": sign_delivery(secret, raw, webhook_id, timestamp),
        },
        method="POST",
    )
    try:
        send = opener or urllib.request.urlopen
        with send(request, timeout=8) as response:
            return response.status in (200, 202)
    except Exception:
        log.exception("webhook grok no salió; la operación sigue")
        return False
