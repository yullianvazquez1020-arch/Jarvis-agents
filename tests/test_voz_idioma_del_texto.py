"""La voz sigue al idioma del texto.

Por qué: el 17 de octubre el dueño escribió «the voice responds quick but I can't understand
him». No era la velocidad. Sus respuestas llegan en español —se ve en su propia captura del
panel— y las leía Daniel, la voz inglesa, porque resolve_voice devolvía siempre la inglesa.
Un texto en español leído con fonética inglesa no se entiende.

Esto invierte una decisión anterior (PR #116, «solo inglés»), a petición del dueño.
"""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "desktop"))
from audio import engines                                  # noqa: E402

LAS_DOS = type("L", (), {"stdout": "Juan es_MX # Hola\nDaniel en_GB # Hello\nMonica es_ES # Hola\n"})()
SOLO_ES = type("L", (), {"stdout": "Juan es_MX # Hola\nMonica es_ES # Hola\n"})()
SOLO_EN = type("L", (), {"stdout": "Daniel en_GB # Hello\nSamantha en_US # Hi\n"})()

# Frases reales del panel del dueño, de su captura del 17 de octubre.
SUYAS = ["La cuenta de Claude se quedó sin saldo. Tu historial se conservó.",
         "Hay que recargar los créditos de la API. Cambiar el modelo no lo arregla.",
         "Para retomar los negocios sin usar IA: /negocios, /ingresosplan, /tienda."]


def voz(texto, listado=LAS_DOS, config=""):
    with patch.object(engines.subprocess, "run", return_value=listado), \
            patch.dict(os.environ, {"JARVIS_REPLY_LANGUAGE": config}):
        return engines.MacSay().resolve_voice(texto)


class IdiomaDelTexto(unittest.TestCase):
    def test_las_frases_reales_del_panel_se_leen_en_espanol(self):
        for frase in SUYAS:
            self.assertEqual(voz(frase), "Juan", frase)

    def test_el_ingles_sigue_leyendose_en_ingles(self):
        for frase in ("Good morning, sir. All systems are online.",
                      "The quarterly numbers look healthy today."):
            self.assertEqual(voz(frase), "Daniel", frase)

    def test_una_voz_personalizada_se_respeta_en_los_dos_idiomas(self):
        with patch.object(engines.subprocess, "run", return_value=LAS_DOS):
            v = engines.MacSay("Oliver")
            self.assertEqual((v.resolve_voice("Hola señor"), v.resolve_voice("Hello sir")),
                             ("Oliver", "Oliver"))

    def test_si_falta_la_voz_del_idioma_usa_la_otra_en_vez_de_callarse(self):
        self.assertEqual(voz("Hola señor, ¿cómo está?", SOLO_EN), "Daniel")
        self.assertEqual(voz("Good morning, sir.", SOLO_ES), "Juan")

    def test_sin_ninguna_voz_masculina_avisa(self):
        vacio = type("L", (), {"stdout": "Paulina es_MX # Hola\nSamantha en_US # Hi\n"})()
        with self.assertRaises(engines.EngineError):
            voz("Hola", vacio)

    def test_nunca_elige_una_voz_femenina(self):
        con_mujer = type("L", (), {"stdout": "Paulina es_MX # Hola\nJuan es_MX # Hola\n"})()
        self.assertEqual(voz("Hola señor", con_mujer), "Juan")


class TextoSinSenal(unittest.TestCase):
    """«ok», «3», «» no dicen de qué idioma son. Antes caían en inglés siempre."""

    def test_manda_el_idioma_configurado(self):
        for texto in ("ok", "3", "", "   ", "mmm"):
            self.assertEqual(voz(texto, config="es-PR"), "Juan", texto)
            self.assertEqual(voz(texto, config="en-GB"), "Daniel", texto)

    def test_una_senal_clara_gana_a_la_configuracion(self):
        self.assertEqual(voz("¿Cómo está, señor?", config="en-GB"), "Juan")
        self.assertEqual(voz("How much money have we made today?", config="es-PR"), "Daniel")

    def test_preferred_lang_lee_la_variable(self):
        for valor, espera in (("es", "es"), ("es-PR", "es"), ("es_MX", "es"),
                              ("en-GB", "en"), ("", "en"), ("fr", "en")):
            with patch.dict(os.environ, {"JARVIS_REPLY_LANGUAGE": valor}):
                self.assertEqual(engines.preferred_lang(), espera, valor)


class ElOtroCamino(unittest.TestCase):
    """desktop/voz_loop.py construye el comando `say` por su cuenta: mismo criterio."""

    def comando(self, texto, listado=LAS_DOS):
        sys.path.insert(0, str(Path(__file__).parents[1] / "desktop"))
        import voz_loop
        voz_loop.Speaker._listing = None
        with patch.dict(os.environ, {"PIPER_MODEL": "", "JARVIS_SAY_VOICE": ""}), \
                patch.object(voz_loop.subprocess, "run", return_value=listado):
            cmd = voz_loop.Speaker().command(texto)
        voz_loop.Speaker._listing = None
        return cmd[:3]

    def test_los_dos_caminos_coinciden(self):
        self.assertEqual(self.comando("La cuenta se quedó sin saldo"), ["say", "-v", "Juan"])
        self.assertEqual(self.comando("Good morning, sir."), ["say", "-v", "Daniel"])

    def test_sin_voz_del_idioma_usa_la_otra(self):
        self.assertEqual(self.comando("Hola señor", SOLO_EN), ["say", "-v", "Daniel"])


if __name__ == "__main__":
    unittest.main()
