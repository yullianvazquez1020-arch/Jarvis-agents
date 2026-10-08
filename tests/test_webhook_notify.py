import base64
import hashlib
import hmac
import io
import json

import jarvis_webhook_notify as hook


class _Resp:
    status = 202

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_sign_matches_standard_webhooks():
    secret = "whsec_" + base64.b64encode(b"0123456789abcdef").decode()
    body = b'{"operation":"paper"}'
    sig = hook.sign_delivery(secret, body, "msg_abc", "1700000000")
    key = base64.b64decode(secret.removeprefix("whsec_"))
    expect = base64.b64encode(
        hmac.new(key, b"msg_abc.1700000000." + body, hashlib.sha256).digest()
    ).decode()
    assert sig == "v1," + expect


def test_missing_secret_does_not_raise(monkeypatch):
    monkeypatch.delenv("JARVIS_GROK_WEBHOOK_URL", raising=False)
    monkeypatch.delenv("JARVIS_WEBHOOK_SECRET", raising=False)
    assert hook.notify_operation_done("paper", "ok") is False


def test_post_failure_does_not_raise(monkeypatch):
    monkeypatch.setenv("JARVIS_GROK_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setenv("JARVIS_WEBHOOK_SECRET", "whsec_" + base64.b64encode(b"k").decode())

    def boom(request, timeout=8):
        raise OSError("red")

    assert hook.notify_operation_done("paper", "ok", opener=boom) is False


def test_accepted_returns_true(monkeypatch):
    monkeypatch.setenv("JARVIS_GROK_WEBHOOK_URL", "https://example.invalid/hook")
    monkeypatch.setenv("JARVIS_WEBHOOK_SECRET", "whsec_" + base64.b64encode(b"k").decode())
    seen = {}

    def ok(request, timeout=8):
        seen["body"] = json.loads(request.data.decode())
        seen["sig"] = request.headers["webhook-signature"]
        return _Resp()

    assert hook.notify_operation_done("paper_cycle", "cerrado", details={"trades": 0}, opener=ok)
    assert seen["body"]["status"] == "completed"
    assert seen["sig"].startswith("v1,")
