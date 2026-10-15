"""Una sola voz a la vez, inglés primero, baja latencia (PR fix/voz-una-sola)."""
import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
import app  # noqa: E402
from audio import engines  # noqa: E402


class UnaSolaVoz(unittest.TestCase):
    def test_sin_saludo_say_paralelo_al_arrancar(self):
        # Causa raíz: main() lanzaba `say -v Juan` en español mientras /api/greet decía el saludo inglés.
        src = inspect.getsource(app.main)
        self.assertNotIn("_announce_focus(", src)
        self.assertNotIn('"say"', src)

    def test_ingles_por_defecto(self):
        self.assertEqual(engines.detect_lang("Systems online"), "en")
        self.assertEqual(engines.detect_lang("ok"), "en")
        self.assertEqual(engines.detect_lang("¿Cómo estás?"), "es")
        self.assertIn("ENGLISH", (ROOT / "jarvis_desktop_api.py").read_text("utf-8"))

    def test_frases_para_hablar_enseguida(self):
        self.assertEqual(app.speech_chunks("Good evening, sir. All systems are online. Ready."),
                         ["Good evening, sir.", "All systems are online. Ready."])
        self.assertEqual(app.speech_chunks("Hola"), ["Hola"])

    def test_calidad_y_ritmo(self):
        self.assertEqual(engines.DEFAULT_WPM, 160); self.assertEqual(engines.DANIEL_WPM, 160)
        self.assertIn("LEI16@44100", inspect.getsource(engines.MacSay.synthesize))

    def test_navegador_cola_por_turno(self):
        js = (ROOT / "desktop/ui/app.js").read_text("utf-8")
        self.assertIn("playQ", js); self.assertNotIn("speechSynthesis", js)


if __name__ == "__main__":
    unittest.main()
