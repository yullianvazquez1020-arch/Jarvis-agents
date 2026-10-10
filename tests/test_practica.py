"""Jarvis 4.2.6 práctica: stop dinámico, métricas de riesgo y datos de la gráfica. Dinero simulado; sin red.
Nada de esto llama a Coinbase real, aprueba órdenes ni cambia el modo cripto."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import test_extensions as base
import jarvis_practica as pr

j = base.j


def market(price, up=True):
    return {"price": price, "sma20": 101 if up else 99, "sma50": 99 if up else 101,
            "trend": "alcista" if up else "bajista", "rsi": 55}


class Practica(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._seen_updates.clear(); j._rate_hits.clear(); j._fence.update(mode="off", leader=True)
        self.real = [patch.object(j, "cb_approve_text", side_effect=AssertionError("aprobar real")),
                     patch.object(j, "_cb_place_order", new=AsyncMock(side_effect=AssertionError("orden real")), create=True)]
        for p in self.real:
            p.start(); self.addCleanup(p.stop)

    def position(self, entry=100.0):
        d = j._paper_new(1000)
        d["positions"]["BTC-USD"] = {"qty": 2.0, "entry": entry, "cost": 200.0, "opened": j._now().isoformat(timespec="minutes")}
        d["cash"] = 800.0
        return d

    def test_is_installed(self):
        self.assertEqual(j.PRACTICA_STATUS, "activa")
        self.assertIn("Stop dinámico", j.PAPER_RULES)

    def test_trailing_stop_closes_after_gain_then_drop(self):
        d = self.position()
        self.assertEqual(j._paper_apply(d, {"BTC-USD": market(106)}), [])          # +6%: todavía no
        self.assertEqual(d["positions"]["BTC-USD"]["peak"], 106)
        events = j._paper_apply(d, {"BTC-USD": market(102.5)})                    # -3.3% desde 106
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["side"], "sell")
        self.assertIn("stop dinámico", events[0]["reason"])
        self.assertNotIn("BTC-USD", d["positions"])

    def test_no_trailing_before_the_gain_threshold(self):
        d = self.position()
        j._paper_apply(d, {"BTC-USD": market(103)})                               # solo +3%
        self.assertEqual(j._paper_apply(d, {"BTC-USD": market(99.8)}), [])          # cae 3.1% pero nunca llegó a +4%
        self.assertIn("BTC-USD", d["positions"])

    def test_drawdowns(self):
        self.assertEqual(pr.drawdowns([100, 120, 90, 110]), (25.0, 8.33, 120))
        self.assertEqual(pr.drawdowns([]), (0.0, 0.0, None))
        self.assertEqual(pr.drawdowns([100, float("nan"), -5, 100]), (0.0, 0.0, 100))

    def test_metrics_and_small_sample_warning(self):
        d = j._paper_new(1000)
        d["trades"] = [{"side": "sell", "pnl": 30.0}, {"side": "sell", "pnl": -10.0}, {"side": "buy"}]
        d["realized"], d["fees"] = 20.0, 5.0
        m = pr.metrics(d)
        self.assertEqual((m["closed_trades"], m["profit_factor"], m["expectancy"]), (2, 3.0, 10.0))
        self.assertEqual(m["fees_share_pct"], 20.0)
        self.assertFalse(m["sample_ok"])
        self.assertIn("Muestra chica", "\n".join(pr.metrics_lines(m)))

    def test_status_text_shows_risk_and_existing_pause(self):
        d = self.position(); d["last_run"] = j._now().isoformat(timespec="minutes")
        d["equity"] = [{"at": "2026-10-08T07:00-04:00", "v": 1000}, {"at": "2026-10-08T08:00-04:00", "v": 880}]
        d["risk"] = {"pause_reason": "drawdown"}
        j._papersave(d)
        text = j.paper_status_text()
        self.assertIn("caída máxima 12.00%", text)
        self.assertIn("Entradas en pausa", text)
        self.assertEqual(j.paper_status()["paused"], "drawdown")

    def test_chart_data_is_practice_only_and_bounded(self):
        d = self.position()
        d["equity"] = [{"at": f"2026-10-08T{h:02d}:00-04:00", "v": 1000 + h} for h in range(24)] * 20
        d["trades"] = [{"at": "2026-10-08T05:00-04:00", "side": "buy", "product": "BTC-USD", "pnl": None}]
        j._papersave(d)
        c = j.practica_chart()
        self.assertEqual(c["mode"], "practice")
        self.assertLessEqual(len(c["equity"]), pr.CHART_POINTS)
        self.assertEqual({p["product"] for p in c["products"]}, set(j.PAPER_PRODUCTS))
        self.assertIn("max_drawdown_pct", c["summary"])

    def test_limits_unchanged(self):
        import jarvis_v420 as v
        self.assertEqual((v.HARD_ORDER, v.HARD_DAY), (100.0, 300.0))
