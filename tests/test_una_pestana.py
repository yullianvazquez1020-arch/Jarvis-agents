"""Las cuatro pantallas de Jarvis en una sola pestana, sin reescribir ninguna."""
import re
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
UI = RAIZ / "desktop" / "ui"
HTML = (UI / "todo.html").read_text(encoding="utf-8")
JS = (UI / "todo.js").read_text(encoding="utf-8")
CSS = (UI / "todo.css").read_text(encoding="utf-8")
APP = (RAIZ / "desktop" / "app.py").read_text(encoding="utf-8")


class Rutas(unittest.TestCase):
    def test_la_ruta_existe_y_sirve_la_pagina(self):
        self.assertIn('"/todo", "/hud"', APP)
        self.assertIn('"/todo": "todo.html"', APP)

    def test_los_archivos_estan_registrados(self):
        for n in ("todo.css", "todo.js"):
            self.assertIn('"%s": "text/' % n, APP, "%s saldria como JSON" % n)
            self.assertTrue((UI / n).is_file())

    def test_apunta_a_las_cuatro_paginas_que_existen(self):
        destinos = re.findall(r'data-src="([^"]+)"', HTML)
        self.assertEqual(destinos, ["/", "/hud", "/mercado", "/avatar"])
        for d in destinos:
            self.assertIn('"%s"' % d, APP, "la ruta %s no la sirve el panel" % d)


class Seguridad(unittest.TestCase):
    def test_solo_se_puede_enmarcar_a_si_mismo(self):
        # Relajado de DENY a SAMEORIGIN SOLO para esto. Un sitio externo sigue sin poder
        # enmarcar el panel, que es de lo que protege la cabecera.
        self.assertIn('self.send_header("X-Frame-Options", "SAMEORIGIN")', APP)
        self.assertIn("frame-ancestors 'self'", APP)
        self.assertIn("frame-src 'self'", APP)

    def test_nunca_se_abre_a_cualquiera(self):
        for suelto in ("frame-ancestors *", "frame-ancestors 'none' 'self'", 'X-Frame-Options", "ALLOWALL',
                       "frame-src *", "unsafe-inline"):
            self.assertNotIn(suelto, APP)

    def test_el_marco_no_recibe_mas_permisos_de_los_necesarios(self):
        m = re.search(r'setAttribute\("allow", "([^"]+)"\)', JS)
        self.assertIsNotNone(m)
        pedidos = {x.strip() for x in m.group(1).split(";") if x.strip()}
        self.assertEqual(pedidos, {"microphone", "camera", "autoplay", "fullscreen"})
        for prohibido in ("geolocation", "payment", "usb", "midi", "serial"):
            self.assertNotIn(prohibido, m.group(1))

    def test_no_pide_nada_a_internet(self):
        for texto in (HTML, JS, CSS):
            self.assertNotIn("http://", texto.replace("http://127.0.0.1", ""))
            self.assertNotIn("https://", texto)


class NoReescribeNada(unittest.TestCase):
    def test_cada_vista_sigue_siendo_su_propia_pagina(self):
        # Si alguna vez se copia aqui el contenido de una pantalla, esta prueba cae: la gracia
        # es que /mercado pueda cambiar manana sin tocar esta pagina.
        self.assertIn('createElement("iframe")', JS)
        for propio in ("tb-equity", "k-equity", "hx-gauges", "#grid"):
            self.assertNotIn(propio, HTML, "se esta duplicando el contenido de otra pantalla")

    def test_no_recarga_al_volver_a_una_vista_ya_abierta(self):
        self.assertIn("if (!marcos[vista]) marcos[vista] = crear(cual);", JS)
        self.assertIn("marcos[k].hidden = k !== vista;", JS)

    def test_recuerda_la_ultima_vista_pero_funciona_sin_memoria(self):
        self.assertIn('localStorage.setItem(RECUERDO, vista)', JS)
        self.assertIn("catch (e) { /* sin memoria */ }", JS)
        self.assertIn('if (!guardada || !mostrar(guardada, false)) mostrar("panel", false);', JS)

    def test_las_teclas_no_molestan_mientras_se_escribe(self):
        self.assertIn('/^(INPUT|TEXTAREA|SELECT)$/.test(activo.tagName)', JS)
        self.assertIn("ev.metaKey || ev.ctrlKey || ev.altKey", JS)


if __name__ == "__main__":
    unittest.main()
