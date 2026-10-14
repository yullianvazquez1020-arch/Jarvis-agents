"""Torre de Aincrad local: 100 pisos, cada uno un negocio, Jarvis al mando.

Todas las cifras son FICTICIAS (DEMO) y nunca salen de datos reales del dueño.
Precios cripto: Coinbase spot público (sin clave, solo lectura); si falla, "sin conexión".
No hay trading real ni claves.
"""
import json
import threading
import time
import urllib.request

DEMO_LABEL = "DEMO · cifras ficticias"
TOTAL_PISOS = 100
NEGOCIOS = (
    {"id": "side-hustle", "nombre": "Side hustle con Jarvis", "estado": "activo",
     "meta_mes_usd": 500, "real_mes_usd": 120},
    {"id": "renta-jarvis", "nombre": "Renta de equipos/servicios Jarvis", "estado": "plan",
     "meta_mes_usd": 800, "real_mes_usd": 0},
    {"id": "trading", "nombre": "Trading con Jarvis (práctica)", "estado": "práctica",
     "meta_mes_usd": 0, "real_mes_usd": 0},
    {"id": "agencia-ia", "nombre": "Agencia de contenido con IA", "estado": "plan",
     "meta_mes_usd": 600, "real_mes_usd": 0},
    {"id": "contesta-ya", "nombre": "ISLAFIX Contesta Ya", "estado": "semana 1",
     "meta_mes_usd": 400, "real_mes_usd": 50},
)
CONTROLADOR = "Jarvis"


def pisos():
    out = []
    for n in range(1, TOTAL_PISOS + 1):
        if n <= len(NEGOCIOS):
            out.append(dict(NEGOCIOS[n - 1], piso=n))
        else:
            out.append({"piso": n, "id": f"libre-{n}", "nombre": "Piso libre", "estado": "por conquistar",
                        "meta_mes_usd": 0, "real_mes_usd": 0})
    return out


def torre():
    activos = [p for p in pisos() if not p["id"].startswith("libre-")]
    return {"nombre": "Torre de Aincrad", "controlador": CONTROLADOR, "demo": True, "etiqueta": DEMO_LABEL,
            "total_pisos": TOTAL_PISOS, "conquistados": len(activos), "pisos": pisos(),
            "negocios": activos,
            "totales": {"meta_mes_usd": sum(p["meta_mes_usd"] for p in activos),
                        "real_mes_usd": sum(p["real_mes_usd"] for p in activos)}}


SPOT = "https://api.coinbase.com/v2/prices/{}/spot"
PARES = ("BTC-USD", "ETH-USD", "SOL-USD")
_cache = {"t": 0.0, "data": None}
_lock = threading.Lock()


def _fetch(par, timeout=4):
    req = urllib.request.Request(SPOT.format(par), headers={"User-Agent": "jarvis-desktop"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return float(json.loads(r.read().decode())["data"]["amount"])


def mercado(fetch=_fetch, ttl=60, now=time.time):
    with _lock:
        if _cache["data"] and now() - _cache["t"] < ttl:
            return _cache["data"]
    precios, error = [], None
    for par in PARES:
        try:
            precios.append({"par": par, "usd": round(fetch(par), 2)})
        except Exception as e:  # red caída, bloqueo o respuesta rara: se muestra sin conexión
            error = type(e).__name__
            precios.append({"par": par, "usd": None})
    ok = any(p["usd"] is not None for p in precios)
    data = {"fuente": "Coinbase spot público (sin clave)", "conectado": ok, "error": None if ok else error,
            "modo": "práctica", "trading_real": False, "precios": precios, "hora": int(now())}
    with _lock:
        _cache.update(t=now(), data=data)
    return data
