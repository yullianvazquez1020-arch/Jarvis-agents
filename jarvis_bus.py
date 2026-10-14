"""Registro compartido de negocios + bus de eventos (Jarvis <-> Grok Bot).

Cada negocio emite eventos de estado; Grok Bot los lee con X-Jarvis-Secret.
Solo lectura/registro: ningún evento ejecuta pagos, envíos ni publicaciones.
Memoria acotada (se pierde al reiniciar; persistencia en Redis = paso siguiente).
"""
import re, threading, time
from collections import deque

ESTADOS = ("idea", "plan", "codigo", "pr", "live", "pausado")
FUENTES = ("jarvis", "grokbot", "negocio")
MAX_EVENTOS = 500
MAX_TEXTO = 1000

NEGOCIOS = {
    "contesta-ya": "Contesta Ya (recepcionista IA)",
    "renta": "Renta de servicios",
    "amazon": "Amazon SP-API (lectura)",
    "alibaba": "Alibaba proveedores",
    "youtube": "Agencia de contenido / YouTube",
    "trading": "Monitores trading/cripto (sin trading real)",
    "subastas-pr": "Subastas PR",
    "membresia": "Membresía asistente",
    "fiscal-acs": "Carta ACS / fiscal",
}

_SECRETO = re.compile(r"(sk|pk|rk|whsec|ghp|xox[abp])[-_][A-Za-z0-9_\-]{8,}|"
                      r"(?i:(password|secret|token|api[_-]?key)\s*[:=]\s*\S+)")


_REDACTOR = None   # main.py instala su redactor completo (_redact_secrets) al importar


def set_redactor(fn):
    """fn(texto) -> texto limpio. main.py instala el redactor completo del repo."""
    global _REDACTOR
    _REDACTOR = fn


def redactar(texto):
    t = str(texto)
    if _REDACTOR is not None:
        t = _REDACTOR(t)
    t = _SECRETO.sub("[REDACTADO]", t)          # red mínima extra, nunca en lugar del completo
    return t[:MAX_TEXTO]                         # truncar DESPUÉS de redactar


def contiene_secreto(texto):
    """True si el redactor cambia el valor. El corte a MAX_TEXTO no cuenta."""
    t = str(texto)
    return redactar(t) != t[:MAX_TEXTO]


def secreto_usable(value):
    """La misma regla que _secret_values: corto o un marcador no abre el bus."""
    v = str(value or "").strip()
    return len(v) >= 8 and v.lower() not in {"change-me", "test-local-only"}


class Bus:
    def __init__(self, now=time.time):
        self._now, self._lock, self._seq = now, threading.Lock(), 0
        self._ev = deque(maxlen=MAX_EVENTOS)
        self._estado = {k: {"id": k, "nombre": v, "estado": "idea", "nota": "", "ts": None}
                        for k, v in NEGOCIOS.items()}

    def emitir(self, negocio, tipo, texto="", estado=None, fuente="jarvis"):
        if negocio not in self._estado: raise KeyError(f"negocio desconocido: {negocio}")
        if estado is not None and estado not in ESTADOS: raise ValueError(f"estado inválido: {estado}")
        if fuente not in FUENTES: raise ValueError(f"fuente inválida: {fuente}")
        crudo = str(tipo)
        with self._lock:
            self._seq += 1
            if _REDACTOR is None: raise RuntimeError("redactor completo no instalado; evento rechazado")
            if contiene_secreto(crudo):
                tipo = "redactado"
            else:
                tipo = re.sub(r"[^a-z0-9_.-]", "", crudo.lower())[:40] or "nota"
                if contiene_secreto(tipo):
                    tipo = "redactado"
            ev = {"seq": self._seq, "ts": self._now(), "negocio": negocio, "tipo": tipo,
                  "texto": redactar(texto), "estado": estado, "fuente": fuente}
            self._ev.append(ev)
            n = self._estado[negocio]; n["ts"] = ev["ts"]; n["nota"] = ev["texto"][:200]
            if estado: n["estado"] = estado
            return dict(ev)

    def eventos(self, desde=0, negocio=None, limite=100):
        limite = max(1, min(int(limite), MAX_EVENTOS))
        with self._lock:
            out = [dict(e) for e in self._ev if e["seq"] > int(desde) and (negocio is None or e["negocio"] == negocio)]
        return out[:limite]

    def tablero(self):
        with self._lock:
            return {"negocios": [dict(v) for v in self._estado.values()], "ultimo_seq": self._seq,
                    "solo_lectura": True}


BUS = Bus()
