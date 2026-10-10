# jarvis_practica.py — Jarvis 4.2.6: práctica de trading más seria.
# Aditivo sobre el simulador de v3.8. Sigue siendo DINERO SIMULADO con precios reales; nunca toca dinero real,
# no envía órdenes a Coinbase y no recomienda qué comprar.
#
# 1. Métricas de riesgo: caída máxima, caída actual, factor de ganancia, ganancia y pérdida promedio, esperanza
#    por operación y cuánto se comieron las comisiones. Con menos de 30 operaciones cerradas lo dice claro.
# 2. Stop dinámico: cuando una posición ya ganó TRAIL_START %, si cae TRAIL % desde su máximo se cierra.
# 3. Muestra la pausa de entradas que ya aplica jarvis_growth (caída máxima o pérdida del día). No la duplica.
# 4. Datos para la gráfica del escritorio: curva de capital, operaciones y lectura de cada mercado.

from __future__ import annotations

import datetime
import math
import os

VERSION = "4.2.6"
MIN_SAMPLE = 30
CHART_POINTS = 240
PAUSE_TEXT = {"drawdown": "la práctica cayó demasiado desde su máximo", "daily_loss": "perdió demasiado hoy"}

core = None


def _env_pct(name, default, low, high):
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if math.isfinite(value) and low <= value <= high else default


TRAIL_START = _env_pct("PAPER_TRAIL_START_PCT", 4, 0.5, 100)
TRAIL = _env_pct("PAPER_TRAIL_PCT", 3, 0.5, 50)


# ---------------------------------------------------------------------------
# Métricas
# ---------------------------------------------------------------------------
def drawdowns(values):
    """-> (caída máxima %, caída actual %, pico). Sobre la curva de capital guardada."""
    peak, worst = None, 0.0
    for v in values:
        if not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
            continue
        peak = v if peak is None else max(peak, v)
        worst = max(worst, (peak - v) / peak * 100)
    if peak is None:
        return 0.0, 0.0, None
    last = next((v for v in reversed(values) if isinstance(v, (int, float)) and math.isfinite(v) and v > 0), peak)
    return round(worst, 2), round((peak - last) / peak * 100, 2), round(peak, 2)


def metrics(d):
    sells = [t for t in d.get("trades", []) if t.get("side") == "sell" and isinstance(t.get("pnl"), (int, float))]
    pnls = [float(t["pnl"]) for t in sells]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    equity = [e.get("v") for e in d.get("equity", []) if isinstance(e, dict)]
    max_dd, cur_dd, peak = drawdowns(equity)
    gross_loss = -sum(losses)
    realized = float(d.get("realized") or 0)
    fees = float(d.get("fees") or 0)
    gross = realized + fees
    return {
        "closed_trades": len(pnls),
        "max_drawdown_pct": max_dd,
        "drawdown_now_pct": cur_dd,
        "equity_peak": peak,
        "profit_factor": round(sum(wins) / gross_loss, 2) if gross_loss > 0 else None,
        "avg_win": round(sum(wins) / len(wins), 2) if wins else None,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else None,
        "expectancy": round(sum(pnls) / len(pnls), 2) if pnls else None,
        "fees_share_pct": round(fees / gross * 100, 1) if gross > 0 else None,
        "sample_ok": len(pnls) >= MIN_SAMPLE,
    }


def metrics_lines(m):
    lines = [f"Riesgo: caída máxima {m['max_drawdown_pct']:.2f}% · caída actual {m['drawdown_now_pct']:.2f}%"]
    if m["closed_trades"]:
        pf = "—" if m["profit_factor"] is None else f"{m['profit_factor']:.2f}"
        lines.append(f"Factor de ganancia {pf} · por operación {core._bank_usd(m['expectancy'])}"
                     + (f" · gana en promedio {core._bank_usd(m['avg_win'])}" if m["avg_win"] is not None else "")
                     + (f" · pierde en promedio {core._bank_usd(m['avg_loss'])}" if m["avg_loss"] is not None else ""))
    if m["fees_share_pct"] is not None:
        lines.append(f"Las comisiones se llevaron {m['fees_share_pct']:.0f}% de la ganancia antes de comisiones.")
    if not m["sample_ok"]:
        lines.append(f"Muestra chica: {m['closed_trades']} operación(es) cerrada(s). Con menos de {MIN_SAMPLE} todavía "
                     "no se puede concluir si la estrategia funciona.")
    return lines


def pause_reason(d):
    return str((d.get("risk") or {}).get("pause_reason") or "")


