import json, time
from playwright.sync_api import sync_playwright

def chart(equity, precio):
    return {"summary": {"equity": 944.64, "pnl_total": -55.36, "pnl_pct": -5.54, "closed_trades": 8,
                        "win_rate_pct": 0, "max_drawdown_pct": 6.28, "drawdown_now_pct": 6.12},
            "start": 1000.0, "equity": equity,
            "products": [{"product": "BTC-USD", "rsi": 44, "trend": "lateral", "price": precio,
                          "change_24h_pct": -1.06, "open": False}]}

base = [{"t": 1760000000000 + i * 3600000, "v": 1000 - i * 0.23} for i in range(40)]
ESTADOS = [chart(base, 81530.73), chart(base, 81999.90),
           chart(base + [{"t": 1760000000000 + 40 * 3600000, "v": 944.64}], 82100.00)]

PRECIO = "() => { const e = document.querySelector('.ring .meta div:nth-child(3)'); return e ? e.textContent : null; }"

def muestrear(pg, expr, segundos=2.2, cada=0.05):
    vistos, t0 = [], time.time()
    while time.time() - t0 < segundos:
        v = pg.evaluate(expr)
        if not vistos or v != vistos[-1]:
            vistos.append(v)
        time.sleep(cada)
    return vistos

with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1500, "height": 900}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    estado = {"i": 0}
    pg.route("**/api/panels/practica", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"chart": ESTADOS[min(estado["i"], 2)], "demo": False})))
    pg.goto("http://127.0.0.1:8893/ui/mercado.html", wait_until="load"); time.sleep(2.0)
    print("precio inicial:", pg.evaluate(PRECIO))
    print("el lienzo se repinta solo:", (lambda a: (time.sleep(0.4), a != pg.evaluate("() => document.getElementById('chart').toDataURL().slice(-200)"))[1])(pg.evaluate("() => document.getElementById('chart').toDataURL().slice(-200)")))

    estado["i"] = 1
    pg.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    pasos = muestrear(pg, PRECIO)
    print("\nvalores por los que pasa el precio (%d):" % len(pasos))
    for v in pasos: print("   ", v)
    print("-> recorre el camino:" , len(pasos) > 2)

    estado["i"] = 2
    pg.evaluate("() => document.dispatchEvent(new Event('visibilitychange'))")
    anillo = muestrear(pg, "() => !!(window.__estado && window.__estado.puntoNuevo)", 3.0, 0.05)
    print("\nanillo del registro nuevo, estados por los que pasa:", anillo)
    print("-> se enciende y se apaga solo:", anillo[:3] == [False, True, False] or anillo[:2] == [True, False])
    print("\nerrores:", errs[:3] or "ninguno")
    b.close()
