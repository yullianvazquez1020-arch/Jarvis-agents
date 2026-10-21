"""Los dos cambios para bajar los 12 s del turno de voz: modelo propio y datos por adelantado.

Medido en la Mac del dueno el 19 oct, 8 turnos completos: el modelo se lleva el 79 % (9.3 s de
mediana, maximo 22 s); transcripcion 2.1 s, voz 0.27 s. El objetivo de estas pruebas no es que
sea rapido —eso solo lo dice su Mac— sino que los dos mecanismos esten y no rompan nada.
"""
import asyncio
import importlib
import json
import re
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
MAIN = (RAIZ / "main.py").read_text(encoding="utf-8")
API = (RAIZ / "jarvis_desktop_api.py").read_text(encoding="utf-8")
api = importlib.import_module("jarvis_desktop_api")


class ElModeloDeVoz(unittest.TestCase):
    def test_un_nombre_que_no_es_un_modelo_se_ignora(self):
        # Nunca se manda a la API una cadena cualquiera que el dueno haya escrito en Render.
        self.assertIn('if VOICE_MODEL and not re.fullmatch(r"claude-[a-z0-9][a-z0-9.-]{2,80}", VOICE_MODEL):', MAIN)
        self.assertIn('    VOICE_MODEL = ""', MAIN)
        bueno = re.compile(r"claude-[a-z0-9][a-z0-9.-]{2,80}")
        for malo in ("", "gpt-4", "rm -rf /", "claude", "Claude-Sonnet", "../../x", "claude-"):
            self.assertIsNone(bueno.fullmatch(malo), malo)
        for valido in ("claude-haiku-4-5", "claude-sonnet-5-5"):
            self.assertIsNotNone(bueno.fullmatch(valido), valido)

    def test_llega_hasta_la_llamada_y_solo_en_este_canal(self):
        self.assertIn("async def _create_con_cache(history, system, tools, model=None):", MAIN)
        self.assertIn("    model = model or MODEL", MAIN)
        self.assertIn("async def _ai_call_scoped(history, tools, extra_system, model=None):", MAIN)
        self.assertIn("_ai_call_scoped(history, scoped_tools, extra_system, model)", MAIN)
        # Telegram y /chat siguen por _ai_call, sin modelo propio.
        self.assertIn("async def _ai_call(history):\n    return await _create_con_cache(history, system_prompt(), TOOLS)", MAIN)
        self.assertIn('model=getattr(core, "VOICE_MODEL", "") or None', API)

    def test_sin_configurar_no_cambia_nada(self):
        # model=None -> se usa MODEL, exactamente como antes.
        self.assertIn("model = model or MODEL", MAIN)