# ---------------------------------------------------------------------------
# Regla nueva: stop dinámico, antes del paso existente
# ---------------------------------------------------------------------------
def trailing_exits(d, markets):
    events = []
    for p, m in markets.items():
        pos = d["positions"].get(p)
        price = m.get("price")
        if not pos or not isinstance(price, (int, float)) or price <= 0:
            continue
        pos["peak"] = max(float(pos.get("peak") or pos["entry"]), float(price))
        gained = pos["peak"] / pos["entry"] - 1
        drop = 1 - price / pos["peak"]
        if gained >= TRAIL_START / 100 and drop >= TRAIL / 100:
            d["last_prices"][p] = price
            events.append(core._paper_sell(d, p, price, f"stop dinámico: bajó {drop * 100:.1f}% desde su máximo "
                                                        f"(había llegado a +{gained * 100:.1f}%)"))
    return events


def chart_data():
    """Datos de solo lectura para la gráfica del escritorio. Nada de esto es dinero real."""
    d = core._paperload()
    s = core.paper_status()
    eq = [{"t": e["at"], "v": e["v"]} for e in d.get("equity", [])[-CHART_POINTS:]
          if isinstance(e, dict) and isinstance(e.get("v"), (int, float))]
    first = eq[0]["t"] if eq else None
    trades = [{"t": t["at"], "side": t["side"], "product": t["product"]} for t in d.get("trades", [])
              if first and t.get("at", "") >= first and t.get("side") in ("buy", "sell")][-60:]
    products = []
    for p in core.PAPER_PRODUCTS:
        m = d.get("last_market", {}).get(p) or {}
        products.append({"product": p, "price": m.get("price"), "change_24h_pct": m.get("change_24h_pct"),
                         "rsi": m.get("rsi"), "trend": m.get("trend"), "open": p in d.get("positions", {})})
    return {"mode": "practice", "start": s["start_usd"], "equity": eq, "trades": trades, "products": products,
            "summary": {"equity": s["equity"], "pnl_total": s["pnl_total"], "pnl_pct": s["pnl_pct"],
                        "win_rate_pct": s["win_rate_pct"], "vs_buy_and_hold": s["vs_buy_and_hold"],
                        **metrics(d)},
            "paused": pause_reason(d) or None, "last_run": d.get("last_run")}


# ---------------------------------------------------------------------------
# Instalación
# ---------------------------------------------------------------------------
def install(j):
    global core
    core = j
    original_apply = j._paper_apply
    original_status = j.paper_status
    original_status_text = j.paper_status_text
    original_report = j.paper_report_text

    def paper_apply(d, markets):
        return trailing_exits(d, markets) + original_apply(d, markets)

    def paper_status():
        s = original_status()
        d = j._paperload()
        s["metrics"] = metrics(d)
        s["paused"] = pause_reason(d) or None
        return s

    def paper_status_text():
        text = original_status_text()
        d = j._paperload()
        if not d.get("last_run"):
            return text
        extra = metrics_lines(metrics(d))
        reason = pause_reason(d)
        if reason:
            extra.append(f"⏸️ Entradas en pausa: {PAUSE_TEXT.get(reason, reason)}. Las salidas siguen funcionando.")
        return text + "\n" + "\n".join(extra)

    def paper_report_text():
        m = metrics(j._paperload())          # caída máxima y factor de ganancia ya los pone la evaluación de growth
        extra = []
        if m["expectancy"] is not None:
            extra.append(f"Por operación: {j._bank_usd(m['expectancy'])} en promedio.")
        if m["fees_share_pct"] is not None:
            extra.append(f"Comisiones: {m['fees_share_pct']:.0f}% de la ganancia antes de comisiones.")
        return original_report() + ("\n" + "\n".join(extra) if extra else "")

    j._paper_apply = paper_apply
    j.paper_status = paper_status
    j.paper_status_text = paper_status_text
    j.paper_report_text = paper_report_text
    j.practica_chart = chart_data
    j.PAPER_RULES = (j.PAPER_RULES + f" Stop dinámico: si una posición llegó a +{TRAIL_START:g}% y luego cae "
                     f"{TRAIL:g}% desde su máximo, se cierra.")
    old_diag = j.diagnostics_text

    async def diagnostics_text():
        return (await old_diag()) + f"\n• Práctica {VERSION}: {getattr(j, 'PRACTICA_STATUS', 'activa')} · stop " \
                                    f"dinámico {TRAIL_START:g}/{TRAIL:g}%"

    j.diagnostics_text = diagnostics_text
    j.PRACTICA_STATUS = "activa"
