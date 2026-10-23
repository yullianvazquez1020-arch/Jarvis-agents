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
import asyncio
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

    def test_cinco_reintentos_seis_intentos_y_tope(self):
        fake = RedisInestable(fallos=99)
        with self._con_redis(fake), self.assertRaises(RuntimeError):
            j.fence_take_leadership(5)
        self.assertEqual(fake.llamadas, 6)
        self.assertEqual(self.dormidas, [2, 4, 8, 16, 30])
        self.dormidas.clear()
        with self._con_redis(fake), self.assertRaises(RuntimeError):
            j.fence_take_leadership(5, 100)
        self.assertEqual(self.dormidas, [30] * 5)

    def test_parametros_invalidos_no_envian_sonda(self):
        fake = RedisInestable()
        with self._con_redis(fake):
            for n, delay in [(-1, 2), (6, 2), (True, 2), (1, -1), (1, float('nan')), (1, float('inf'))]:
                with self.subTest(n=n, delay=delay), self.assertRaises(ValueError):
                    j.fence_take_leadership(n, delay)
        self.assertEqual(fake.llamadas, 0)

    def test_transportes_reales_se_reintentan_sin_exponer_secretos(self):
        request = j.httpx.Request('POST', 'https://example.invalid')
        ok = j.httpx.Response(200, json={'result': 'OK'}, request=request)
        for error in (j.httpx.ReadTimeout('private-token'), j.httpx.ConnectError('private-token')):
            with self.subTest(error=type(error).__name__), patch.object(j, 'USE_REDIS', True), \
                 patch.object(j.httpx, 'post', side_effect=[error, ok]) as post, \
                 self.assertLogs('jarvis', level='WARNING') as logs:
                j.fence_take_leadership(5)
            self.assertEqual(post.call_count, 2)
            self.assertNotIn('private-token', str(logs.output))
            self.assertIn(type(error).__name__, str(logs.output))

    def test_http_json_y_error_redis_se_rechazan(self):
        request = j.httpx.Request('POST', 'https://example.invalid')
        for response, category in [
            (j.httpx.Response(401, request=request), 'http_401'),
            (j.httpx.Response(429, request=request), 'http_429'),
            (j.httpx.Response(503, request=request), 'http_503'),
            (j.httpx.Response(200, text='not json', request=request), 'invalid_json'),
            (j.httpx.Response(200, json={'error': 'private-token'}, request=request), 'invalid_response_or_command_error'),
            (j.httpx.Response(200, json=[], request=request), 'invalid_response_or_command_error'),
        ]:
            with self.subTest(category=category), patch.object(j.httpx, 'post', return_value=response):
                with self.assertRaises(j.RedisRequestFailed) as ctx:
                    j._redis(['GET', 'dummy'])
                self.assertEqual(ctx.exception.category, category)
                self.assertNotIn('private-token', str(ctx.exception))

    def test_lifespan_no_inicia_servicios_sin_liderazgo(self):
        async def run():
            async with j._lifespan(j.app):
                self.fail('startup must refuse')
        with patch.object(j, 'fence_take_leadership', side_effect=RuntimeError('refused')) as fence, \
             patch.object(j, '_restaurar_seq_bus') as bus, \
             patch.object(j, '_tg_recover_inbox') as tg, \
             patch.object(j, '_scheduler_loop') as scheduler:
            with self.assertRaises(RuntimeError):
                asyncio.run(run())
        fence.assert_called_once_with(5)
        bus.assert_not_called(); tg.assert_not_called(); scheduler.assert_not_called()

    def test_http_400_distingue_cuotas_permisos_y_lua_sin_texto_remoto(self):
        request = j.httpx.Request('POST', 'https://example.invalid')
        cases = [
            ('ERR max daily request limit exceeded', 'daily_request_limit'),
            ('ERR max requests limit exceeded', 'monthly_request_limit'),
            ('ERR max request size exceeded', 'request_size_limit'),
            ('ERR max concurrent connections exceeded', 'connection_limit'),
            ('ERR max data size exceeded', 'storage_limit'),
            ('ERR database capacity quota exceeded', 'storage_limit'),
            ('NOPERM this user has no permissions', 'permission_denied'),
            ('READONLY You cannot write', 'read_only'),
            ('WRONGPASS invalid username-password pair', 'authentication_failed'),
            ('NOAUTH Authentication required', 'authentication_required'),
            ("ERR unknown command 'EVAL'", 'unsupported_command'),
            ('ERR wrong number of arguments', 'invalid_arguments'),
            ('ERR Error running script', 'script_error'),
            ('ERR Error compiling script', 'script_error'),
        ]
        for error, category in cases:
            with self.subTest(category=category):
                response = j.httpx.Response(400, json={'error': error + ' private-token'}, request=request)
                with patch.object(j.httpx, 'post', return_value=response), \
                     patch.object(j, 'USE_REDIS', True), self.assertLogs('jarvis', level='WARNING') as logs:
                    with self.assertRaisesRegex(RuntimeError, 'startup refused'):
                        j.fence_take_leadership()
                self.assertIn('http_400:' + category, str(logs.output))
                self.assertNotIn('private-token', str(logs.output))
                self.assertNotIn(error, str(logs.output))
                self.assertFalse(j._fence['leader'])

    def test_respuestas_desconocidas_no_filtran_el_cuerpo(self):
        request = j.httpx.Request('POST', 'https://example.invalid')
        responses = [
            j.httpx.Response(400, json={'error':'private-token'}, request=request),
            j.httpx.Response(400, json={'error':{'message':'private-token'}}, request=request),
            j.httpx.Response(400, json=['private-token'], request=request),
            j.httpx.Response(400, text='<html>private-token</html>', request=request),
            j.httpx.Response(400, json={'error':'max requests limit exceeded' + 'x' * 9000}, request=request),
            j.httpx.Response(400, json={'error':'x' * 4200}, request=request),
        ]
        for response in responses:
            with self.subTest(body_type=response.headers.get('content-type')), \
                 patch.object(j.httpx, 'post', return_value=response):
                with self.assertRaises(j.RedisRequestFailed) as ctx:
                    j._redis(['EVAL', 'private-script', '1', 'private-key'])
                self.assertEqual(ctx.exception.category, 'http_400')
                self.assertNotIn('private', str(ctx.exception))

    def test_error_redis_en_http_200_se_clasifica_y_no_habilita_escrituras(self):
        request = j.httpx.Request('POST', 'https://example.invalid')
        response = j.httpx.Response(200, json={'error':'NOPERM private-token'}, request=request)
        with patch.object(j.httpx, 'post', return_value=response):
            with self.assertRaises(j.RedisRequestFailed) as ctx:
                j._redis(['GET', 'private-key'])
        self.assertEqual(ctx.exception.category, 'invalid_response_or_command_error:permission_denied')
        self.assertNotIn('private-token', str(ctx.exception))

    def test_health_error_redis_es_503_sin_exponer_diagnosticos(self):
        import jarvis_brain
        async def run():
            return await j.health()
        with patch.object(jarvis_brain, 'health', side_effect=j.RedisRequestFailed('ReadTimeout')):
            result = asyncio.run(run())
        self.assertEqual(result.status_code, 503)
        self.assertNotIn(b'ReadTimeout', result.body)

    def test_esperando_liderazgo_no_se_permiten_escrituras(self):
        fake = RedisInestable(fallos=1)
        j._fence.update(mode='on', leader=True)
        def waiting(_):
            self.assertFalse(j._fence['leader'])
            with self.assertRaises(j.StaleInstance):
                j._redis_write(['dummy', 'value'])
        with self._con_redis(fake), patch('time.sleep', new=waiting):
            j.fence_take_leadership(5)
        self.assertEqual(fake.llamadas, 2)


if __name__ == "__main__":
    unittest.main()
