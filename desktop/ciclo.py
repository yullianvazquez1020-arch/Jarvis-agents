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
import json
import os
import re
import threading
import time
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


def web(url, fetch=None):
    if not re.match(r"^https://[^/\s@]+(/|$)", url or ""):
        return "solo https público"
    fetch = fetch or (lambda u: urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "jarvis-desktop"}),
                                                       timeout=10).read(MAX_BYTES).decode("utf-8", "replace"))
    body = fetch(url)
    m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I | re.S)
    title = html.unescape(m.group(1)).strip() if m else "(sin título)"
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", " ", body)))
    return f"{title}: {html.unescape(text).strip()[:240]}"


def archivo(ruta, base):
    base = Path(base).resolve(); p = (base / str(ruta or "")).resolve()
    if base not in p.parents and p != base or not p.is_file():
        return "fuera de la carpeta permitida o no existe"
    if re.search(r"(\.env|secret|token|key|password|privado)", p.name, re.I):
        return "archivo sensible: no lo leo"
    lines = [l.strip() for l in p.read_text(encoding="utf-8", errors="replace").splitlines() if l.strip()]
    return f"{p.name}: {len(lines)} líneas. " + " · ".join(lines[:3])[:240]


def procesar(e, *, base, mouse=None, estado=None, fetch=None):
    tipo = e.get("tipo")
    if tipo not in TIPOS:
        return "tipo no permitido"
    if PROHIBIDO.search(json.dumps(e, ensure_ascii=False)):
        return "bloqueado: envíos, cobros y contraseñas solo con /enviar o /aprobar + /confirmar en Jarvis"
    try:
        if tipo == "web":
            return web(e.get("url"), fetch)
        if tipo == "archivo":
            return archivo(e.get("ruta"), base)
        if tipo == "mouse":
            r = (mouse or (lambda o: {"ok": False, "motivo": "sin mouse"}))(e.get("orden"))
            return "mouse: orden " + r.get("orden", "") + " en cola" if r.get("ok") else "mouse: " + r.get("motivo", "rechazado")
        return (estado or (lambda: "sin servidor"))()
    except Exception as ex:  # una tarea rota no detiene el ciclo
        return f"error {type(ex).__name__}"


class Ciclo:
    def __init__(self, home, *, base, emit, speak, stopped, mouse=None, estado=None, intervalo=30, fetch=None):
        self.home = Path(home); self.cola = self.home / "encargos.jsonl"; self.hechos = self.home / "encargos_hechos.json"
        self.base, self.emit, self.speak, self.stopped = base, emit, speak, stopped
        self.mouse, self.estado, self.intervalo, self.fetch = mouse, estado, intervalo, fetch
        self.ultimo = None; self.vueltas = 0

    def _hechos(self):
        try:
            return set(json.loads(self.hechos.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return set()

    def vuelta(self):
        self.vueltas += 1
        if self.stopped():
            self.ultimo = "STOP activo: ciclo en pausa"; return []
        hechos, out, presentes = self._hechos(), [], set()
        hechos |= {k.split(":", 1)[1] for k in hechos if re.match(r"^\d+:", k)}   # migra claves antiguas con índice
        for i, e in enumerate(leer_cola(self.cola)):
            key = str(e.get("id") or json.dumps(e, sort_keys=True))      # clave estable: el contenido, nunca la posición
            presentes.add(key)
            if key in hechos:
                continue
            res = procesar(e, base=self.base, mouse=self.mouse, estado=self.estado, fetch=self.fetch)
            hechos.add(key); out.append(res)
            self.emit({"type": "ciclo", "tipo": e.get("tipo"), "text": res[:300]})
            self.speak(f"Encargo listo. {res[:160]}")
        vigentes = hechos & presentes                      # se recuerda TODO lo que sigue en la cola (sin tope que lo reprocese)
        if out or vigentes != hechos:
            self.home.mkdir(parents=True, exist_ok=True)
            tmp = self.hechos.with_name(self.hechos.name + ".tmp")
            tmp.write_text(json.dumps(sorted(vigentes)), encoding="utf-8"); os.replace(tmp, self.hechos)
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
