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

    def test_frases_para_hablar_enseguida(self):
        self.assertEqual(app.speech_chunks("Good evening, sir. All systems are online. Ready."),
                         ["Good evening, sir.", "All systems are online. Ready."])
        self.assertEqual(app.speech_chunks("Hola"), ["Hola"])

    def test_calidad_y_ritmo(self):
        self.assertEqual(engines.DEFAULT_WPM, 170); self.assertEqual(engines.DANIEL_WPM, 170)
        self.assertIn("LEI16@44100", inspect.getsource(engines.MacSay.synthesize))

    def test_stop_during_first_synthesis_prevents_playback(self):
        import threading
        from types import SimpleNamespace
        c = app.Companion.__new__(app.Companion)
        c.lock = threading.RLock(); c.prefs = {"discreet": False, "rate": 1.0}; c.owner = "test"
        c._voz_gen = 0; c.audio = {}; c.last = {}; c._playback_native = lambda: False
        def synthesize(text, rate):
            c.stop_local_audio()
            return b"RIFFfake", "audio/wav"
        c.tts = SimpleNamespace(problem=lambda: "", synthesize=synthesize)
        c.emit = lambda event: self.fail("Cancelled speech must not emit audio")
        self.assertIsNone(c.speak("A response cancelled during synthesis."))
        self.assertEqual(c.audio, {})

    def test_navegador_cola_por_turno(self):
        js = (ROOT / "desktop/ui/app.js").read_text("utf-8")
        self.assertIn("playQ", js); self.assertNotIn("speechSynthesis", js)


if __name__ == "__main__":
    unittest.main()
