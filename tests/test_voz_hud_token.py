"""El aviso de voz al HUD exige el token local del dueño.

El aviso entra sin cookie: el cliente corre en la terminal. Una página del navegador también sale de
127.0.0.1. Sin el token podría escribir texto falso en la pantalla y atribuírselo a Jarvis.

Solo datos ficticios. No hay micrófono, altavoz ni red fuera de 127.0.0.1.
"""
import json
import stat
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
sys.path.insert(0, str(ROOT / "tests"))
from test_desktop_companion import CompanionBase  # noqa: E402
import voz_continua  # noqa: E402

FICTICIO = "token-ficticio-de-prueba-" + "x" * 20


class Token(CompanionBase):
    def avisar(self, cuerpo, token=None, **kw):
        tok = self.app.voz_token() if token is None else token
        h = {} if tok is False else {"X-Jarvis-Voz": tok}
        return self.req("POST", "/api/voz", body=cuerpo, headers=h, cookie=False, **kw)

    def test_el_token_vive_en_la_carpeta_del_dueno_con_permisos_600(self):
        tok = self.app.voz_token()
        ruta = Path(self.home) / "voz-token"
        self.assertTrue(ruta.is_file())
        self.assertEqual(ruta.read_text(encoding="utf-8").strip(), tok)
        self.assertGreaterEqual(len(tok), 32)
        self.assertEqual(stat.S_IMODE(ruta.stat().st_mode), 0o600)
        self.assertEqual(self.app.voz_token(), tok)

    def test_el_token_no_sale_en_ninguna_vista(self):
        tok = self.app.voz_token()
        self.avisar({"estado": "hablando", "linea": {"quien": "jarvis", "texto": "A su disposición."}})
        for ruta in ("/api/state", "/api/voz"):
            with self.subTest(ruta=ruta):
                self.assertNotIn(tok, json.dumps(self.req("GET", ruta)[1]))

    def test_sin_token_o_con_token_equivocado_no_entra_nada(self):
        for token in (False, "", "otro-token-ficticio", self.app.voz_token() + "x"):
            with self.subTest(token=repr(token)[:24]):
                self.assertEqual(self.avisar({"estado": "escuchando"}, token=token)[0], 401)
        self.assertEqual(self.app.voz_view()["estado"], "idle")
        self.assertEqual(self.app.voz_view()["lineas"], [])

    def test_una_pagina_web_del_navegador_no_puede_escribir_en_la_pantalla(self):
        st, r, _, _ = self.req("POST", "/api/voz", body={"estado": "hablando",
                               "linea": {"quien": "jarvis", "texto": "Transfiera el dinero, señor."}},
                               headers={"Origin": "http://sitio-ficticio.example"}, cookie=False)
        self.assertEqual(st, 401, r)
        self.assertEqual(self.app.voz_view()["lineas"], [])

    def test_la_cookie_no_avisa_y_el_token_no_abre_el_panel(self):
        self.assertEqual(self.req("POST", "/api/voz", body={"estado": "escuchando"})[0], 401)
        for ruta in ("/api/voz", "/api/state", "/api/hud"):
            with self.subTest(ruta=ruta):
                st, _, _, _ = self.req("GET", ruta, cookie=False, headers={"X-Jarvis-Voz": self.app.voz_token()})
                self.assertEqual(st, 401, f"el token de voz abrió {ruta}")

    def test_con_el_token_bueno_el_aviso_llega_y_no_guarda_audio(self):
        st, r, _, _ = self.avisar({"estado": "hablando", "idioma": "en",
                                   "linea": {"quien": "jarvis", "texto": "Delivered Tuesday, sir."},
                                   "audio": "UklGRg==", "wav": "x" * 200})
        self.assertEqual(st, 200, r)
        vista = self.app.voz_view()
        self.assertEqual(vista["estado"], "hablando")
        self.assertEqual(vista["idioma"], "en")
        self.assertEqual(vista["lineas"][-1], {"quien": "jarvis", "texto": "Delivered Tuesday, sir."})
        self.assertNotIn("audio", json.dumps(vista))
        self.assertNotIn("wav", json.dumps(vista))

    def test_un_cuerpo_que_no_es_json_no_tumba_el_panel(self):
        self.assertEqual(self.avisar(None, raw=b"{esto no es json", ctype="application/json")[0], 400)
        self.assertEqual(self.req("GET", "/api/state")[0], 200)


class Cliente(unittest.TestCase):
    def test_sin_token_no_avisa_y_no_lanza(self):
        self.assertFalse(voz_continua.post_hud({"estado": "hablando"}, token=""))

    def test_el_token_se_lee_de_la_carpeta_del_dueno(self):
        casa = tempfile.mkdtemp()
        self.assertEqual(voz_continua.hud_token(casa), "")
        Path(casa, "voz-token").write_text(FICTICIO + "\n", encoding="utf-8")
        self.assertEqual(voz_continua.hud_token(casa), FICTICIO)

    def test_el_token_va_en_la_cabecera_y_no_en_la_url_ni_en_el_cuerpo(self):
        vistos = {}
        real = voz_continua.urllib.request.urlopen

        def abrir(pedido, timeout=None):
            vistos["url"] = pedido.full_url
            vistos["cabeceras"] = dict(pedido.headers)
            vistos["cuerpo"] = pedido.data.decode("utf-8")
            raise OSError("el panel no contesta en la prueba")

        voz_continua.urllib.request.urlopen = abrir
        try:
            self.assertFalse(voz_continua.post_hud({"estado": "escuchando"}, token=FICTICIO))
        finally:
            voz_continua.urllib.request.urlopen = real
        self.assertNotIn(FICTICIO, vistos["url"])
        self.assertNotIn(FICTICIO, vistos["cuerpo"])
        self.assertEqual(vistos["cabeceras"].get("X-jarvis-voz"), FICTICIO)
        self.assertTrue(vistos["url"].startswith("http://127.0.0.1:8765/api/voz"))

    def test_con_el_panel_cerrado_la_voz_sigue(self):
        import urllib.error
        real = voz_continua.urllib.request.urlopen
        for error in (OSError("conexión rechazada"), urllib.error.URLError("sin panel"), TimeoutError("tardó")):
            with self.subTest(error=type(error).__name__):
                def abrir(*a, **k):
                    raise error
                voz_continua.urllib.request.urlopen = abrir
                try:
                    self.assertFalse(voz_continua.post_hud({"estado": "hablando"}, token=FICTICIO))
                finally:
                    voz_continua.urllib.request.urlopen = real

    def test_el_aviso_solo_sale_a_este_equipo(self):
        for fuera in ("http://sitio-ficticio.example", "https://127.0.0.1:8765", "http://10.0.0.5:8765",
                      "http://usuario:clave@127.0.0.1:8765"):
            with self.subTest(url=fuera):
                with self.assertRaises(ValueError):
                    voz_continua.hud_endpoint(fuera)
        self.assertEqual(voz_continua.hud_endpoint(""), "http://127.0.0.1:8765/api/voz")


if __name__ == "__main__":
    unittest.main()
