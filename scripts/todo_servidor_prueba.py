"""Sirve /todo y cuatro paginas falsas con las MISMAS cabeceras que el panel real,
   para comprobar que SAMEORIGIN deja enmarcar y que nada queda en blanco."""
import http.server, socketserver, pathlib
AQUI = pathlib.Path("/tmp/todoprueba")
PAGINAS = {"/": "panel", "/hud": "hud", "/mercado": "mercado", "/avatar": "core"}

class H(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; style-src 'self'; script-src 'self'; "
                         "frame-src 'self'; frame-ancestors 'self'")
        self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        if self.path == "/todo":
            return self._send(200, (AQUI / "index0.html").read_bytes(), "text/html; charset=utf-8")
        if self.path.startswith("/ui/"):
            n = self.path[4:].split("?")[0]
            t = "text/css; charset=utf-8" if n.endswith(".css") else "text/javascript; charset=utf-8"
            return self._send(200, (AQUI / n).read_bytes(), t)
        if self.path in PAGINAS:
            nombre = PAGINAS[self.path]
            cuerpo = ("<!doctype html><meta charset=utf-8><title>%s</title>"
                      "<body data-quien='%s'><div id='quien'>%s</div>"
                      "<script src='/ui/marca.js'></script>" % (nombre, nombre, nombre.upper())).encode()
            return self._send(200, cuerpo, "text/html; charset=utf-8")
        self._send(404, b"no", "text/plain")

socketserver.TCPServer.allow_reuse_address = True
socketserver.TCPServer(("127.0.0.1", 8896), H).serve_forever()
