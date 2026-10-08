"""Boot the real FastAPI/Anthropic stack in isolated subprocesses, without secrets or external calls."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DeploymentHTTP(unittest.TestCase):
    def boot(self, desktop):
        with tempfile.TemporaryDirectory() as data:
            env = {k: v for k, v in os.environ.items() if k in (
                "PATH", "HOME", "LANG", "SYSTEMROOT", "SSL_CERT_FILE")}
            env.update(AGENT_API_KEY="deployment-local-test", ANTHROPIC_API_KEY="",
                       DATA_DIR=data, PYTHON_DOTENV_DISABLED="1", SCHEDULER_ENABLED="false",
                       CRYPTO_PRACTICE_ONLY="true", COINBASE_TRADING_ENABLED="false",
                       DESKTOP_API_ENABLED=str(desktop).lower())
            script = '''
from fastapi.testclient import TestClient
import main
with TestClient(main.app) as client:
    for path in ("/", "/health"):
        response = client.get(path)
        assert response.status_code == 200, response.text
        state = response.json()
        assert state["version"] == "4.2.0"
        assert state["v420"]["status"] == "activa"
        assert main.kv_get("jarvis:v420:boot", {})["version"] == "4.2.0"
        assert state["instance"]["leader"] is True
        assert state["coinbase"]["practice_only"] is True
        assert state["coinbase"]["trading"] is False
        assert state["ai"]["configured"] is False
    assert client.post("/chat", headers={"x-api-key": "wrong"},
                       json={"message": "hola"}).status_code == 401
    assert client.get("/backup", headers={"x-api-key": "wrong"}).status_code == 401
    assert client.post("/telegram", json={"update_id": 1}).status_code == 401
    reply = client.post("/chat", headers={"x-api-key": "deployment-local-test"},
                        json={"message": "Explica como calcular materiales"})
    assert reply.status_code == 200, reply.text
    assert "no está configurada" in reply.json()["reply"], reply.text
    snapshot = client.get("/backup", headers={"x-api-key": "deployment-local-test"})
    assert snapshot.status_code == 200, snapshot.text
    assert state["desktop_api"]["enabled"] is DESKTOP
    denied = client.get("/desktop/v1/status")
    assert denied.status_code == (401 if DESKTOP else 404), denied.text
print("Real stack startup, shutdown, health, authentication, backup and AI-off: OK")
'''.replace("DESKTOP", repr(desktop))
            result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, env=env,
                                    capture_output=True, text=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_boot_with_desktop_disabled(self):
        self.boot(False)

    def test_boot_with_desktop_enabled(self):
        self.boot(True)


if __name__ == "__main__":
    unittest.main()
