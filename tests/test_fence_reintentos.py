"""Arranque: la sonda de liderazgo (fence) con reintentos acotados.

El deploy de la unión (2026-10-20) murió al arrancar por UNA sonda EVAL
fallida contra Upstash ("Redis EVAL is required for safe writes; startup
refused"), con el mismo código que la versión anterior había arrancado
bien. La función sigue estricta por defecto (un intento, como pinta el
test de hardening); el arranque pide reintentos para que un mal momento
transitorio de Upstash no tumbe un deploy. Datos ficticios, sin red."""
import os
import sys
import unittest
from unittest.mock import patch

for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
             "http_proxy", "https_proxy", "all_proxy"):
    os.environ.pop(name, None)

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_jarvis as base

j = base.j


class RedisInestable:
    """Falla las primeras N llamadas EVAL y luego contesta como se le pide."""

    def __init__(self, fallos=0, resultado="OK"):
        self.fallos = fallos
        self.resultado = resultado
        self.llamadas = 0

    def __call__(self, cmd):
        self.llamadas += 1
        if cmd[0] == "EVAL" and self.llamadas <= self.fallos:
            raise RuntimeError("Redis request failed")
        return self.resultado


class FenceReintentos(unittest.TestCase):
    def setUp(self):
        self.dormidas = []
        self.p_sleep = patch("time.sleep", new=self.dormidas.append)
        self.p_sleep.start()

    def tearDown(self):
        self.p_sleep.stop()
        j.USE_REDIS = False
        j._fence.update(mode="off", leader=True)

    def _con_redis(self, fake):
        j.USE_REDIS = True
        return patch.object(j, "_redis", new=fake)

    def test_estricto_por_defecto_un_solo_intento(self):
        fake = RedisInestable(fallos=99)
        with self._con_redis(fake):
            with self.assertRaises(RuntimeError) as ctx:
                j.fence_take_leadership()
        self.assertIn("startup refused", str(ctx.exception))
        self.assertEqual(fake.llamadas, 1)
        self.assertEqual(self.dormidas, [])
        self.assertEqual(j._fence["mode"], "unavailable")

    def test_un_mal_momento_no_tumba_el_arranque(self):
        fake = RedisInestable(fallos=2)
        with self._con_redis(fake):
            salida = j.fence_take_leadership(5)
        self.assertEqual(fake.llamadas, 3)
        self.assertEqual(self.dormidas, [2.0, 4.0])
        self.assertEqual(salida["mode"], "on")
        self.assertTrue(salida["leader"])

    def test_si_eval_nunca_vuelve_se_rechaza_igual(self):
        fake = RedisInestable(fallos=99)
        with self._con_redis(fake):
            with self.assertRaises(RuntimeError) as ctx:
                j.fence_take_leadership(3)
        self.assertEqual(str(ctx.exception),
                         "Redis EVAL is required for safe writes; "
                         "startup refused")
        self.assertEqual(fake.llamadas, 4)
        self.assertEqual(self.dormidas, [2.0, 4.0, 8.0])
        self.assertEqual(j._fence["mode"], "unavailable")
        self.assertFalse(j._fence["leader"])

    def test_sonda_sin_ok_tambien_reintenta(self):
        class DosCaras:
            def __init__(self):
                self.llamadas = 0

            def __call__(self, cmd):
                self.llamadas += 1
                return "NO" if self.llamadas == 1 else "OK"

        fake = DosCaras()
        with self._con_redis(fake):
            salida = j.fence_take_leadership(5)
        self.assertEqual(fake.llamadas, 2)
        self.assertEqual(salida["mode"], "on")


if __name__ == "__main__":
    unittest.main()
