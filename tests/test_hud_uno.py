"""El HUD (/hud, segundo monitor) como un solo panel.

El dueño señaló esta pantalla, no index.html: su título ya decía «PROTOCOLO DE INTERFAZ
AVANZADO». Eran seis cajas sueltas y los mismos siete números salían DOS veces —la tira de
tarjetas de arriba y los medidores de abajo—, y los dos botones hacían exactamente lo mismo
(POST /api/open con el mismo destino).

Comprobado además en un Chromium de verdad a 1920 y 3840 px: cabe en una pantalla sin scroll.
Eso no se puede repetir aquí sin navegador; esto vigila lo que sí se puede leer del archivo.
"""
import re
import unittest
from pathlib import Path

UI = Path(__file__).parents[1] / "desktop" / "ui"
HTML = (UI / "hud.html").read_text(encoding="utf-8")
CSS = (UI / "hud-uno.css").read_text(encoding="utf-8")
JS = {n: (UI / n).read_text(encoding="utf-8") for n in ("hud.js", "hudx.js")}
IDS = set(re.findall(r'id="([^"]+)"', HTML))


class NadaSePerdio(unittest.TestCase):
    def test_los_elementos_que_busca_el_javascript_siguen_ahi(self):
        faltan = {}
        for nombre, src in JS.items():
            busca = set(re.findall(r'\$\(\s*["\']([^"\']+)', src)) | \
                    set(re.findall(r'getElementById\(\s*["\']([^"\']+)', src))
            ausentes = sorted(i for i in busca if i not in IDS)
            if ausentes:
                faltan[nombre] = ausentes
        self.assertEqual(faltan, {}, f"el JavaScript del HUD busca lo que ya no existe: {faltan}")

    def test_ningun_id_repetido(self):
        todos = re.findall(r'id="([^"]+)"', HTML)
        self.assertEqual(sorted({i for i in todos if todos.count(i) > 1}), [])


class UnSoloPanel(unittest.TestCase):
    def test_los_siete_numeros_ya_no_salen_dos_veces(self):
        """La tira y los medidores mostraban lo mismo y hacían lo mismo al pulsarlos."""
        self.assertIn("body.hud-v2 #grid.strip { display: none !important; }", CSS)
        self.assertIn('id="hx-gauges"', HTML)            # el que se queda sigue existiendo

    def test_los_medidores_van_arriba_del_cuerpo(self):
        """Tienen que ser hermanos del marco, no hijos del bloque central: dentro de
        .command-deck el orden de la rejilla no les aplicaba y se quedaban abajo."""
        self.assertLess(HTML.index('id="hx-gauges"'), HTML.index('class="hudx-body"'))
        centro = HTML[HTML.index('class="command-deck'):HTML.index('</section>', HTML.index('class="command-deck'))]
        self.assertNotIn("hx-gauges", centro, "los medidores volvieron a quedar dentro del centro")

    def test_las_cajas_sueltas_se_funden_en_una_superficie(self):
        for regla in ("body.hud-v2 .hx-panel", "body.hud-v2 .command-deck"):
            bloque = re.search(re.escape(regla) + r"[^{]*\{([^}]*)\}", CSS)
            self.assertTrue(bloque, regla)
            self.assertIn("border: 0", bloque.group(1), f"{regla} conserva su borde propio")
        self.assertIn("body.hud-v2 .hx-panel::before", CSS)   # las esquinas sueltas se quitan

    def test_cabe_en_una_pantalla(self):
        """Un HUD de segundo monitor con scroll no sirve: no se mira, se vigila."""
        self.assertIn("height: calc(100vh - 56px)", CSS)
        self.assertIn("overflow-y: auto", CSS)                 # las columnas se desplazan por dentro
        self.assertIn("minmax(0, 1fr)", CSS)

    def test_la_hoja_nueva_se_carga_la_ultima(self):
        hojas = re.findall(r'<link rel="stylesheet" href="/ui/([^"?]+)', HTML)
        self.assertEqual(hojas[-1], "hud-uno.css")
        # Sin clase nueva en el body: una prueba de la suite exige ese atributo exacto, y
        # añadírsela la rompió. hud-uno.css solo lo carga esta página, así que basta hud-v2.
        self.assertIn('class="hud-page hud-v2"', HTML)
        self.assertNotIn("hud-uno\"", HTML.split("<body")[1][:80])


class EnIngles(unittest.TestCase):
    ACENTOS = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")

    def test_el_html_visible_no_tiene_espanol(self):
        visible = re.sub(r"<!--.*?-->", " ", HTML, flags=re.S)
        self.assertFalse(self.ACENTOS.search(visible), "quedó español en el HUD")
        self.assertEqual(re.search(r'<html lang="([^"]+)"', HTML).group(1), "en")
        self.assertIn("ADVANCED INTERFACE PROTOCOL", HTML)

    def test_los_textos_del_javascript_tampoco(self):
        """Los que se ven: etiquetas y notas. Los comentarios del código se quedan en español."""
        for nombre, src in JS.items():
            sin_comentarios = re.sub(r"//[^\n]*", " ", src)
            cadenas = re.findall(r'"([^"\n]*)"', sin_comentarios)
            malas = [c for c in cadenas if self.ACENTOS.search(c)]
            self.assertEqual(malas, [], f"{nombre}: {malas}")


if __name__ == "__main__":
    unittest.main()
