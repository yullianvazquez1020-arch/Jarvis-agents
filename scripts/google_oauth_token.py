#!/usr/bin/env python3
"""Saca el GOOGLE_REFRESH_TOKEN de SOLO LECTURA (Gmail + Calendar) para Jarvis. Córrelo en TU Mac (Python 3.9+).

    python3 scripts/google_oauth_token.py

Te pide el Client ID y el Client Secret del cliente OAuth tipo "App de escritorio", abre el navegador, tú aceptas
con yullianvazquez@gmail.com y el token sale SOLO en esta terminal. No guarda nada en disco ni en Git.
Usa solo la biblioteca estándar (sin pip install).
"""
import getpass
import hashlib
import base64
import http.server
import json
import secrets
import socket
import sys
import urllib.parse
import urllib.request
import webbrowser

SCOPES = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar.readonly"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); return s.getsockname()[1]


def main():
    cid = input("Client ID: ").strip()
    csec = getpass.getpass("Client Secret (no se ve al escribir): ").strip()
    if not cid or not csec:
        print("Faltan datos."); return 2
    port = free_port(); redirect = f"http://127.0.0.1:{port}"
    state = secrets.token_urlsafe(24); verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPES, "state": state,
        "access_type": "offline", "prompt": "consent", "code_challenge": challenge, "code_challenge_method": "S256"})
    got = {}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write("Listo. Vuelve a la terminal.".encode())

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", port), H)
    print("Abriendo el navegador. Si no abre, copia esta dirección:\n" + url)
    webbrowser.open(url)
    srv.handle_request(); srv.server_close()
    if got.get("state") != state or "code" not in got:
        print("No llegó la autorización: " + got.get("error", "estado inválido")); return 1
    data = urllib.parse.urlencode({"code": got["code"], "client_id": cid, "client_secret": csec,
                                   "redirect_uri": redirect, "grant_type": "authorization_code",
                                   "code_verifier": verifier}).encode()
    with urllib.request.urlopen("https://oauth2.googleapis.com/token", data, timeout=30) as r:
        tok = json.loads(r.read())
    if not tok.get("refresh_token"):
        print("Google no devolvió refresh token. Quita el acceso en myaccount.google.com/permissions y repite."); return 1
    print("\nPermisos concedidos:", tok.get("scope"))
    print("\nGOOGLE_REFRESH_TOKEN (cópialo a Render; no lo pegues en chats ni en Git):\n" + tok["refresh_token"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
