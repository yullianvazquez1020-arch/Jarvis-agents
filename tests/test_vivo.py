"""Los numeros vivos: que esten cableados y que el refresco no se quede en un minuto."""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
UI = RAIZ / "desktop" / "ui"
VIVO = (UI / "vivo.js").read_text(encoding="utf-8")
MERCADO_JS = (UI / "mercado.js").read_text(encoding="utf-8")
MERCADO_CSS = (UI / "mercado.css").read_text(encoding="utf-8")
MERCADO_HTML = (UI / "mercado.html").read_text(encoding="utf-8")
APP_PY = (RAIZ / "desktop" / "app.py").read_text(encoding="utf-8")


class Cableado(unittest.TestCase):
    def test_el_archivo_existe_se_sirve_y_se_carga(self):
        self.assertTrue((UI / "vivo.js").is_file())
        self.assertIn('"vivo.js": "text/javascript', APP_PY)
        self.assertIn("/ui/vivo.js", MERCADO_HTML)
        self.assertIn("/ui/vivo.js", (UI / "index.html").read_text(encoding="utf-8"))

    def test_se_carga_antes_de_mercado_js(self):
        # Si no, el primer dato se pinta sin que nadie lo este observando.
        self.assertLess(MERCADO_HTML.index("/ui/vivo.js"), MERCADO_HTML.index("/ui/mercado.js"))

    def test_los_numeros_de_la_barra_estan_seguidos(self):
        m = re.search(r'seguirTodo\("([^"]+)"\)', MERCADO_JS)
        self.assertIsNotNone(m, "mercado.js no sigue ningun numero")
        seguidos = {s.strip().lstrip("#") for s in m.group(1).split(",")}
        for ident in ("k-equity", "k-pnl", "k-dd", "k-win"):
            self.assertIn(ident, seguidos)
        for ident in seguidos:
            self.assertIn('id="%s"' % ident, MERCADO_HTML, "%s no existe en la pagina" % ident)

    def test_si_vivo_js_falta_la_pagina_sigue_funcionando(self):
        self.assertIn("if (window.JarvisVivo) {", MERCADO_JS)


class ElRefresco(unittest.TestCase):
    def test_ya_no_es_de_un_minuto(self):
        self.assertNotIn("setInterval(load, 60000)", MERCADO_JS)
        m = re.search(r"var VIVO_CADA = (\d+);", MERCADO_JS)
        self.assertIsNotNone(m)
        cada = int(m.group(1))
        self.assertLessEqual(cada, 15000, "sigue tardando demasiado en moverse")
        self.assertGreaterEqual(cada, 5000, "tan seguido no aporta y gasta bateria")

    def test_no_pide_nada_con_la_pestana_oculta(self):
        self.assertIn("if (!document.hidden) load();", MERCADO_JS)
        self.assertIn('document.addEventListener("visibilitychange"', MERCADO_JS)

    def test_dice_la_edad_real_del_dato_y_no_solo_actualizado(self):
        self.assertIn("state.ultimoDato = Date.now();", MERCADO_JS)
        self.assertIn("function pintarEdad()", MERCADO_JS)
        self.assertIn("vivo-viejo", MERCADO_JS)
        self.assertIn("vivo-viejo", MERCADO_CSS)
        # El punto late solo cuando el dato es reciente de verdad.
        self.assertIn("vivo-fresco", MERCADO_CSS)

    def test_respeta_a_quien_pidio_menos_movimiento(self):
        self.assertIn("prefers-reduced-motion", MERCADO_CSS)


class NoInventa(unittest.TestCase):
    def test_no_anima_si_el_texto_de_alrededor_cambio(self):
        self.assertIn("if (a.prefijo !== b.prefijo || a.sufijo !== b.sufijo || a.moneda !== b.moneda) return null;", VIVO)

    def test_no_pide_datos_ni_inventa_valores(self):
        codigo = re.sub(r"/\*.*?\*/", "", VIVO, flags=re.S)
        codigo = re.sub(r"//[^\n]*", "", codigo)
        for prohibido in ("fetch(", "XMLHttpRequest", "Math.random", "WebSocket"):
            self.assertNotIn(prohibido, codigo)

    def test_no_se_pelea_consigo_mismo(self):
        # El fallo que encontro el navegador: cada cuadro de la animacion se tomaba por un dato
        # nuevo y se animaba de vuelta. El numero acababa en el valor viejo.
        self.assertIn("el.__vivoUltimo = texto;", VIVO)
        self.assertIn("if (objetivo === el.__vivoUltimo) return;", VIVO)
        self.assertNotIn("__vivoEscribiendo", VIVO)


if __name__ == "__main__":
    unittest.main()
