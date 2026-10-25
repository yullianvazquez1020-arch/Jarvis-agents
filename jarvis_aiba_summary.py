"""Jarvis -> AIBA read-only metrics adapter. Explicit opt-in. No PII or actions."""
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urlsplit


def fetch_aiba_summary(url=None, key=None):
    url = url if url is not None else os.getenv("AIBA_SUMMARY_URL", "")
    key = key if key is not None else os.getenv("AIBA_JARVIS_OPERATOR_KEY", "")
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "aiba-technologies-preview.onrender.com"
            or parts.port not in (None, 443)
            or parts.path != "/api/integrations/jarvis/summary"
            or parts.query or parts.fragment or parts.username or parts.password):
        raise ValueError("AIBA summary URL not allowed")
    if not isinstance(key, str) or len(key) < 32:
        raise ValueError("AIBA integration not configured")
    request = urllib.request.Request(url, method="GET", headers={
        "Authorization": "Bearer " + key, "Accept": "application/json"})
    # Do not follow any redirects with credentials.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=10) as response:
            if response.status != 200 or response.headers.get_content_type() != "application/json":
                raise RuntimeError("AIBA metrics unavailable")
            raw = response.read(16385)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("AIBA metrics unavailable") from None
    if len(raw) > 16384:
        raise RuntimeError("AIBA response oversized")
    try:
        data = json.loads(raw)
    except ValueError:
        raise RuntimeError("AIBA returned invalid metrics") from None
    counts = data.get("leads_by_status") if isinstance(data, dict) else None
    if not isinstance(counts, dict) or data.get("service") != "AIBA":
        raise RuntimeError("Invalid AIBA response")
    if any(not isinstance(k, str) or type(v) is not int or v < 0 for k,v in counts.items()):
        raise RuntimeError("Invalid AIBA metric values")
    return {"service": "AIBA", "leads_by_status": counts}


if __name__ == "__main__":
    try:
        print(json.dumps(fetch_aiba_summary(), ensure_ascii=False, sort_keys=True))
    except (ValueError, RuntimeError):
        print("AIBA integration is unavailable or not configured")
        raise SystemExit(1) from None
