import time
from playwright.sync_api import sync_playwright
LEER = "(id) => { const e = document.getElementById(id); return {t: e.textContent, c: e.className}; }"
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8897/p.html", wait_until="load")
    pg.evaluate("() => window.__set('k-equity', '$951.20')")
    time.sleep(0.25)
    medio = pg.evaluate(LEER, "k-equity")
    time.sleep(1.0)
    fin = pg.evaluate(LEER, "k-equity")
    print("subida  · a mitad:", medio["t"], "| clase:", medio["c"], "| al final:", fin["t"])
    pg.evaluate("() => window.__set('k-pnl', '-$58.10 (-5.44 %)')")
    time.sleep(0.25); m2 = pg.evaluate(LEER, "k-pnl")
    time.sleep(1.0); f2 = pg.evaluate(LEER, "k-pnl")
    print("bajada  · a mitad:", m2["t"], "| clase:", m2["c"], "| al final:", f2["t"])
    pg.evaluate("() => window.__set('k-n', '9 operación(es) cerrada(s)')")
    time.sleep(1.0)
    print("entero  · al final:", pg.evaluate(LEER, "k-n")["t"])
    pg.evaluate("() => window.__set('k-dd', '6.28%')")
    time.sleep(0.8)
    print("sin numero antes · al final:", pg.evaluate(LEER, "k-dd")["t"])
    pg.evaluate("() => window.__set('k-equity', 'No disponible')")
    time.sleep(0.5)
    print("a texto · al final:", pg.evaluate(LEER, "k-equity")["t"])
    print("errores:", errs[:3] or "ninguno")
    b.close()
