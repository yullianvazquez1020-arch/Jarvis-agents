"""Órdenes de pantalla por voz: la frase del dueño se convierte en una orden que el ejecutor ya acepta.

Aquí no se mueve ningún mouse ni se abre ninguna app: el puente está sustituido y el validador del ejecutor se
usa solo para comprobar que lo que la voz produce cae dentro de su lista segura. Datos ficticios.
"""
import logging
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_agent_executor import ae                                   # el validador de verdad, sin tocarlo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
import app as desk                                                   # noqa: E402
import intents                                                       # noqa: E402

# Lo que el dueño dice y la orden que debe salir. Una fila por forma de decirlo que ya usa.
FRASES = {
    "Jarvis, abre Safari": {"action": "open_app", "app": "Safari"},
    "abre notas": {"action": "open_app", "app": "Notes"},
    "Abre Outlook": {"action": "open_app", "app": "Microsoft Outlook"},
    "ábreme la app Slack": {"action": "open_app", "app": "Slack"},
    "abre github": {"action": "open_url", "url": "https://github.com"},
    "ve a github": {"action": "open_url", "url": "https://github.com"},
    "baja": {"action": "scroll", "dy": -intents.MOUSE_SCROLL},
    "sigue bajando": {"action": "scroll", "dy": -intents.MOUSE_SCROLL},
    "desplázate hacia abajo": {"action": "scroll", "dy": -intents.MOUSE_SCROLL},
    "sube": {"action": "scroll", "dy": intents.MOUSE_SCROLL},
    "desplázate arriba": {"action": "scroll", "dy": intents.MOUSE_SCROLL},
    "tómame una captura de pantalla": {"action": "screenshot"},
    "hazme un pantallazo": {"action": "screenshot"},
    "mira la pantalla": {"action": "screenshot"},
    "¿qué hay en la pantalla?": {"action": "screenshot"},
    "espera 5 segundos": {"action": "wait", "seconds": 5},
    "espera 1 segundo": {"action": "wait", "seconds": 1},
}

# Frases que NO deben convertirse en una orden de pantalla, y qué debe pasar con ellas.
NO_MOUSE = {
    "abre el micrófono": "mic_on",            # ya existía: no se lo puede robar la tabla del mouse
    "apaga el micrófono": "mic_off",
    "abre práctica": "panel",                 # los paneles siguen ganando
    "abre la agenda": "panel",
    "muéstrame los cobros": "panel",
    "silencio": "stop_audio",
    "para el mouse": "stop_mouse",            # la parada sigue siendo parada, no una orden
    "repite": "repeat",
    "borra el recordatorio": "refuse",
    "aprueba la orden 2": "refuse",
    "confirma 123456": "refuse",
    "envíale el correo a Ana": "refuse",
    "compra 100 de bitcoin": "refuse",
    "¿cuánto me deben?": "server",            # las preguntas siguen yendo a Jarvis
    "¿cómo van los trabajos de Ana?": "server",
    "abre el banco": "server",                # fuera de la lista: no se inventa una orden
    "abre facebook": "server",
    "abre la Terminal": "server",
}

# Por voz no se produce nada que necesite una coordenada o un texto que habría que inventar.
PROHIBIDAS = {"click", "double_click", "move", "type", "hotkey"}
TENTACIONES = ("haz clic aquí", "haz doble clic en el botón azul", "mueve el mouse al botón",
               "clic en aceptar", "escribe mi contraseña", "escribe hola en las notas",
               "pon el cursor sobre el enlace", "dale enter", "presiona command q")


class Tabla(unittest.TestCase):
    def test_conversacion_no_acciona_pantalla(self):
        for texto in ("la demanda baja", "el precio sube", "no abre Safari", "no baja",
                      "si digo baja que haces", "abre Safari y luego Slack",
                      "no mira la pantalla", "ella espera 5 segundos", "abre github falso"):
            with self.subTest(texto=texto):
                self.assertEqual(intents.parse(texto)[0], "server")

    def test_cortesia_conserva_orden_completa(self):
        for texto in ("por favor baja", "baja por favor", "Jarvis, por favor baja por favor"):
            self.assertEqual(intents.parse(texto), ("mouse", {"action": "scroll", "dy": -intents.MOUSE_SCROLL}))

    def test_cada_frase_produce_su_orden(self):
        for texto, orden in FRASES.items():
            with self.subTest(texto=texto):
                self.assertEqual(intents.parse(texto), ("mouse", orden))

    def test_lo_que_no_es_orden_de_pantalla(self):
        for texto, kind in NO_MOUSE.items():
            with self.subTest(texto=texto):
                self.assertEqual(intents.parse(texto)[0], kind)

    def test_la_voz_nunca_produce_clic_ni_escritura(self):
        for texto in TENTACIONES + tuple(FRASES) + tuple(NO_MOUSE):
            kind, arg = intents.parse(texto)
            if kind == "mouse":
                self.assertNotIn(arg["action"], PROHIBIDAS, texto)
        producibles = {o["action"] for o in FRASES.values()}
        self.assertFalse(producibles & PROHIBIDAS)

    def test_la_espera_se_recorta(self):
        for dicho, segundos in (("espera 90 segundos", 10), ("espera 11 segundos", 10), ("espera 3 segundos", 3)):
            with self.subTest(dicho=dicho):
                self.assertEqual(intents.parse(dicho)[1]["seconds"], segundos)


