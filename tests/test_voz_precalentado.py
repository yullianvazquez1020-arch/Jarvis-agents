"""El precalentado de Whisper al arrancar el panel.

Por qué existe: el latencia.log del dueño (33 turnos reales, 15 y 16 de octubre) dice que los
primeros cuatro turnos tardan 6 669 ms en transcribir y los 29 siguientes 2 098 ms. El modelo
llega al caché del sistema con el primer turno de verdad, y ese turno lo paga el dueño.

Aquí no se mide tiempo —eso solo sale en su Mac, en el propio latencia.log—; se comprueba el
contrato: que se llame al arrancar, que transcriba algo generado (no el micrófono), que no
reviente si whisper no está, y que no espere a que termine.
"""
import os
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "desktop"))
import app as panel                                     # noqa: E402
from audio import wav                                   # noqa: E402

FUENTE = (Path(__file__).parents[1] / "desktop" / "app.py").read_text(encoding="utf-8")


class MotorFalso:
    """Un STT de pega: apunta lo que le dan y cuánto tardó en llamarse."""

    def __init__(self, problema="", tarda=0.0, estalla=False):
        self._problema = problema
        self.tarda = tarda
        self.estalla = estalla
        self.recibido = []
        self.listo = threading.Event()

    def problem(self):
        return self._problema

    def transcribe(self, datos, retain_dir=None):
        time.sleep(self.tarda)
        self.recibido.append(datos)
        self.listo.set()
        if self.estalla:
            raise RuntimeError("whisper falló")
        return {"text": "tono"}


class Precalentado(unittest.TestCase):
    def panel_con(self, motor):
        companion = object.__new__(panel.Companion)       # sin __init__: no hace falta el resto
        companion.stt = motor
        companion.lock = threading.RLock()               # el motor comparte el mismo candado que los turnos
        return companion

    def test_transcribe_un_tono_generado_no_el_microfono(self):
        motor = MotorFalso()
        self.panel_con(motor).prewarm_stt()
        self.assertTrue(motor.listo.wait(5), "el precalentado no llamó al STT")
        datos = motor.recibido[0]
        self.assertEqual(wav.check_wav(datos), 0.4)       # 0,4 s, el mínimo que acepta el motor
        self.assertTrue(wav.has_voice_energy(datos),
                        "sin energía el motor lo descarta y no se precalienta nada")

    def test_no_llama_al_stt_si_no_esta_configurado(self):
        motor = MotorFalso(problema="whisper.cpp no está instalado")
        self.panel_con(motor).prewarm_stt()
        time.sleep(0.2)
        self.assertEqual(motor.recibido, [], "precalentó con el motor sin configurar")

    def test_un_fallo_del_motor_no_tumba_el_panel(self):
        motor = MotorFalso(estalla=True)
        self.panel_con(motor).prewarm_stt()               # no debe propagar nada
        self.assertTrue(motor.listo.wait(5))

    def test_no_bloquea_el_arranque(self):
        """Si esperara, el panel tardaría en abrir lo que tarda Whisper en cargar."""
        motor = MotorFalso(tarda=2.0)
        inicio = time.monotonic()
        self.panel_con(motor).prewarm_stt()
        self.assertLess(time.monotonic() - inicio, 0.5, "prewarm_stt bloqueó el arranque")

    def test_el_panel_lo_llama_al_arrancar(self):
        self.assertIn("app.prewarm_stt()", FUENTE)
        self.assertLess(FUENTE.index("app.prewarm_tts()"), FUENTE.index("app.prewarm_stt()"))

    def test_el_resultado_se_descarta(self):
        """No se guarda ni se muestra: un tono no es una frase del dueño."""
        trozo = FUENTE[FUENTE.index("def prewarm_stt"):FUENTE.index("def prewarm_tts")]
        self.assertNotIn("self.turns", trozo)
        self.assertNotIn("emit", trozo)
        for prohibido in ("RawInputStream", "sounddevice", "micro"):
            self.assertNotIn(prohibido, trozo, "el precalentado no toca el micrófono")


if __name__ == "__main__":
    unittest.main()
