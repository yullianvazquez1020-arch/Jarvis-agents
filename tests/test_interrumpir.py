"""Que la interrupción quede enganchada donde debe, y que no se pueda desenganchar sin darse cuenta.

El dueño, 19 oct: «no se deja interrumpir». La causa era una línea: play() apagaba el micrófono
para que Jarvis no se oyera a sí mismo.

La lógica de cuándo cortar se prueba aparte, con node (tests/test_interrumpir.cjs), porque es
donde está el riesgo de verdad: que Jarvis se calle solo al oír su propia voz.
"""
import re
import subprocess
import unittest
from pathlib import Path

RAIZ = Path(__file__).parents[1]
APP = (RAIZ / "desktop" / "ui" / "app.js").read_text(encoding="utf-8")
BARGE = (RAIZ / "desktop" / "ui" / "barge-in.js").read_text(encoding="utf-8")
HTML = (RAIZ / "desktop" / "ui" / "index.html").read_text(encoding="utf-8")
SERVER = (RAIZ / "desktop" / "app.py").read_text(encoding="utf-8")


class Enganchado(unittest.TestCase):
    def test_escucha_mientras_habla(self):
        play = APP[APP.index("function play(id, keepQ)"):][:400]
        self.assertIn("JarvisBargeIn.watch()", play, "play() ya no se queda escuchando")
        self.assertIn("stopMic(true)", play, "la captura normal debe seguir cerrándose")

    def test_deja_de_vigilar_cuando_calla(self):
        self.assertIn("JarvisBargeIn.stop()", APP)
        i = APP.index("JarvisBargeIn.stop()")
        self.assertIn("audioEl", APP[i:i + 200], "se para junto con el audio")

    def test_el_panel_expone_lo_justo(self):
        api = APP[APP.index("window.JarvisMicAPI"):][:400]
        for parte in ("warmStream", "startMic", "stopAudio"):
            self.assertIn(parte, api, parte)
        self.assertNotIn("chunks", api, "no se expone el audio capturado")

    def test_la_pagina_lo_carga_y_el_servidor_lo_sabe_servir(self):
        self.assertIn('src="/ui/barge-in.js', HTML)
        self.assertLess(HTML.index('/ui/app.js'), HTML.index('/ui/barge-in.js'),
                        "barge-in.js necesita que app.js ya haya definido JarvisMicAPI")
        self.assertIn('"barge-in.js": "text/javascript', SERVER,
                      "sin registrar, el servidor lo manda como JSON y el navegador lo rechaza")


class NoSePasaDeListo(unittest.TestCase):
    def test_no_graba_ni_manda_nada(self):
        for prohibido in ("fetch(", "XMLHttpRequest", "WebSocket", "MediaRecorder", "/api/"):
            self.assertNotIn(prohibido, BARGE, f"la vigilancia hace algo que no debe: {prohibido}")

    def test_se_puede_apagar_y_ajustar_sin_tocar_codigo(self):
        self.assertIn('"jarvis-barge"', BARGE)
        self.assertIn('"jarvis-barge-umbral"', BARGE)
        self.assertIn("function encendido()", BARGE)

    def test_tiene_los_tres_frenos(self):
        """Periodo de gracia, umbral y sostenido. Sin los tres, Jarvis se calla a sí mismo."""
        for freno in ("gracia", "umbral", "sostenido"):
            self.assertIn(freno, BARGE, freno)
        self.assertIn("echoCancellation", APP, "el navegador tiene que cancelar el eco")

    def test_suelta_el_audio_al_cortar(self):
        self.assertIn("function soltar()", BARGE)
        self.assertIn("ctx.close()", BARGE)
        self.assertIn("disconnect()", BARGE)


class ParaCalibrarEnSuMac(unittest.TestCase):
    def test_expone_el_nivel_medido(self):
        # Sin esto, ajustar el umbral es a ojo: no hay forma de saber cuanto mide su propia voz.
        js = (RAIZ / "desktop" / "ui" / "barge-in.js").read_text(encoding="utf-8")
        self.assertIn("ultimo = nivel;", js)
        self.assertIn("nivel: function () { return ultimo; }", js)
        self.assertIn("mirando: function () { return mirando; }", js)

    def test_el_umbral_de_localstorage_llega_al_decisor(self):
        # Ya funcionaba: el constructor usa ajuste() como valor por defecto. Esta prueba lo fija
        # para que nadie lo rompa al limpiar codigo que parece sin usar.
        js = (RAIZ / "desktop" / "ui" / "barge-in.js").read_text(encoding="utf-8")
        self.assertIn('ajuste("jarvis-barge-umbral"', js)
        self.assertIn("this.umbral = op.umbral != null ? op.umbral : ajuste(", js)


class LaLogica(unittest.TestCase):
    def test_las_nueve_comprobaciones_de_node(self):
        """Lo importante: que su propia voz NO lo corte. Se prueba con node."""
        r = subprocess.run(["node", str(RAIZ / "tests" / "test_interrumpir.cjs")],
                           capture_output=True, text=True, cwd=str(RAIZ))
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("9 comprobaciones OK", r.stdout)


if __name__ == "__main__":
    unittest.main()