class LaInstantanea(unittest.TestCase):
    def setUp(self):
        api._instantanea.update(at=0.0, texto="")

    def correr(self, **falsos):
        class Nucleo:
            pass
        n = Nucleo()
        for k, v in falsos.items():
            setattr(n, k, v)
        with patch.object(api, "core", n), patch.object(api, "_stamp", lambda: "2026-10-19T21:00:00"):
            return asyncio.run(api.instantanea())

    def test_mete_los_datos_y_dice_de_cuando_son(self):
        t = self.correr(paper_status=lambda: {"capital": 945.57, "pnl": -54.43},
                        upcoming=lambda: [{"what": "Kevin Kirk"}])
        self.assertIn("paper_status = ", t)
        self.assertIn("945.57", t)
        self.assertIn("upcoming = ", t)
        self.assertIn("2026-10-19T21:00:00", t)
        self.assertIn("no tool call needed", t)

    def test_una_lectura_que_falla_no_impide_contestar(self):
        def revienta(): raise RuntimeError("Upstash caido")
        t = self.correr(paper_status=revienta, upcoming=lambda: [{"what": "algo"}])
        self.assertNotIn("paper_status", t)
        self.assertIn("upcoming", t)

    def test_si_todo_falla_devuelve_vacio_y_no_revienta(self):
        def revienta(): raise RuntimeError("todo mal")
        self.assertEqual(self.correr(paper_status=revienta, upcoming=revienta), "")

    def test_una_lectura_colgada_no_cuelga_el_turno(self):
        # Se mide lo que espera el DUENO: cuanto tarda instantanea() en devolver. El hilo colgado
        # sigue vivo hasta que su lectura termine (asyncio no puede matar un hilo), pero el turno
        # ya contesto. En el servidor el bucle es de larga vida, asi que eso no retrasa a nadie;
        # aqui se corre a mano para no medir el cierre del pool de hilos de asyncio.run.
        def cuelga(): time.sleep(30)
        class Nucleo: pass
        n = Nucleo(); n.paper_status = cuelga; n.upcoming = lambda: [{"what": "algo"}]
        bucle = asyncio.new_event_loop()
        try:
            with patch.object(api, "core", n), patch.object(api, "_stamp", lambda: "x"):
                t0 = time.time()
                t = bucle.run_until_complete(api.instantanea())
                tardo = time.time() - t0
        finally:
            bucle.close()
        self.assertLess(tardo, 6.0, "el turno espero %.1f s por una lectura colgada" % tardo)
        self.assertIn("upcoming", t)
        self.assertNotIn("paper_status", t)

    def test_las_lecturas_van_en_paralelo_no_una_tras_otra(self):
        def lenta(): time.sleep(0.6)
        t0 = time.time()
        self.correr(paper_status=lenta, upcoming=lenta, finances_summary=lenta, jobs_summary=lenta)
        tardo = time.time() - t0
        self.assertLess(tardo, 1.5, "4 lecturas de 0.6 s tardaron %.1f s: van en serie" % tardo)

    def test_un_dato_enorme_se_recorta(self):
        t = self.correr(paper_status=lambda: {"x": "y" * 5000})
        self.assertLess(len(t), 1800)
        self.assertIn("recortado", t)

    def test_se_guarda_unos_segundos_y_no_se_relee_en_cada_turno(self):
        veces = {"n": 0}
        def contar():
            veces["n"] += 1
            return {"n": veces["n"]}
        self.correr(paper_status=contar)
        self.correr(paper_status=contar)
        self.assertEqual(veces["n"], 1, "se releyo en el segundo turno")
        api._instantanea["at"] = time.time() - api.INSTANTANEA_TTL - 1
        self.correr(paper_status=contar)
        self.assertEqual(veces["n"], 2, "no se refresco al vencer")

    def test_el_turno_la_usa_y_no_pisa_el_prompt(self):
        self.assertIn("extra_system=DESKTOP_PROMPT + await instantanea()", API)

    def test_no_promete_que_el_dato_es_de_ahora(self):
        self.assertIn("Never present it as newer than its timestamp", API)

    def test_no_apaga_las_herramientas(self):
        # Si la instantanea no cubre la pregunta, el modelo todavia puede pedir el dato.
        self.assertIn("Use the tools only for what is NOT here", API)
        self.assertIn("allowed_tools=READ_TOOLS", API)


class LaCadenaDeEnvoltorios(unittest.TestCase):
    """El fallo que costo esta tanda: dos extensiones envuelven core.run enumerando sus argumentos,
    asi que anadir uno nuevo reventaba el canal del panel entero — en Render tambien, no solo aqui."""

    FUENTES = ("jarvis_v420.py", "jarvis_selfcheck.py")

    def test_los_envoltorios_dejan_pasar_lo_que_no_conocen(self):
        for nombre in self.FUENTES:
            with self.subTest(archivo=nombre):
                texto = (RAIZ / nombre).read_text(encoding="utf-8")
                self.assertIn("read_only=None, **extra):", texto,
                              "%s enumera los argumentos; el proximo parametro nuevo lo rompe" % nombre)
                reenvios = texto.count("original_run(session, message")
                self.assertGreater(reenvios, 0)
                # Se cuenta el final del reenvio, no "**extra)" a secas: la propia firma
                # termina en "**extra):" y contaba de mas.
                self.assertEqual(texto.count("read_only=read_only, **extra)"), reenvios,
                                 "%s: hay un reenvio a original_run que no pasa **extra" % nombre)

    def test_de_verdad_pasan_un_argumento_nuevo(self):
        # No basta con que el texto lo diga: se construye la cadena y se comprueba que llega.
        import inspect
        for nombre in self.FUENTES:
            with self.subTest(archivo=nombre):
                texto = (RAIZ / nombre).read_text(encoding="utf-8")
                firma = re.search(r"async def run\(session, message,[^)]*\)", texto).group(0)
                espacio = {}
                exec("async def original_run(session, message, **kw):\n    return kw\n", espacio)
                exec(firma + ":\n    return await original_run(session, message, allowed_tools=allowed_tools,"
                     " extra_system=extra_system, read_only=read_only, **extra)\n", espacio)
                salida = asyncio.run(espacio["run"]("s", "m", allowed_tools=frozenset(), model="claude-haiku-4-5"))
                self.assertEqual(salida.get("model"), "claude-haiku-4-5")


if __name__ == "__main__":
    unittest.main()
