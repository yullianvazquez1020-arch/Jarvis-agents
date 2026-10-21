"""Advanced Interface Protocol: las cuatro capas del panel, fundidas en una.

Antes había dos pantallas distintas: las tarjetas flotando sobre el cristal y, detrás del botón
«Paneles», otra con la conversación, seis pestañas y las alertas. El dueño pidió una sola, con
el núcleo en el centro.

Lo que vigila esta prueba es lo único que puede romperse al mover piezas de sitio: que ningún
elemento que el JavaScript busca desaparezca del HTML. Un `getElementById` que devuelve null no
da error en pantalla, simplemente deja de funcionar un botón y nadie se entera.

No comprueba que se vea bien: eso se miró en un Chromium de verdad (1920, 3840 y 1000 px de
ancho) y no se puede repetir aquí sin navegador.
"""
import re
import unittest
from pathlib import Path

UI = Path(__file__).parents[1] / "desktop" / "ui"
HTML = (UI / "index.html").read_text(encoding="utf-8")
AIP = (UI / "aip.css").read_text(encoding="utf-8")
GUIONES = ("app.js", "nucleo-home.js", "crystal.js", "crystal-motion.js", "lipsync.js", "mask.js")

IDS_HTML = set(re.findall(r'id="([^"]+)"', HTML))


def ids_que_busca(nombre):
    s = (UI / nombre).read_text(encoding="utf-8")
    return set(re.findall(r'getElementById\(\s*["\']([^"\']+)', s)) | set(re.findall(r'\$\(\s*["\']([^"\']+)', s))


class NadaSePerdio(unittest.TestCase):
    def test_ningun_elemento_que_busca_el_javascript_falta(self):
        """La prueba que justifica el cambio entero."""
        faltan = {}
        for g in GUIONES:
            ausentes = sorted(i for i in ids_que_busca(g) if i not in IDS_HTML
                              and i not in ("hands", "hud-negocio"))   # ya faltaban antes del cambio
            if ausentes:
                faltan[g] = ausentes
        self.assertEqual(faltan, {}, f"el JavaScript busca elementos que ya no existen: {faltan}")

    def test_estan_los_55_de_siempre(self):
        self.assertEqual(len(IDS_HTML), 55, "cambió el número de elementos; mira cuál se fue")
        for imprescindible in ("talk", "transcript", "send", "panel-lines", "panel-title", "alert-list",
                               "crystal-heard", "crystal-motion", "crystal-art", "estado", "paneles",
                               "mic-level", "mic-source", "st-clock", "pair-start", "claim"):
            self.assertIn(imprescindible, IDS_HTML, imprescindible)

    def test_las_pestanas_y_los_accesos_siguen_completos(self):
        self.assertEqual(len(re.findall(r'data-panel="', HTML)), 6)
        self.assertEqual(len(re.findall(r'data-launch="', HTML)), 3)
        self.assertIn('class="tabs"', HTML)          # crystal.js busca '.tabs button'

    def test_ningun_id_repetido(self):
        todos = re.findall(r'id="([^"]+)"', HTML)
        repetidos = sorted({i for i in todos if todos.count(i) > 1})
        self.assertEqual(repetidos, [], f"ids duplicados: {repetidos}")


class UnSoloPanel(unittest.TestCase):
    def test_el_marco_deja_el_centro_libre_para_el_cristal(self):
        self.assertIn('grid-template-areas: "top top top" "left core right" "bottom bottom bottom"', AIP)
        self.assertIn("pointer-events: none", AIP)   # el hueco no captura el ratón

    def test_las_capas_viejas_ya_no_se_ven(self):
        for vieja in (".crystal-cards", ".crystal-brand", "main.layout"):
            self.assertIn(vieja, AIP, f"{vieja} debería quedar oculta por aip.css")
        oculta = AIP[AIP.index("body.aip-on .crystal-cards"):][:200]
        self.assertIn("display: none !important", oculta)

    def test_estado_y_respuesta_no_salen_dos_veces(self):
        """#crystal-state/#crystal-reply dicen lo mismo que #state/#reply. Los cuatro siguen en
        el DOM porque dos scripts distintos los escriben, pero solo se ve una pareja."""
        self.assertIn("body.aip-on #crystal-state, body.aip-on #crystal-reply { display: none; }", AIP)
        for sigue in ("crystal-state", "crystal-reply", "state", "reply"):
            self.assertIn(sigue, IDS_HTML)
        self.assertNotIn("#crystal-heard { display: none", AIP)      # «last heard» es único

    def test_lo_fijado_por_otras_hojas_vuelve_a_la_rejilla(self):
        """`.foot` y `.paneles` son `position: fixed` en app.css y crystal.css: sin esto, la
        barra se montaba encima de las columnas y el botón se salía de la cabecera."""
        # Hay que mirar la regla PROPIA de cada uno, no la compartida que solo pinta el fondo.
        # (La primera versión de esta prueba buscaba el selector suelto y leía el bloque
        # equivocado: fallaba con el CSS correcto delante. El fallo era de la prueba.)
        for sel in ("body.aip-on .aip-bottom", "body.aip-on .aip-top .paneles"):
            bloques = re.findall(re.escape(sel) + r"\s*\{([^}]*)\}", AIP)
            self.assertTrue(bloques, f"no hay ninguna regla para {sel}")
            self.assertTrue(any("position: static" in b for b in bloques),
                            f"{sel} sigue fijado fuera de la rejilla")

    def test_aip_css_se_carga_el_ultimo(self):
        hojas = re.findall(r'<link rel="stylesheet" href="/ui/([^"?]+)', HTML)
        self.assertEqual(hojas[-1], "aip.css", "aip.css tiene que ir después para poder mandar")
        self.assertIn('class="nucleo-home aip-on"', HTML)

    def test_en_pantalla_estrecha_las_columnas_se_apilan(self):
        self.assertIn("@media (max-width: 1100px)", AIP)
        estrecho = AIP[AIP.index("@media (max-width: 1100px)"):][:420]
        self.assertIn('"top" "left" "right" "bottom"', estrecho)

    def test_el_panel_lleva_su_nombre(self):
        self.assertIn("ADVANCED INTERFACE PROTOCOL", HTML)

    def test_la_interfaz_quedo_en_ingles(self):
        """El dueño: «todo en inglés». El texto visible, no los comentarios."""
        visible = re.sub(r"<!--.*?-->", " ", HTML, flags=re.S)
        visible = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", visible, flags=re.S)
        for espanol in ("Hablar", "Micrófono de entrada", "Apagar micrófono", "Detener audio",
                        "Modo discreto", "Velocidad", "Conversación", "Paneles"):
            self.assertNotIn(espanol, visible, f"quedó «{espanol}» en pantalla")
        self.assertIn("Talk", visible); self.assertIn("Discreet mode", visible)
        self.assertEqual(re.search(r'<html lang="([^"]+)"', HTML).group(1), "en")


if __name__ == "__main__":
    unittest.main()
