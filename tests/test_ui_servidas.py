"""Todo archivo que piden las paginas tiene que estar en UI_FILES del servidor.

Por que existe: desktop/app.py sirve /ui/<archivo> SOLO si el nombre esta en el diccionario
UI_FILES. Lo que no esta se devuelve como JSON, y el navegador lo rechaza por nosniff:

    The resource from ".../ui/aip.css?v=1" was blocked due to MIME type ("application/json")
    mismatch (X-Content-Type-Options: nosniff)

Paso de verdad. aip.css estaba en el disco, el HTML la pedia, el CSS era correcto, y la
pantalla del dueno llevaba DIAS sin columnas. No lo vi porque la probe con un servidor que
adivina el tipo por la extension; el suyo no adivina, y hace bien.

Esta prueba lee cada pagina, saca lo que pide, y exige que el servidor sepa servirlo.
"""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).parents[1]
UI = RAIZ / "desktop" / "ui"
APP = (RAIZ / "desktop" / "app.py").read_text(encoding="utf-8")

PAGINAS = ["index.html", "hud.html", "mercado.html", "avatar.html", "nucleo.html",
           "orbe.html", "torre.html", "ironman.html"]
PEDIDO = re.compile(r'(?:href|src)="/ui/([^"?#]+)')


def registrados():
    inicio = APP.index("UI_FILES = {")
    fin = APP.index("\n", APP.index("}", inicio))
    return set(re.findall(r'"([^"]+\.[a-z0-9]+)"\s*:', APP[inicio:fin]))


class ServidasDeVerdad(unittest.TestCase):
    def test_todo_lo_que_piden_las_paginas_esta_registrado(self):
        reg, faltan = registrados(), {}
        for pagina in PAGINAS:
            ruta = UI / pagina
            if not ruta.is_file():
                continue
            pide = set(PEDIDO.findall(ruta.read_text(encoding="utf-8")))
            ausentes = sorted(a for a in pide if a not in reg)
            if ausentes:
                faltan[pagina] = ausentes
        self.assertEqual(faltan, {}, "el servidor los devolveria como JSON y el navegador "
                                     "los rechazaria: " + repr(faltan))

    def test_los_cuatro_que_fallaron_estan(self):
        """Prueba de regresion del caso concreto."""
        reg = registrados()
        for f in ("aip.css", "hud-uno.css", "mercado-barra.css", "mercado-barra.js"):
            self.assertIn(f, reg, f)

    def test_el_tipo_corresponde_a_la_extension(self):
        inicio = APP.index("UI_FILES = {")
        fin = APP.index("\n", APP.index("}", inicio))
        bloque = APP[inicio:fin]
        esperado = {".css": "text/css", ".js": "text/javascript", ".jpg": "image/jpeg",
                    ".png": "image/png", ".wav": "audio/wav", ".svg": "image/svg+xml"}
        for nombre, tipo in re.findall(r'"([^"]+\.[a-z0-9]+)"\s*:\s*"([^"]+)"', bloque):
            ext = "." + nombre.rsplit(".", 1)[1]
            if ext in esperado:
                self.assertTrue(tipo.startswith(esperado[ext]),
                                f"{nombre} se sirve como {tipo}")

    # Estos cuatro llegaron a la Mac del dueno en una entrega aparte y no viven en esta rama.
    # Se registran a proposito para que el servidor sepa servirlos ALLI. Si alguno se anade
    # alguna vez a esta rama, hay que sacarlo de esta lista: la prueba de abajo lo exige.
    FUERA_DE_ESTA_RAMA = ("aip.css", "hud-uno.css", "mercado-barra.css", "mercado-barra.js")

    def test_todo_lo_registrado_existe_en_el_disco_salvo_lo_declarado(self):
        faltan = [f for f in registrados()
                  if not (UI / f).is_file() and f not in self.FUERA_DE_ESTA_RAMA]
        self.assertEqual(faltan, [], f"registrados pero no estan en desktop/ui/: {faltan}")

    def test_la_lista_de_excepciones_no_se_queda_vieja(self):
        # Una excepcion que ya no hace falta esconde el proximo archivo que falte de verdad.
        sobran = [f for f in self.FUERA_DE_ESTA_RAMA if (UI / f).is_file()]
        self.assertEqual(sobran, [], f"ya estan en el disco, saquelos de FUERA_DE_ESTA_RAMA: {sobran}")

    def test_lo_que_falta_del_disco_no_tumba_el_servidor(self):
        # Es la unica razon por la que registrar algo ausente es aceptable: el 404 limpio.
        py = (RAIZ / "desktop" / "app.py").read_text(encoding="utf-8")
        self.assertIn("except OSError:", py)


    def test_un_nombre_sin_archivo_da_404_y_no_500(self):
        # read_bytes() sin proteger reventaba el servidor con 500 si el nombre estaba
        # registrado y el archivo no estaba en el disco. Es justo lo que pasa a medio instalar.
        py = (RAIZ / "desktop" / "app.py").read_text(encoding="utf-8")
        self.assertIn('return self._send(404, {"error": "no existe"})   # registrado pero sin archivo', py)
        self.assertNotIn('return self._send(200, (HERE / "ui" / u.path[4:]).read_bytes()', py)


if __name__ == "__main__":
    unittest.main()
