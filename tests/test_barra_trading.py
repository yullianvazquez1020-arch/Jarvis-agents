"""La barra de trading de /mercado.

El dueño mandó una captura de otro panel: «quiero que mi barra de trading se vea así», y
después «el diseño sí, el violeta no». O sea la disposición —tira de arriba, número grande del
día, fila de tarjetas— con su azul y negro de siempre.

Lo que vigila esta prueba: que no se invente ningún número y que no se rompa nada de lo que ya
funcionaba. Cómo se ve se comprobó en un Chromium de verdad (1600 y 480 px, y con los casos
sin datos); eso no se puede repetir aquí sin navegador.
"""
import re
import unittest
from pathlib import Path

UI = Path(__file__).parents[1] / "desktop" / "ui"
HTML = (UI / "mercado.html").read_text(encoding="utf-8")
CSS = (UI / "mercado-barra.css").read_text(encoding="utf-8")
JS = (UI / "mercado-barra.js").read_text(encoding="utf-8")
BASE = (UI / "mercado.js").read_text(encoding="utf-8")
IDS = set(re.findall(r'id="([^"]+)"', HTML))


class NadaSePerdio(unittest.TestCase):
    def test_los_medidores_viejos_siguen_en_la_pagina(self):
        """mercado.js los escribe. Si desaparecen, renderSummary revienta a media carga."""
        for viejo in ("k-equity", "k-pnl", "k-dd", "k-ddnow", "k-pf", "k-win", "k-n", "k-exp", "k-fees"):
            self.assertIn(viejo, IDS, viejo)

    def test_todo_lo_que_busca_mercado_js_existe(self):
        busca = set(re.findall(r'\$\(\s*["\']([^"\']+)', BASE))
        self.assertEqual(sorted(i for i in busca if i not in IDS), [])

    def test_ningun_id_repetido(self):
        todos = re.findall(r'id="([^"]+)"', HTML)
        self.assertEqual(sorted({i for i in todos if todos.count(i) > 1}), [])


class SinInventarNada(unittest.TestCase):
    def test_la_barra_no_pide_nada_a_la_red(self):
        """Lee lo que mercado.js ya trajo. Ni fetch, ni XHR, ni WebSocket."""
        for prohibido in ("fetch(", "XMLHttpRequest", "WebSocket", "import(", "coingecko", "finnhub"):
            self.assertNotIn(prohibido, JS, f"la barra salió a la red: {prohibido}")

    def test_lo_que_falta_dice_que_falta(self):
        """Ningún hueco se rellena con un cero o un número de ejemplo."""
        self.assertIn('"—"', JS)
        self.assertIn("sin registro de hoy", JS)
        self.assertIn("sin lectura de 24 h todavía", JS)
        self.assertIn("function num(v)", JS)
        self.assertIn("isFinite", JS)          # un NaN o un null nunca llega a pantalla

    def test_dice_de_donde_salen_los_numeros(self):
        self.assertIn("Dinero simulado", HTML)
        self.assertIn("Precios públicos de Coinbase", HTML)
        self.assertIn("Nunca toca dinero real", HTML)

    def test_sigue_siendo_solo_lectura(self):
        """Buscar la palabra «orden» no servía: hay una variable que se llama así. Lo que importa
        es que no exista ninguna forma de ACTUAR."""
        for prohibido in ("/api/open", "POST", "credentials:", ".submit(", "location ="):
            self.assertNotIn(prohibido, JS, f"la barra puede actuar: {prohibido}")


class ColorYLectura(unittest.TestCase):
    def test_sin_violeta(self):
        """«El diseño sí, el violeta no». Se miran los VALORES de color, no los comentarios:
        la primera versión de esta prueba fallaba por la palabra «violeta» de un comentario."""
        sin_comentarios = re.sub(r"/\*.*?\*/", " ", CSS, flags=re.S).lower()
        for morado in ("purple", "violet", "magenta", "#8b5cf6", "#a855f7", "#7c3aed", "#6d28d9"):
            self.assertNotIn(morado, sin_comentarios, morado)
        for h in re.findall(r"#([0-9a-f]{6})", sin_comentarios):
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            self.assertFalse(b > 110 and r > 110 and g < min(r, b) - 40,
                             f"#{h} tira a morado")

    def test_el_color_nunca_va_solo(self):
        """Verde y rojo son el par que peor distingue un daltónico: cada número lleva flecha
        y signo, así que el dato se lee sin ver el color."""
        self.assertIn("▲", JS); self.assertIn("▼", JS)
        self.assertIn('(v > 0 ? "+" : "")', JS)
        self.assertIn("el color no puede ser el único aviso", JS)

    def test_usa_los_tokens_que_ya_existian(self):
        for token in ("var(--ink)", "var(--ink-2)", "var(--ink-3)", "var(--panel)", "var(--rule)"):
            self.assertIn(token, CSS, token)
        self.assertIn("--loss:var(--sell)", CSS)      # el rojo es el que ya usaba la venta

    def test_una_sola_serie_no_lleva_leyenda(self):
        """La línea del capital es una sola serie: el título la nombra y no hace falta leyenda."""
        self.assertIn("CAPITAL · ÚLTIMOS REGISTROS", HTML)
        self.assertIn('aria-label="Curva del capital simulado"', HTML)


class NoEstorbaALoQueYaFuncionaba(unittest.TestCase):
    def test_si_la_barra_falla_la_pagina_sigue(self):
        self.assertIn("try { pintarTodo(ch); } catch", JS)

    def test_el_enganche_es_una_linea_en_mercado_js(self):
        self.assertIn("window.JarvisBarra.pintar(p.chart)", BASE)
        self.assertEqual(BASE.count("window.JarvisBarra.pintar"), 1)

    def test_un_solo_registro_ya_no_tumba_la_curva(self):
        """Fallo viejo de mercado.js que la barra destapó: con UN punto, Math.max(1, …) daba
        last = 1 y el bucle leía pts[1], que no existe."""
        self.assertIn("Math.min(n - 1, Math.max(1, Math.floor((n - 1) * grow)))", BASE)
        self.assertNotIn("last = Math.max(1, Math.floor((n - 1) * grow))", BASE)

    def test_la_hoja_nueva_se_carga_despues(self):
        hojas = re.findall(r'<link rel="stylesheet" href="/ui/([^"?]+)', HTML)
        self.assertEqual(hojas[-1], "mercado-barra.css")


if __name__ == "__main__":
    unittest.main()
