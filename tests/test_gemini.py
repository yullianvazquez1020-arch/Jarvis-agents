import datetime
import json
import os
import secrets
import types
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import jarvis_gemini as gemini


class GeminiReview(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "GEMINI_ENABLED": "true", "GEMINI_API_KEY": "fake-provider-credential",
            "GEMINI_MODEL": "gemini-test", "GEMINI_REVIEW_ACCESS_KEY": "test-review-" + "x" * 32,
        })
        self.env.start()
        self.addCleanup(self.env.stop)
        self.claims = set()
        self.requests = []
        self.reply = {"candidates": [{"finishReason": "STOP", "content": {
            "parts": [{"text": "Revisión de ejemplo"}]}}]}
        self.code = 200
        self.core = types.SimpleNamespace(
            app=FastAPI(), API_KEY="fake-master", _SECRET_ENVS=(),
            _key_ok=lambda a, b: secrets.compare_digest(a, b),
            _today=lambda: datetime.date(2026, 10, 8), _claim=self.claim,
            _redact_secrets=self.redact,
        )
        gemini.install(self.core)
        self.client = TestClient(self.core.app)
        self.headers = {"x-api-key": os.environ["GEMINI_REVIEW_ACCESS_KEY"]}
        real_client = httpx.AsyncClient
        self.factory = patch.object(gemini.httpx, "AsyncClient", side_effect=lambda **kw:
                                    real_client(transport=httpx.MockTransport(self.provider), **kw))
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def claim(self, key, ttl):
        if key in self.claims:
            return False
        self.claims.add(key)
        return True

    def redact(self, text):
        found = []
        for name in self.core._SECRET_ENVS:
            secret = os.getenv(name, "")
            if secret and secret in text:
                text = text.replace(secret, "[OMITIDO]")
                found.append(name)
        return text, found

    def provider(self, request):
        self.requests.append(request)
        return httpx.Response(self.code, json=self.reply)

    def post(self, text="Revisa este texto público"):
        return self.client.post("/gemini/review", headers=self.headers, json={"text": text})

    def test_auth_before_network(self):
        for headers in ({}, {"x-api-key": self.core.API_KEY}):
            self.assertEqual(self.client.post("/gemini/review", headers=headers,
                             json={"text": "hola"}).status_code, 401)
        self.assertEqual(self.requests, [])

    def test_off_without_network(self):
        os.environ["GEMINI_ENABLED"] = "false"
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(self.requests, [])

    def test_missing_or_unsafe_model(self):
        for model in ("", "gemini-test/../../other?key=x"):
            os.environ["GEMINI_MODEL"] = model
            self.assertEqual(self.post().status_code, 503)
        self.assertEqual(self.requests, [])

    def test_known_secrets_rejected(self):
        for name in ("GEMINI_API_KEY", "GEMINI_REVIEW_ACCESS_KEY"):
            self.assertEqual(self.post(os.environ[name]).status_code, 400)
        self.assertEqual(self.requests, [])

    def test_review_has_no_tools_or_history(self):
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["executed"])
        request = self.requests[0]
        self.assertEqual(request.url.host, "generativelanguage.googleapis.com")
        self.assertEqual(request.url.query, b"")
        data = json.loads(request.content)
        self.assertNotIn("tools", data)
        self.assertEqual(len(data["contents"]), 1)
        self.assertNotIn(self.core.API_KEY, str(request.headers))

    def test_daily_limit(self):
        for _ in range(8):
            self.assertEqual(self.post().status_code, 200)
        self.assertEqual(self.post().status_code, 429)
        self.assertEqual(len(self.requests), 8)

    def test_provider_error_not_leaked_or_retried(self):
        self.code = 429
        self.reply = {"error": os.environ["GEMINI_API_KEY"]}
        response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn(os.environ["GEMINI_API_KEY"], response.text)
        self.assertEqual(len(self.requests), 1)

    def test_output_redacted_and_blocked_handled(self):
        self.reply["candidates"][0]["content"]["parts"][0]["text"] = os.environ["GEMINI_API_KEY"]
        self.assertEqual(self.post().json()["text"], "[OMITIDO]")
        self.reply = {"promptFeedback": {"blockReason": "SAFETY"}}
        self.assertEqual(self.post().status_code, 502)

    def test_status_does_not_claim_live_connection(self):
        response = self.client.get("/gemini/status", headers=self.headers)
        self.assertTrue(response.json()["configured"])
        self.assertFalse(response.json()["connection_verified"])
        self.assertEqual(self.requests, [])

    def test_input_and_output_limits(self):
        self.assertEqual(self.post("a" * 8001).status_code, 422)
        self.reply = {"padding": "a" * 66000}
        self.assertEqual(self.post().status_code, 502)

    def test_master_key_cannot_be_reused(self):
        self.core.API_KEY = os.environ["GEMINI_REVIEW_ACCESS_KEY"]
        self.assertEqual(self.post().status_code, 503)
        self.assertEqual(self.requests, [])

    def test_oversized_response_never_grows_buffer_past_limit(self):
        buffers = []

        class TrackedBuffer(bytearray):
            def __init__(self):
                super().__init__()
                self.peak = 0
                buffers.append(self)

            def extend(self, data):
                super().extend(data)
                self.peak = max(self.peak, len(self))

        self.reply = {"padding": "x" * (1024 * 1024)}
        with patch.object(gemini, "bytearray", TrackedBuffer, create=True):
            response = self.post()
        self.assertEqual(response.status_code, 502)
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(len(self.claims), 1)
        self.assertEqual(len(buffers), 1)
        self.assertLessEqual(buffers[0].peak, 65536)

    def test_encryption_key_cannot_be_reused(self):
        with patch.dict(os.environ, {"DATA_ENCRYPTION_KEY": os.environ["GEMINI_REVIEW_ACCESS_KEY"]}):
            self.assertEqual(self.post().status_code, 503)
        self.assertEqual(self.requests, [])


