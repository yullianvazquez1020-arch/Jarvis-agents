"""Un solo interruptor de idioma: JARVIS_REPLY_LANGUAGE.

El dueño (17 de octubre): «has que todo sea en inglés, yo soy full english, que me entienda en
inglés y responda en inglés». El problema no era cambiar un sitio: el idioma estaba escrito a
mano en CUATRO, y no coincidían entre ellos.

  1. main.py, instrucción de voz ..... "Latin American Spanish" fijo
  2. main.py, instrucción del sistema . PERSONALIDAD.md está en español y el modelo lo imitaba
  3. jarvis_chat_voice.py ............. notas de Telegram con detección automática
  4. desktop/app.py ................... el panel no fijaba VOICE_STT_LANGUAGE, caía en "auto"

Se lee con ast y texto: main.py necesita fastapi y aquí no está, y justamente por eso conviene
que esta prueba no dependa de importarlo.
"""
import ast
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).parents[1]
MAIN = (RAIZ / "main.py").read_text(encoding="utf-8")
PANEL = (RAIZ / "desktop" / "app.py").read_text(encoding="utf-8")
VOZ_TG = (RAIZ / "jarvis_chat_voice.py").read_text(encoding="utf-8")

sys.path.insert(0, str(RAIZ / "desktop"))
from audio import engines                                   # noqa: E402


def constante(fuente, nombre):
    for n in ast.parse(fuente).body:
        if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == nombre for t in n.targets):
            return ast.get_source_segment(fuente, n.value)
    raise AssertionError(f"falta {nombre}")


class UnSoloInterruptor(unittest.TestCase):
    def test_el_ingles_es_lo_de_por_defecto(self):
        """Lo que pidió el dueño. Y un es-* lo devuelve al español sin tocar código."""
        for fuente, nombre in ((MAIN, "REPLY_LANG"), (VOZ_TG, "DEFAULT_STT_LANG")):
            expr = constante(fuente, nombre)
            self.assertIn('"en-GB"', expr, "el valor por defecto ya no es inglés")
            self.assertIn("JARVIS_REPLY_LANGUAGE", expr)
            self.assertIn('startswith("es")', expr, "un es-* tiene que devolverlo al español")

    def test_los_cuatro_sitios_leen_la_misma_variable(self):
        self.assertIn("JARVIS_REPLY_LANGUAGE", MAIN)
        self.assertIn("JARVIS_REPLY_LANGUAGE", VOZ_TG)
        self.assertIn("JARVIS_REPLY_LANGUAGE", PANEL)
        self.assertIn("JARVIS_REPLY_LANGUAGE", (RAIZ / "desktop" / "audio" / "engines.py").read_text("utf-8"))

    def test_el_idioma_hablado_ya_no_esta_escrito_a_mano(self):
        self.assertIn("SPEECH_STYLE", MAIN)
        voz = MAIN[MAIN.index("VOICE QUERY: read-only"):][:900]
        self.assertIn("+ SPEECH_STYLE +", voz)
        self.assertNotIn("Latin American Spanish", voz, "el idioma volvió a quedar fijo en la voz")

    def test_hay_estilo_para_los_dos_idiomas(self):
        estilo = constante(MAIN, "SPEECH_STYLE")
        self.assertIn("British English", estilo)
        self.assertIn("Latin American Spanish", estilo)

    def test_la_regla_de_idioma_va_despues_de_la_personalidad(self):
        """PERSONALIDAD.md está escrito en español y el modelo lo imita. La regla tiene que ir
        después para ganarle; si se pone antes, no sirve de nada."""
        self.assertIn("PERSONALITY_PROMPT + LANGUAGE_RULE", MAIN)
        regla = constante(MAIN, "LANGUAGE_RULE")
        self.assertIn("always answer in English", regla)
        self.assertIn("written in", regla)                   # menciona el archivo en español

    def test_el_panel_fija_el_idioma_del_reconocimiento(self):
        self.assertIn('"VOICE_STT_LANGUAGE": "en"', PANEL)


class NotasDeTelegram(unittest.TestCase):
    def test_el_idioma_se_resuelve_en_el_proceso_padre(self):
        """El trabajador de Whisper corre aparte y NO recibe estas variables (_SAFE_ENV no las
        incluye). Resolverlo dentro del trabajador lo habría roto: solo importa json, resource
        y sys. Me pasó al escribir esto y por eso está la prueba."""
        inicio = VOZ_TG.index("_WORKER = r\"\"\"")
        fin = VOZ_TG.index("\"\"\"", inicio + 14)
        trabajador = VOZ_TG[inicio:fin]
        self.assertNotIn("JARVIS_REPLY_LANGUAGE", trabajador)
        self.assertNotIn("os.getenv", trabajador)
        self.assertNotIn("import os", trabajador)
        self.assertIn("language = DEFAULT_STT_LANG", VOZ_TG[fin:])

    def test_ya_no_adivina_el_idioma_por_defecto(self):
        firma = VOZ_TG[VOZ_TG.index("async def transcribe_local_detect"):][:600]
        self.assertIn('language: str = ""', firma)
        self.assertIn('if language in ("", "auto", None)', firma)

    def test_un_idioma_explicito_sigue_mandando(self):
        firma = VOZ_TG[VOZ_TG.index("async def transcribe_local_detect"):][:600]
        self.assertNotIn('language = "en"', firma, "no puede pisar un es/en pedido a propósito")


class VozDelPanel(unittest.TestCase):
    def test_con_ingles_configurado_lo_dudoso_se_lee_en_ingles(self):
        with patch.dict(os.environ, {"JARVIS_REPLY_LANGUAGE": "en-GB"}):
            self.assertEqual(engines.preferred_lang(), "en")
            self.assertEqual(engines.detect_lang("ok"), "en")
            self.assertEqual(engines.detect_lang("¿Cómo está?"), "es")   # una señal clara gana

    def test_y_al_reves_si_vuelve_al_espanol(self):
        with patch.dict(os.environ, {"JARVIS_REPLY_LANGUAGE": "es-PR"}):
            self.assertEqual(engines.detect_lang("ok"), "es")
            self.assertEqual(engines.detect_lang("Good morning sir"), "en")


if __name__ == "__main__":
    unittest.main()
