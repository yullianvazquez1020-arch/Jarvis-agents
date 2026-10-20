"""La caché del prompt: que marque las herramientas y no cambie lo que el modelo ve.

Se lee main.py con ast en vez de importarlo: main.py necesita fastapi, httpx, pydantic y
anthropic, y en un entorno sin ellas las pruebas que lo importan no se ejecutan — justo donde
más barato sería romper esto sin que nadie se enterara.

Lo que NO prueba: que la caché acierte de verdad contra la API. Eso solo se ve en producción,
con usage.cache_read_input_tokens, y en el latencia.log del dueño.
"""
import ast
import os
import unittest

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(RAIZ, "main.py"), encoding="utf-8") as f:
    FUENTE = f.read()
ARBOL = ast.parse(FUENTE)


def funcion(nombre):
    for n in ast.walk(ARBOL):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == nombre:
            return n
    raise AssertionError(f"falta la función {nombre}()")


def texto(nodo):
    return ast.get_source_segment(FUENTE, nodo) or ""


class CachePrompt(unittest.TestCase):
    def test_se_cachean_las_herramientas_no_la_instruccion(self):
        """La instrucción lleva la hora al minuto: cachearla no acertaría nunca. Las
        herramientas son idénticas en cada llamada y van antes en el orden de la caché."""
        cuerpo = texto(funcion("_tools_cached"))
        self.assertIn('"cache_control"', cuerpo)
        self.assertIn('"ephemeral"', cuerpo)
        sp = texto(funcion("system_prompt"))
        self.assertNotIn("cache_control", sp, "no se cachea la instrucción: cambia cada minuto")
        self.assertIn("%H:%M", sp, "si la instrucción dejara de llevar la hora, reconsidera esto")

    def test_la_marca_va_en_la_ultima_herramienta(self):
        """El corte de la caché marca el final del prefijo: tiene que ser la última."""
        cuerpo = texto(funcion("_tools_cached"))
        self.assertIn("tools[-1]", cuerpo)
        self.assertIn("tools[:-1]", cuerpo)

    def test_no_muta_la_lista_original(self):
        """Si marcara TOOLS en su sitio, el objeto compartido quedaría tocado para siempre."""
        cuerpo = texto(funcion("_tools_cached"))
        self.assertIn("dict(tools[-1])", cuerpo, "hay que copiar la herramienta antes de marcarla")
        self.assertNotIn("tools[-1][", cuerpo)
        self.assertNotIn(".append(", cuerpo)

    def test_se_puede_apagar_con_una_variable(self):
        self.assertIn('os.getenv("AI_PROMPT_CACHE"', FUENTE)
        cuerpo = texto(funcion("_tools_cached"))
        self.assertIn("PROMPT_CACHE_ON", cuerpo)
        for valor in ('"false"', '"0"', '"no"'):
            self.assertIn(valor, FUENTE[FUENTE.index('os.getenv("AI_PROMPT_CACHE"'):][:200])

    def test_una_lista_vacia_no_revienta(self):
        self.assertIn("not tools", texto(funcion("_tools_cached")))

    def test_si_la_api_la_rechaza_se_reintenta_sin_ella(self):
        """Una respuesta tarde es mejor que un chat roto. Y solo se avisa una vez."""
        cuerpo = texto(funcion("_create_con_cache"))
        self.assertIn("BadRequestError", cuerpo)
        self.assertIn("_cache_unsupported", cuerpo)
        self.assertIn("logger.warning", cuerpo)
        self.assertEqual(cuerpo.count("client.messages.create"), 2, "falta el reintento sin caché")
        self.assertIn("raise", cuerpo, "un error que no sea de caché tiene que propagarse")

    def test_las_dos_llamadas_del_agente_pasan_por_ahi(self):
        for nombre in ("_ai_call", "_ai_call_scoped"):
            cuerpo = texto(funcion(nombre))
            self.assertIn("_create_con_cache", cuerpo, f"{nombre} no usa el camino con caché")
            self.assertNotIn("client.messages.create", cuerpo)

    def test_no_cambia_el_modelo_ni_el_tope_de_respuesta(self):
        cuerpo = texto(funcion("_create_con_cache"))
        # El modelo entra por argumento (VOICE_MODEL en el canal del panel) y MODEL sigue siendo
        # el valor por defecto: ningun canal cambia de modelo por accidente.
        self.assertIn("model = model or MODEL", cuerpo)
        self.assertEqual(cuerpo.count("model=model"), 2, "las dos llamadas tienen que usar el mismo modelo")
        self.assertIn("max_tokens=AI_MAX_TOKENS", cuerpo)

    def test_la_instruccion_sigue_llegando_entera_en_las_dos(self):
        self.assertIn("system_prompt()", texto(funcion("_ai_call")))
        self.assertIn("system_prompt() + extra_system", texto(funcion("_ai_call_scoped")))


class Comportamiento(unittest.TestCase):
    """La lógica de _tools_cached, ejecutada de verdad, copiada tal cual del archivo."""

    def setUp(self):
        self.ns = {"os": os}
        inicio = FUENTE.index("PROMPT_CACHE_ON = ")
        fin = FUENTE.index("async def _create_con_cache")
        exec(compile(FUENTE[inicio:fin], "main.py", "exec"), self.ns)

    def correr(self, tools, encendida=True):
        self.ns["PROMPT_CACHE_ON"] = encendida
        self.ns["_cache_unsupported"] = {"si": False}
        return self.ns["_tools_cached"](tools)

    def test_marca_solo_la_ultima_y_no_toca_el_original(self):
        tools = [{"name": "a"}, {"name": "b"}, {"name": "c"}]
        salida = self.correr(tools)
        self.assertEqual([t["name"] for t in salida], ["a", "b", "c"])   # mismo orden
        self.assertNotIn("cache_control", salida[0])
        self.assertNotIn("cache_control", salida[1])
        self.assertEqual(salida[-1]["cache_control"], {"type": "ephemeral"})
        self.assertEqual(tools, [{"name": "a"}, {"name": "b"}, {"name": "c"}])  # intacto

    def test_apagada_devuelve_las_mismas(self):
        tools = [{"name": "a"}]
        self.assertIs(self.correr(tools, encendida=False), tools)

    def test_lista_vacia(self):
        self.assertEqual(self.correr([]), [])

    def test_una_sola_herramienta(self):
        salida = self.correr([{"name": "sola"}])
        self.assertEqual(salida[0]["cache_control"], {"type": "ephemeral"})

    def test_tras_un_rechazo_deja_de_marcarlas(self):
        tools = [{"name": "a"}, {"name": "b"}]
        self.ns["PROMPT_CACHE_ON"] = True
        self.ns["_cache_unsupported"] = {"si": True}
        self.assertIs(self.ns["_tools_cached"](tools), tools)


if __name__ == "__main__":
    unittest.main()
