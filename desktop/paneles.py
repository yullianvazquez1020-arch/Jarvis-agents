"""Paneles visuales de negocio para /nucleo. SOLO datos reales y locales.

Fuentes (todas de solo lectura):
- ~/.jarvis-control/audit.jsonl   -> acciones del agente (actividad por hora, últimas acciones)
- ~/.jarvis-control/ultimo_move.json -> último movimiento del puntero
- ~/.jarvis-control/capturas/*.png   -> evidencia visual (solo nombre y hora; nunca se sirve fuera de la sesión)
- ~/.jarvis-control/negocios/<id>.json -> progreso real que el dueño o Jarvis escriban (hitos, serie, monto)
- panel "cobros"/"estado" del servidor Jarvis cuando el equipo está emparejado (lo pasa app.py)
Si una fuente no existe o está vacía: "sin datos" / "pendiente de conectar". Nunca se inventan cifras.
Las cifras de negocios.py son DEMO y aquí NO se usan.
"""
import json
import os
import re
import time
from pathlib import Path

SIN_DATOS = "sin datos"
PENDIENTE = "pendiente de conectar"
MAX_LINEAS = 4000

NEGOCIOS = (
    {"id": "islafix", "nombre": "ISLAFIX PRO", "alias": ["islafix", "isla fix", "contesta ya", "cobro", "cliente"],
     "fuente": "servidor Jarvis (panel cobros) + negocios/islafix.json"},
    {"id": "amazon", "nombre": "Amazon Seller", "alias": ["amazon", "seller", "fba", "inventario"],
     "fuente": "negocios/amazon.json (Amazon SP-API aún no conectado)"},
    {"id": "youtube", "nombre": "YouTube", "alias": ["youtube", "canal", "video", "suscriptor"],
     "fuente": "negocios/youtube.json (API de YouTube aún no conectada)"},
    {"id": "agencia-ia", "nombre": "Agencia de contenido IA", "alias": ["agencia", "contenido"],
     "fuente": "negocios/agencia-ia.json"},
    {"id": "trading", "nombre": "Trading (práctica)", "alias": ["trading", "cripto", "bitcoin", "btc"],
     "fuente": "Coinbase spot público + negocios/trading.json"},
)


def control_dir():
    raw = os.environ.get("JARVIS_CONTROL_DIR", "").strip()
    return Path(raw) if raw else Path.home() / ".jarvis-control"


def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _txt(v, n=120):
    return " ".join(str(v or "").split())[:n]


def _read_json(path):
    try:
        if path.is_file() and path.stat().st_size < 262144:
            d = json.loads(path.read_text("utf-8"))
            return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None
    return None


def negocio(base, root, servidor=None):
    """Un panel. Datos de negocios/<id>.json (escritos por el dueño o Jarvis) y, para ISLAFIX, el servidor."""
    out = {"id": base["id"], "nombre": base["nombre"], "alias": base["alias"], "fuente": base["fuente"],
           "estado": PENDIENTE, "progreso": None, "meta": None, "real": None, "unidad": "",
           "serie": [], "hitos": [], "lineas": [], "as_of": None, "datos": False}
    d = _read_json(root / "negocios" / f"{base['id']}.json")
    if d:
        out["estado"] = _txt(d.get("estado"), 40) or "activo"
        meta, real = _num(d.get("meta")), _num(d.get("real"))
        out.update(meta=meta, real=real, unidad=_txt(d.get("unidad"), 12), as_of=_txt(d.get("as_of"), 32) or None)
        if meta and real is not None:
            out["progreso"] = max(0.0, min(1.0, real / meta))
        out["serie"] = [x for x in (_num(v) for v in (d.get("serie") or [])[:60]) if x is not None]
        out["hitos"] = [{"t": _txt(h.get("t"), 60), "ok": bool(h.get("ok"))}
                        for h in (d.get("hitos") or [])[:8] if isinstance(h, dict) and h.get("t")]
        if out["progreso"] is None and out["hitos"]:
            out["progreso"] = sum(h["ok"] for h in out["hitos"]) / len(out["hitos"])
        out["lineas"] = [_txt(x) for x in (d.get("lineas") or [])[:4]]
        out["datos"] = True
    if servidor and isinstance(servidor.get("lineas"), list) and servidor["lineas"]:
        out["lineas"] = ([_txt(x) for x in servidor["lineas"][:4]] + out["lineas"])[:5]
        out["as_of"] = out["as_of"] or _txt(servidor.get("as_of"), 32) or None
        out["datos"] = True
        if out["estado"] == PENDIENTE:
            out["estado"] = "conectado"
    if not out["datos"]:
        out["estado"] = PENDIENTE if base["id"] in ("amazon", "youtube") else SIN_DATOS
    return out


