#!/usr/bin/env python3
"""Genera YOUTUBE_REFRESH_TOKEN en TU Mac (no en Render, no en git).

Uso:
  python3 scripts/youtube_refresh_token.py --client-secret ~/Downloads/client_secret_XXXX.json
  (o --client-id ... --client-secret-value ...)

Abre el navegador, tú autorizas el canal, y el script imprime los 4 valores para Render:
YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN, YOUTUBE_CHANNEL_ID.
No guarda nada en disco ni sube nada a YouTube. Solo biblioteca estándar.
"""
import argparse, base64, hashlib, http.server, json, secrets, sys, threading, urllib.parse, urllib.request, webbrowser

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels?part=id,snippet&mine=true"
# /subiryoutube (videos.insert) y /publicaryoutube (videos.update) necesitan el alcance completo;
# youtube.upload solo NO permite cambiar a público.
SCOPE = "https://www.googleapis.com/auth/youtube"


def load_client(path=None, cid=None, csecret=None):
    if path:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        block = data.get("installed") or data.get("web")
        if not block:
            raise SystemExit("El JSON no es un cliente OAuth. Crea uno tipo 'App de escritorio'.")
        if "installed" not in data:
            raise SystemExit("Ese cliente es tipo 'Web'. Crea uno tipo 'App de escritorio' (Desktop).")
        return block["client_id"], block["client_secret"]
    if cid and csecret:
        return cid, csecret
    raise SystemExit("Falta --client-secret archivo.json (o --client-id y --client-secret-value).")


def pkce_pair():
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(cid, redirect, challenge, state):
    q = {"client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
         "access_type": "offline", "prompt": "consent", "include_granted_scopes": "true",
         "code_challenge": challenge, "code_challenge_method": "S256", "state": state}
    return AUTH_URL + "?" + urllib.parse.urlencode(q)


def exchange(cid, csecret, code, redirect, verifier, opener=urllib.request.urlopen):
    body = urllib.parse.urlencode({"code": code, "client_id": cid, "client_secret": csecret,
                                   "redirect_uri": redirect, "grant_type": "authorization_code",
                                   "code_verifier": verifier}).encode()
    with opener(urllib.request.Request(TOKEN_URL, data=body, method="POST")) as r:
        tok = json.loads(r.read())
    if not tok.get("refresh_token"):
        raise SystemExit("Google no devolvió refresh_token. Quita el acceso en myaccount.google.com/permissions y repite.")
    return tok


def channel_of(access_token, opener=urllib.request.urlopen):
    req = urllib.request.Request(CHANNELS_URL, headers={"Authorization": "Bearer " + access_token})
    with opener(req) as r:
        items = json.loads(r.read()).get("items") or []
    if not items:
        raise SystemExit("Esa cuenta Google no tiene canal YouTube. Elige la cuenta/marca del canal al autorizar.")
    return items[0]["id"], items[0].get("snippet", {}).get("title", "")


def render_lines(cid, csecret, refresh, channel_id):
    return [f"YOUTUBE_CLIENT_ID={cid}", f"YOUTUBE_CLIENT_SECRET={csecret}",
            f"YOUTUBE_REFRESH_TOKEN={refresh}", f"YOUTUBE_CHANNEL_ID={channel_id}"]


def wait_for_code(state):
    got = {}
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if q.get("state", [""])[0] == state:
                got.update(code=q.get("code", [""])[0], error=q.get("error", [""])[0])
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("Listo. Vuelve a la Terminal.".encode())
        def log_message(self, *a): pass
    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    return srv, got


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client-secret", help="JSON descargado del cliente OAuth Desktop")
    ap.add_argument("--client-id"); ap.add_argument("--client-secret-value")
    a = ap.parse_args(argv)
    cid, csecret = load_client(a.client_secret, a.client_id, a.client_secret_value)
    state = secrets.token_urlsafe(16); verifier, challenge = pkce_pair()
    srv, got = wait_for_code(state)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = build_auth_url(cid, redirect, challenge, state)
    print("Abriendo el navegador. Si no abre, copia este enlace:\n" + url + "\n")
    threading.Thread(target=webbrowser.open, args=(url,), daemon=True).start()
    while not got:
        srv.handle_request()
    if got.get("error") or not got.get("code"):
        raise SystemExit("Autorización cancelada: " + (got.get("error") or "sin código"))
    tok = exchange(cid, csecret, got["code"], redirect, verifier)
    ch, title = channel_of(tok["access_token"])
    print(f"Canal autorizado: {title} ({ch})\n\nPega estas 4 variables en Render > Environment (NO en git):\n")
    print("\n".join(render_lines(cid, csecret, tok["refresh_token"], ch)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
