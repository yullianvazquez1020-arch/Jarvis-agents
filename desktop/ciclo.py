"""Ciclo autónomo local del display (siempre encendido, VOICE_CICLO=false lo apaga).

Toma encargos de ~/.jarvis-desktop/encargos.jsonl (uno por línea) y usa SOLO herramientas de lectura:
  {"tipo": "web", "url": "https://..."}         -> título y primeras líneas de una página pública (GET)
  {"tipo": "archivo", "ruta": "notas.md"}       -> resumen de un archivo dentro de VOICE_CICLO_DIR
  {"tipo": "mouse", "orden": {...}}             -> orden de investigación al mouse autónomo (reglas del ejecutor)
  {"tipo": "estado"}                            -> estado del servidor Jarvis si está emparejado
El resultado se muestra y se dice en voz local. Nunca envía correos/mensajes (eso es /enviar en Jarvis),
nunca cobra (/aprobar + /confirmar), nunca escribe secretos y respeta STOP (~/.jarvis-control/STOP).
El ciclo del servidor (BRAIN 4.2.7) vive en Render con BRAIN_ENABLED=true; este es el gemelo local.
"""
import html
import ipaddress
import json
import os
import re
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TIPOS = ("web", "archivo", "mouse", "estado")
PROHIBIDO = re.compile(r"\b(enviar|send|pagar|pay|cobrar|charge|comprar|buy|transfer|password|contraseña)\b", re.I)
MAX_BYTES = 200_000


def leer_cola(path):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            e = json.loads(ln)
            if isinstance(e, dict):
                out.append(e)
        except ValueError:
            continue
    return out


