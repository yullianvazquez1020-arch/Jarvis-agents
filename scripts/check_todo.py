import time
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={"width": 1400, "height": 800}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: errs.append("consola: " + m.text) if m.type == "error" else None)
    pg.goto("http://127.0.0.1:8896/todo", wait_until="load"); time.sleep(0.8)
    def visible():
        return pg.evaluate("""() => {
          const f = [...document.querySelectorAll('iframe')].find(x => !x.hidden);
          if (!f) return null;
          try { return f.contentWindow.__quien || '(sin cargar)'; } catch (e) { return 'BLOQUEADO: ' + e.message; }
        }""")
    print("al abrir  ->", visible(), "| pestaña:", pg.evaluate("() => JarvisTodo.actual()"))
    for tecla, esperado in (("2", "hud"), ("3", "mercado"), ("4", "core"), ("1", "panel")):
        pg.keyboard.press(tecla); time.sleep(0.6)
        v = visible()
        print("tecla %s   -> %-10s %s" % (tecla, v, "OK" if v == esperado else "MAL, esperaba " + esperado))
    print("marcos abiertos:", pg.evaluate("() => JarvisTodo.abiertas()"))
    # Volver a una ya abierta NO debe recargarla: el contador se quedaria en 1.
    pg.keyboard.press("2"); time.sleep(0.4); pg.keyboard.press("1"); time.sleep(0.5)
    print("veces que se cargo el panel:", pg.evaluate("""() => {
      const f = [...document.querySelectorAll('iframe')].find(x => !x.hidden);
      return f.contentWindow.__contador;
    }"""))
    print("permiso de microfono en el panel:", pg.evaluate("""() => {
      const f = [...document.querySelectorAll('iframe')].find(x => !x.hidden);
      return f.getAttribute('allow');
    }"""))
    pg.screenshot(path="/tmp/todoprueba/una-pestana.png")
    print("errores:", errs[:4] or "ninguno")
    b.close()