class DentroDeLaListaDelEjecutor(unittest.TestCase):
    """La prueba que importa: lo que la voz produce lo acepta el validador real, sin cambiarle nada."""

    def setUp(self):
        self.ctl = tempfile.TemporaryDirectory(); self.addCleanup(self.ctl.cleanup)
        p = patch.dict(os.environ, {"JARVIS_AUTONOMO": "1", "JARVIS_CONTROL_DIR": self.ctl.name})
        p.start(); self.addCleanup(p.stop)

    def ordenes(self):
        for texto in FRASES:
            kind, arg = intents.parse(texto)
            self.assertEqual(kind, "mouse", texto)
            yield texto, dict(arg, agent=ae.AUTO_AGENT)              # el agente lo pone el puente

    def test_todas_pasan_la_lista_segura(self):
        self.assertTrue(ae.autonomo())
        for texto, orden in self.ordenes():
            with self.subTest(texto=texto):
                self.assertIsNone(ae.denial(orden))
                self.assertIn(orden["action"], ae.AUTO_ACTIONS)
                self.assertTrue(ae.auto_ok(orden), orden)

    def test_las_apps_y_webs_son_las_del_ejecutor(self):
        for app in intents.MOUSE_APPS.values():
            self.assertIn(ae.norm(app), ae.ALLOW_APPS, app)
        for url in intents.MOUSE_WEBS.values():
            self.assertTrue(ae.allowed_host(ae.host_of(url)), url)

    def test_con_stop_no_se_ejecuta_ninguna(self):
        (Path(self.ctl.name) / "STOP").write_text("x", encoding="utf-8")
        self.assertTrue(ae.stopped())
        for texto, orden in self.ordenes():
            with self.subTest(texto=texto):
                self.assertFalse(ae.auto_ok(orden) and not ae.stopped())
                with self.assertRaises(RuntimeError):
                    ae.perform(orden, object())          # con STOP ni llega a tocar el puntero


class Ruteo(unittest.TestCase):
    def test_captura_encolada_no_se_declara_completada(self):
        dicho = self.turno(self.build(True), "mira la pantalla", {"ok": True})
        self.assertIn("Solicité", dicho)
        self.assertIn("no he confirmado", dicho)
        self.assertNotIn("Miré", dicho)

    """desktop/app.py: el interruptor, lo que se dice y lo que nunca se dice en voz alta."""

    def build(self, encendido):
        home = tempfile.mkdtemp(); self.addCleanup(shutil.rmtree, home, True)
        cfg = dict(desk.DEFAULTS, VOICE_HOME=home, VOICE_PORT="0", VOICE_TTS_BACKEND="none",
                   VOICE_MOUSE_ENABLED="true" if encendido else "false")
        app = desk.Companion(cfg)
        self.dicho = []
        app.turns = {"t1": {"state": "nuevo"}}
        app.emit = lambda e: None
        app._finish = lambda tid, state, reply=None, **kw: self.dicho.append(reply)
        return app

    def turno(self, app, texto, respuesta):
        self.encargos = []
        def fake(orden):
            self.encargos.append(orden)
            return respuesta
        with patch.object(desk.mouse_autonomo, "encargar", new=fake):
            app._run_turn("t1", texto)
        return self.dicho[-1]

    def test_apagado_no_encarga_nada(self):
        app = self.build(False)
        dicho = self.turno(app, "abre Safari", {"ok": True})
        self.assertEqual(self.encargos, [])
        self.assertIn("VOICE_MOUSE_ENABLED", dicho)

    def test_encendido_manda_la_orden_y_la_confirma(self):
        app = self.build(True)
        dicho = self.turno(app, "abre Safari", {"ok": True, "orden": "open_app"})
        self.assertEqual(self.encargos, [{"action": "open_app", "app": "Safari"}])
        self.assertIn("Safari", dicho)

    def test_cada_orden_se_confirma_en_una_frase_corta(self):
        app = self.build(True)
        for texto in FRASES:
            with self.subTest(texto=texto):
                dicho = self.turno(app, texto, {"ok": True})
                self.assertTrue(dicho and len(dicho) < 120, dicho)

    def test_nunca_lee_un_comando_en_voz_alta(self):
        app = self.build(True)
        motivo = "agente del mouse apagado: bash desktop/mac/instalar_mouse_autonomo.sh instalar"
        dicho = self.turno(app, "abre Safari", {"ok": False, "motivo": motivo})
        for pedazo in ("bash", ".sh", "instalar_mouse", "/"):
            self.assertNotIn(pedazo, dicho)
        self.assertIn("no está encendido", dicho)

    def test_motivos_del_puente_se_dicen_en_claro(self):
        app = self.build(True)
        for motivo in ("STOP activo", "ya hay una orden pendiente", "app", "url", "denylist", "accion", "agente"):
            with self.subTest(motivo=motivo):
                dicho = self.turno(app, "abre Safari", {"ok": False, "motivo": motivo})
                self.assertNotEqual(dicho, motivo)
                self.assertGreater(len(dicho), len(motivo))

    def test_un_motivo_desconocido_no_se_filtra(self):
        app = self.build(True)
        dicho = self.turno(app, "abre Safari", {"ok": False, "motivo": "rm -rf /tmp/x"})
        self.assertNotIn("rm -rf", dicho)

    def test_si_el_puente_falla_el_turno_no_muere(self):
        app = self.build(True)
        def boom(orden):
            raise OSError("disco")
        logging.disable(logging.CRITICAL); self.addCleanup(logging.disable, logging.NOTSET)
        with patch.object(desk.mouse_autonomo, "encargar", new=boom):
            app._run_turn("t1", "abre Safari")
        self.assertIn("No moví nada", self.dicho[-1])

    def test_el_interruptor_viene_apagado(self):
        self.assertEqual(desk.DEFAULTS["VOICE_MOUSE_ENABLED"], "false")


class Plantilla(unittest.TestCase):
    def test_env_example_trae_el_interruptor(self):
        texto = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
        self.assertIn("VOICE_MOUSE_ENABLED=false", texto)


if __name__ == "__main__":
    unittest.main()
