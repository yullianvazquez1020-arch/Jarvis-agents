"""HTTPS client from the Mac companion to Jarvis on Render (/desktop/v1). Python 3.8+, standard library only.

The device token travels only in the Authorization header, never in a URL. TLS is always verified.
Turns are idempotent: a network retry re-sends the SAME request_id; if the result is unknown it asks the
server for that turn instead of running it again."""
import json
import os
import socket
import stat
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PANELS = ("estado", "agenda", "cobros", "practica")
EVENT_TYPES = ("state", "transcript.final", "reply.text", "panel.open", "proposal.created", "turn.done", "turn.error")


UNPAIRED = -1      # ServerError.status when there is no local token (no request was sent)


class ServerError(RuntimeError):
    def __init__(self, status, detail, maybe_done=False):
        super().__init__(detail); self.status = status; self.detail = detail; self.maybe_done = maybe_done


def check_url(url):
    u = urllib.parse.urlsplit(url or "")
    loopback = u.hostname in ("127.0.0.1", "localhost", "::1")
    if not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError("JARVIS_SERVER_URL debe ser https://tu-servicio.onrender.com sin usuario ni parámetros")
    if u.scheme != "https" and not (u.scheme == "http" and loopback):   # http only for a local test server
        raise ValueError("JARVIS_SERVER_URL debe empezar con https://")
    return url.rstrip("/")


class TokenStore:
    """Device token in ~/.jarvis-desktop/device.json, readable only by this user (0600)."""

    def __init__(self, folder):
        self.folder = Path(folder); self.path = self.folder / "device.json"

    def load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("token") or ""
        except (OSError, ValueError):
            return ""

    def save(self, token, device_id):
        """Atomic: a reader never sees an empty or half-written file (write a private temp file, then rename)."""
        self.folder.mkdir(parents=True, exist_ok=True)
        os.chmod(self.folder, 0o700)
        tmp = self.folder / f".device.{os.getpid()}.{os.urandom(4).hex()}.tmp"
        fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"token": token, "device_id": device_id}, f)
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
        os.replace(tmp, self.path)

    def delete(self):
        try:
            self.path.unlink()
        except OSError:
            pass


class JarvisClient:
    def __init__(self, url, token_fn, timeout=60):
        self.url = check_url(url) if url else ""
        self.token_fn = token_fn; self.timeout = timeout

    def _call(self, method, path, body=None, auth=True):
        if not self.url:
            raise ServerError(0, "JARVIS_SERVER_URL no está configurada")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.url + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("User-Agent", "jarvis-desktop/1")
        if auth:
            tok = self.token_fn()
            if not tok:   # local condition, not an answer from Jarvis: never treated as "token revoked"
                raise ServerError(UNPAIRED, "este equipo no está emparejado con Jarvis")
            req.add_header("Authorization", "Bearer " + tok)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                detail = json.loads(e.read() or b"{}").get("detail", "")
            except ValueError:
                detail = ""
            raise ServerError(e.code, str(detail or f"Jarvis respondió {e.code}")[:200]) from None
        except (urllib.error.URLError, socket.timeout, ConnectionError, TimeoutError) as e:
            # the request may or may not have reached Jarvis
            raise ServerError(0, f"sin conexión con Jarvis ({type(e).__name__})", maybe_done=data is not None) from None

    # pairing (no token yet)
    def pair_start(self, name):
        return self._call("POST", "/desktop/v1/pair/start", {"device_name": name}, auth=False)

    def pair_claim(self, pid, secret):
        return self._call("POST", "/desktop/v1/pair/claim", {"pairing_id": pid, "claim_secret": secret}, auth=False)

    def status(self):
        return self._call("GET", "/desktop/v1/status")

    def panel(self, name):
        if name not in PANELS:
            raise ServerError(400, "panel desconocido")
        return self._call("POST", "/desktop/v1/panel", {"name": name})

    def pulse(self):
        """Status for the top bar plus the alerts of the moment (one authenticated request)."""
        return self._call("POST", "/desktop/v1/pulse", {})

    def hud(self):
        return self._call("POST", "/desktop/v1/hud", {})

    def turn(self, request_id, text, attempts=3):
        """Same request_id on every retry. If the outcome is unknown, ask for it; never run it twice."""
        last = None
        for _ in range(attempts):
            try:
                return self._call("POST", "/desktop/v1/turns", {"request_id": request_id, "text": text})
            except ServerError as e:
                last = e
                if e.status not in (0, 502, 503, 504):
                    raise
        try:
            return self._call("POST", "/desktop/v1/turns/get", {"request_id": request_id})
        except ServerError:
            raise last


def safe_events(events):
    """Only known event types and known panels; anything else from the server is dropped."""
    out = []
    for e in events or []:
        if not isinstance(e, dict) or e.get("type") not in EVENT_TYPES:
            continue
        if e["type"] == "panel.open":
            if e.get("panel") not in PANELS:
                continue
            out.append({"type": "panel.open", "panel": e["panel"]})
        else:
            out.append({"type": e["type"]})
    return out