def actividad(root, now=None):
    """Acciones reales del agente (audit.jsonl): conteo por hora de las últimas 24 h y las 6 últimas."""
    now = time.time() if now is None else now
    path = root / "audit.jsonl"
    horas = [0] * 24; ultimas = []; veredictos = {}
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()[-MAX_LINEAS:] if path.is_file() else []
    except OSError:
        lines = []
    for raw in lines:
        try:
            e = json.loads(raw)
        except ValueError:
            continue
        if not isinstance(e, dict):
            continue
        t = _ts(e.get("at"))
        v = _txt(e.get("verdict"), 16) or "?"
        veredictos[v] = veredictos.get(v, 0) + 1
        if t is not None and 0 <= now - t < 86400:
            horas[23 - int((now - t) // 3600)] += 1
        ultimas.append({"at": _txt(e.get("at"), 32), "agente": _txt(e.get("agent"), 20),
                        "accion": _txt(e.get("action"), 20), "veredicto": v, "motivo": _txt(e.get("reason"), 40)})
    return {"fuente": str(path), "datos": bool(ultimas), "por_hora": horas, "veredictos": veredictos,
            "total": len(ultimas), "ultimas": ultimas[-6:][::-1], "estado": "ok" if ultimas else SIN_DATOS}


def _ts(s):
    from datetime import datetime
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def evidencia(root):
    folder = root / "capturas"; caps = []
    try:
        files = sorted((p for p in folder.glob("*.png") if re.fullmatch(r"\d{1,12}\.png", p.name)),
                       key=lambda p: p.name, reverse=True) if folder.is_dir() else []
    except OSError:
        files = []
    for p in files[:4]:
        caps.append({"nombre": p.name, "t": int(p.stem)})
    move = _read_json(root / "ultimo_move.json")
    mv = None
    if move:
        mv = {"at": _txt(move.get("at"), 32), "ok": bool(move.get("ok")), "real": move.get("real") if isinstance(move.get("real"), list) else None,
              "accesibilidad": move.get("accesibilidad") if isinstance(move.get("accesibilidad"), bool) else None}
    return {"capturas": caps, "total_capturas": len(files), "ultimo_move": mv,
            "estado": "ok" if (caps or mv) else SIN_DATOS}


def captura(root, nombre):
    if not re.fullmatch(r"\d{1,12}\.png", nombre or ""):
        return None
    p = root / "capturas" / nombre
    return p.read_bytes() if p.is_file() and p.stat().st_size < 8 * 1024 * 1024 else None


def resumen(servidor_cobros=None, cripto=None, root=None, now=None):
    root = root or control_dir()
    neg = [negocio(b, root, servidor_cobros if b["id"] == "islafix" else None) for b in NEGOCIOS]
    if cripto and cripto.get("conectado"):
        t = next(n for n in neg if n["id"] == "trading")
        t["lineas"] = (["%s $%s" % (p["par"], f"{p['usd']:,.2f}") for p in cripto.get("precios", []) if p.get("usd")] + t["lineas"])[:5]
        t["datos"] = True
        if t["estado"] == SIN_DATOS:
            t["estado"] = "práctica · precios en vivo"
    return {"negocios": neg, "actividad": actividad(root, now), "evidencia": evidencia(root),
            "hora": int(time.time() if now is None else now), "inventado": False}
