"""Registro compartido de negocios + bus de eventos (Jarvis <-> Grok Bot).

Cada negocio emite eventos de estado; Grok Bot los lee con X-Jarvis-Secret.
Solo lectura/registro: ningún evento ejecuta pagos, envíos ni publicaciones.
Memoria acotada (se pierde al reiniciar; persistencia en Redis = paso siguiente).
"""
import re, secrets, threading, time
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
        self._epoch = secrets.token_hex(8)          # cambia en cada arranque; el cursor viejo no sirve
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
            n = self._estado[negocio]
            previo = {"nota": n["nota"], "ts": n["ts"], "estado": n["estado"]}
            ev = {"seq": self._seq, "ts": self._now(), "negocio": negocio, "tipo": tipo,
                  "texto": redactar(texto), "estado": estado, "fuente": fuente, "_previo": previo}
            self._ev.append(ev)
            n["ts"] = ev["ts"]; n["nota"] = ev["texto"][:200]
            if estado: n["estado"] = estado
            publico = dict(ev)
            publico.pop("_previo", None)
            return publico

    def deshacer_emision(self, seq):
        """Quita el último evento si su número no llegó a guardarse. El siguiente puede reutilizarlo."""
        with self._lock:
            if not self._ev or self._ev[-1].get("seq") != int(seq) or self._seq != int(seq):
                return False
            ev = self._ev.pop()
            self._seq -= 1
            previo = ev.get("_previo")
            if isinstance(previo, dict):
                self._estado[ev["negocio"]].update(previo)
            return True

    def continuar_desde(self, seq):
        """El siguiente evento sigue al último que ya se guardó. Un reinicio no vuelve a 1."""
        try:
            n = int(seq)
        except (TypeError, ValueError):
            return
        if n < 0:
            return
        with self._lock:
            if n > self._seq:
                self._seq = n

    def consultar(self, desde=0, negocio=None, limite=100, epoch=None):
        """Lectura con época. Un cursor de otro arranque no esconde los eventos nuevos."""
        limite = max(1, min(int(limite), MAX_EVENTOS))
        with self._lock:
            cursor = int(desde)
            otro_ciclo = epoch is not None and epoch != self._epoch
            reinicio = otro_ciclo or cursor > self._seq
            if reinicio:
                cursor = 0
            out = []
            for e in self._ev:
                if e["seq"] > cursor and (negocio is None or e["negocio"] == negocio):
                    publico = dict(e)
                    publico.pop("_previo", None)
                    out.append(publico)
            page = out[:limite]
            siguiente = page[-1]["seq"] if page else cursor
            return {"eventos": page, "epoch": self._epoch, "reinicio": reinicio,
                    "cursor": siguiente, "ultimo_seq": siguiente, "seq_alto": self._seq}

    def eventos(self, desde=0, negocio=None, limite=100):
        return self.consultar(desde, negocio, limite)["eventos"]

    def tablero(self):
        with self._lock:
            return {"negocios": [dict(v) for v in self._estado.values()], "ultimo_seq": self._seq,
                    "epoch": self._epoch, "solo_lectura": True}


BUS = Bus()