class GeminiStartup(unittest.TestCase):
    def test_main_entrypoint_preserves_jarvis(self):
        self.check_entrypoint(False)

    def test_transit_preimport_preserves_gemini_routes(self):
        self.check_entrypoint(True)

    def check_entrypoint(self, preimport_transit):
        import subprocess
        import sys
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as data:
            env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "SSL_CERT_FILE")}
            env.update(AGENT_API_KEY="deployment-local-test", ANTHROPIC_API_KEY="",
                       DATA_DIR=data, PYTHON_DOTENV_DISABLED="1", SCHEDULER_ENABLED="false",
                       GEMINI_ENABLED="false", GEMINI_API_KEY="fake-provider-secret",
                       GEMINI_REVIEW_ACCESS_KEY="x" * 40, CRYPTO_PRACTICE_ONLY="true",
                       COINBASE_TRADING_ENABLED="false")
            script = '''
from fastapi.testclient import TestClient
from unittest.mock import patch
import main as core
paths = [route.path for route in core.app.routes]
assert paths.count('/gemini/status') == paths.count('/gemini/review') == 1
with TestClient(core.app) as c, patch('httpx.AsyncClient', side_effect=AssertionError('outbound network attempted')) as outbound:
    assert c.get('/health').status_code == 200
    s = c.get('/gemini/status', headers={'x-api-key': 'x'*40})
    assert s.status_code == 200 and s.json()['enabled'] is False
    assert s.json()['connection_verified'] is False
    assert c.post('/gemini/review', headers={'x-api-key': 'x'*40}, json={'text':'hola'}).status_code == 503
    assert c.get('/backup', headers={'x-api-key': 'x'*40}).status_code == 401
    assert core.MONEY_MAX_ORDER <= 100 and core.MONEY_MAX_DAY <= 300
    assert 'fake-provider-secret' not in core._redact_secrets('fake-provider-secret')[0]
    assert outbound.call_count == 0
'''
            if preimport_transit:
                script = 'import jarvis_transit\n' + script
            result = subprocess.run([sys.executable, "-c", script],
                                    cwd=Path(__file__).resolve().parents[1], env=env,
                                    capture_output=True, text=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