def host_publico(host, resolver=None):
    """False para loopback, LAN, link-local, multicast o un nombre que resuelve a eso."""
    host = (host or "").strip("[]").rstrip(".").lower()
    if not host or host == "localhost" or host.endswith(".local") or host.endswith(".internal"):
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None:
        return bool(ip.is_global)
    try:
        infos = (resolver or socket.getaddrinfo)(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            addr = ipaddress.ip_address(info[4][0])
        except (TypeError, ValueError, IndexError):
            return False
        if not addr.is_global:
            return False
    return True


class _RedirectPublico(urllib.request.HTTPRedirectHandler):
    def __init__(self, resolver=None):
        super().__init__()
        self.resolver = resolver

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parts = urllib.parse.urlsplit(newurl)
        if parts.scheme != "https" or not host_publico(parts.hostname, self.resolver):
            raise urllib.error.URLError("redirect no publico")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _bajar(url, resolver=None):
    opener = urllib.request.build_opener(_RedirectPublico(resolver))
    req = urllib.request.Request(url, headers={"User-Agent": "jarvis-desktop"})
    with opener.open(req, timeout=10) as resp:
        return resp.read(MAX_BYTES).decode("utf-8", "replace")


def web(url, fetch=None, resolver=None):
    parts = urllib.parse.urlsplit(url or "")
    if parts.scheme != "https" or not parts.hostname or not host_publico(parts.hostname, resolver):
        return "solo https público"
    fetch = fetch or (lambda u: _bajar(u, resolver))
    try:
        body = fetch(url)
    except urllib.error.URLError:
        return "solo https público"
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    title = html.unescape(m.group(1)).strip() if m else "(sin título)"
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", body)))
    return f"{title}: {html.unescape(text).strip()[:240]}"


def archivo(ruta, base):
    base = Path(base).resolve(); p = (base / str(ruta or "")).resolve()
    if base not in p.parents and p != base or not p.is_file():
        return "fuera de la carpeta permitida o no existe"
    rel = p.relative_to(base)
    if any(re.search(r"(\.env|secret|token|key|password|privado)", part, re.I) for part in rel.parts):
        return "archivo sensible: no lo leo"
    lines = [l.strip() for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    return f"{p.name}: {len(lines)} líneas. " + " · ".join(lines[:3])[:240]


def procesar(e, *, base, mouse=None, estado=None, fetch=None, resolver=None):
    tipo = e.get("tipo")
    if tipo not in TIPOS:
        return "tipo no permitido", True
    if PROHIBIDO.search(json.dumps(e, ensure_ascii=False)):
        return "bloqueado: envíos, cobros y contraseñas solo con /enviar o /aprobar + /confirmar en Jarvis", True
    try:
        if tipo == "web":
            return web(e.get("url"), fetch, resolver), True
        if tipo == "archivo":
            return archivo(e.get("ruta"), base), True
        if tipo == "mouse":
            r = (mouse or (lambda o: {"ok": False, "motivo": "sin mouse"}))(e.get("orden"))
            if r.get("ok"):
                return "mouse: orden " + r.get("orden", "") + " en cola", True
            return "mouse: " + r.get("motivo", "rechazado"), False
        return (estado or (lambda: "sin servidor"))(), True
    except Exception as ex:  # una tarea rota no detiene el ciclo
        return f"error {type(ex).__name__}", True


class Ciclo:
    def __init__(self, home, *, base, emit, speak, stopped, mouse=None, estado=None, intervalo=30, fetch=None, resolver=None):
        self.home = Path(home); self.cola = self.home / "encargos.jsonl"; self.hechos = self.home / "encargos_hechos.json"
        self.base, self.emit, self.speak, self.stopped = base, emit, speak, stopped
        self.mouse, self.estado, self.intervalo, self.fetch = mouse, estado, intervalo, fetch
        self.resolver = resolver
        self.ultimo = None; self.vueltas = 0

    def _hechos(self):
        """Cuenta cuántas veces se completó cada clave. Una lista guarda las repeticiones."""
        try:
            raw = json.loads(self.hechos.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        counts = {}
        items = raw.items() if isinstance(raw, dict) else ((k, 1) for k in raw) if isinstance(raw, list) else ()
        for key, n in items:
            key = str(key)
            legado = re.match(r"^(\d+):(.*)$", key)
            if legado:
                try:
                    obj = json.loads(legado.group(2))
                except ValueError:
                    obj = None
                if isinstance(obj, dict) and legado.group(2) == json.dumps(obj, sort_keys=True):
                    key = legado.group(2)
            try:
                n = int(n)
            except (TypeError, ValueError):
                continue
            if n > 0:
                counts[key] = counts.get(key, 0) + n
        return counts

    def _con_id(self, entradas):
        """Cada línea guarda su propio id. Dos textos iguales no comparten el hecho de una sola."""
        cambio, out = False, []
        for e in entradas:
            e = dict(e)
            if not str(e.get("id") or "").strip():
                e["id"] = "c-" + secrets.token_hex(8)
                cambio = True
            out.append(e)
        if not cambio:
            return out
        self.home.mkdir(parents=True, exist_ok=True)
        tmp = self.cola.with_name(self.cola.name + ".tmp")
        tmp.write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in out), encoding="utf-8")
        os.replace(tmp, self.cola)
        return out

    def vuelta(self):
        self.vueltas += 1
        if self.stopped():
            self.ultimo = "STOP activo: ciclo en pausa"; return []
        hechos, out, vistos = self._hechos(), [], {}
        previo = [k for k, n in sorted(hechos.items()) for _ in range(n)]
        for e in self._con_id(leer_cola(self.cola)):
            key = str(e.get("id"))
            vistos[key] = vistos.get(key, 0) + 1
            if vistos[key] <= hechos.get(key, 0):
                continue
            res, aceptar = procesar(e, base=self.base, mouse=self.mouse, estado=self.estado,
                                    fetch=self.fetch, resolver=self.resolver)
            if aceptar:
                hechos[key] = hechos.get(key, 0) + 1
            out.append(res)
            self.emit({"type": "ciclo", "tipo": e.get("tipo"), "text": res[:300]})
            self.speak(f"Encargo listo. {res[:160]}")
        vigentes = {k: min(hechos.get(k, 0), n) for k, n in vistos.items()}
        vigentes = {k: n for k, n in vigentes.items() if n > 0}
        lista = [k for k, n in sorted(vigentes.items()) for _ in range(n)]
        if lista != previo:
            self.home.mkdir(parents=True, exist_ok=True)
            tmp = self.hechos.with_name(self.hechos.name + ".tmp")
            tmp.write_text(json.dumps(lista), encoding="utf-8"); os.replace(tmp, self.hechos)
        self.ultimo = out[-1] if out else self.ultimo
        return out

    def estado_view(self):
        return {"activo": True, "vueltas": self.vueltas, "ultimo": self.ultimo, "cola": str(self.cola),
                "intervalo_s": self.intervalo}

    def arrancar(self):
        def loop():
            while True:
                try:
                    self.vuelta()
                except Exception:
                    pass
                time.sleep(self.intervalo)
        threading.Thread(target=loop, daemon=True).start()
