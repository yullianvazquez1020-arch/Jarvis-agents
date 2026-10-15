"""Holograma + Torre de Aincrad (/avatar/ironman): bandera apagada por defecto, vista que solo muestra.

Sin red fuera de 127.0.0.1, sin dinero, sin datos reales del dueño: las cifras de la vista son ficticias.
"""
import http.client
import json
import pathlib
import re
import sys
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
UI = ROOT / "desktop" / "ui"
sys.path.insert(0, str(ROOT / "desktop"))
import app as desk                                  # noqa: E402

OWN_FILES = ["ironman.html", "ironman.css", "ironman.js", "aincrad.js"]


class Files(unittest.TestCase):
    """Reglas de la casa sobre los archivos nuevos. Solo lectura."""

    def read(self, name):
        return (UI / name).read_text(encoding="utf-8")

    def test_no_external_tts_or_cdn(self):
        for name in OWN_FILES:
            src = self.read(name)
            for bad in ("ttsEndpoint", "ttsApikey", "speechSynthesis", "SpeechSynthesisUtterance",
                        "openai", "elevenlabs", "googleapis", "polly", "azure"):
                with self.subTest(file=name, bad=bad):
                    self.assertNotIn(bad, src)
            with self.subTest(file=name, bad="url externa"):
                self.assertIsNone(re.search(r"https?://", src))

    def test_no_html_injection_sinks(self):
        for name in OWN_FILES:
            src = self.read(name)
            for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
                with self.subTest(file=name, sink=sink):
                    self.assertNotIn(sink, src)

    def test_no_inline_script_or_style(self):
        html = self.read("ironman.html")
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html))
        self.assertNotIn("<style", html)
        self.assertNotIn(" style=", html)

    def test_three_is_local_not_cdn(self):
        scene = self.read("ironman.js")
        self.assertIn('from "./vendor/three/three.module.js"', scene)
        self.assertIn('from "./vendor/three/controls/OrbitControls.js"', scene)
        for name in ("three.module.js", "three.core.js", "controls/OrbitControls.js", "LICENSE"):
            with self.subTest(vendor=name):
                self.assertTrue((UI / "vendor" / "three" / name).is_file())
        orbit = (UI / "vendor" / "three" / "controls" / "OrbitControls.js").read_text(encoding="utf-8")
        self.assertNotIn("from 'three'", orbit)        # sin importmap: la CSP no permite scripts en línea
        self.assertIn("from '../three.module.js'", orbit)

    def test_light_on_the_2015_mac(self):
        scene = self.read("ironman.js")
        self.assertIn("setPixelRatio(1)", scene)
        self.assertIn("document.hidden", scene)
        self.assertIn("visibilitychange", scene)
        for pass_name in ("EffectComposer", "UnrealBloomPass", "BloomPass", "postprocessing"):
            with self.subTest(pass_name=pass_name):
                self.assertNotIn(pass_name, scene)

    def test_view_only_never_moves_money(self):
        """La vista no puede aprobar, confirmar, enviar ni tocar cripto."""
        for name in OWN_FILES:
            src = self.read(name)
            for verb in ("/aprobar", "/confirmar", "/enviar", "coinbase", "prepare_order",
                         "/api/hand-mouse/", "withdraw"):
                with self.subTest(file=name, verb=verb):
                    self.assertNotIn(verb, src)

    def test_only_read_only_endpoints(self):
        scene = self.read("ironman.js")
        self.assertNotIn("method: \"POST\"", scene)
        self.assertNotIn("method: 'POST'", scene)
        self.assertEqual(sorted(set(re.findall(r'fetch\("([^"]+)"', scene))), ['/api/panels/'])

    def test_demo_figures_are_labelled(self):
        self.assertIn("Datos demo", self.read("aincrad.js"))
        self.assertIn("data-notice", self.read("ironman.html"))

    def test_flag_is_off_in_env_example(self):
        env = (ROOT / ".env.example").read_text(encoding="utf-8")
        self.assertIn("JARVIS_AVATAR_IRONMAN=0", env)
        self.assertNotIn("JARVIS_AVATAR_IRONMAN=1", env)
        self.assertEqual(desk.DEFAULTS["JARVIS_AVATAR_IRONMAN"], "0")

    def test_served_files_are_declared(self):
        for name in ("ironman.css", "ironman.js", "aincrad.js"):
            with self.subTest(name=name):
                self.assertIn(name, desk.UI_FILES)
        post = [f"three/postprocessing/{n}.js" for n in ("BokehPass", "EffectComposer", "MaskPass", "OutputPass", "Pass",
                                                          "RenderPass", "ShaderPass", "UnrealBloomPass", "GTAOPass", "AfterimagePass")]
        shaders = [f"three/shaders/{n}.js" for n in ("BokehShader", "CopyShader", "LuminosityHighPassShader", "OutputShader", "GTAOShader", "PoissonDenoiseShader", "AfterimageShader")]
        self.assertEqual(sorted(desk.VENDOR_FILES), sorted(["three/controls/OrbitControls.js", "three/three.core.js",
                                                            "three/three.module.js", "three/math/SimplexNoise.js", "three/loaders/HDRLoader.js"] + post + shaders))   # lista cerrada (torre cine)


class Route(unittest.TestCase):
    """La ruta solo existe con la bandera encendida, y siempre detrás de la sesión del panel."""
    flag = "0"

    def setUp(self):
        import tempfile
        cfg = dict(desk.DEFAULTS, VOICE_HOME=tempfile.mkdtemp(), VOICE_PORT="0",
                   JARVIS_AVATAR_IRONMAN=self.flag)
        self.app, self.httpd, self.port = desk.serve(cfg)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        self.host = f"127.0.0.1:{self.port}"

    def get(self, path, cookie=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Host": self.host}
        if cookie:
            headers["Cookie"] = "jd_session=" + cookie
        c.request("GET", path, headers=headers)
        r = c.getresponse()
        body = r.read()
        c.close()
        return r.status, body

    def login(self):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        c.request("GET", f"/?launch={self.app.new_launch()}", headers={"Host": self.host})
        r = c.getresponse(); r.read()
        cookie = r.getheader("Set-Cookie").split(";")[0].split("=", 1)[1]
        c.close()
        return cookie

    def test_off_by_default(self):
        self.assertFalse(self.app.avatar_ironman)
        status, _ = self.get("/avatar/ironman", self.login())
        self.assertEqual(status, 404)

    def test_three_served_for_core_while_off(self):   # el núcleo WebGL necesita three.js aunque el avatar esté apagado
        status, _ = self.get("/ui/vendor/three/three.module.js", self.login())
        self.assertEqual(status, 200)
        status, _ = self.get("/ui/vendor/three/three.module.js")      # sin sesión, nada
        self.assertNotEqual(status, 200)

    def test_every_three_module_served_as_js_while_off(self):   # postprocessing/* incluido (antes 404 JSON → 2D viejo)
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / "desktop" / "ui" / "vendor"
        files = sorted((root / "three").rglob("*.js"))
        self.assertGreater(len(files), 10)
        cookie = self.login()
        for f in files:
            status, _ = self.get("/ui/vendor/" + f.relative_to(root).as_posix(), cookie)
            self.assertEqual(status, 200, f)

    def test_state_reports_the_flag(self):
        status, body = self.get("/api/state", self.login())
        self.assertEqual(status, 200)
        self.assertIs(json.loads(body)["avatar_ironman"], False)

    def test_avatar_untouched(self):
        status, body = self.get("/avatar", self.login())
        self.assertEqual(status, 200)
        self.assertIn(b"/ui/nucleo.js", body)                     # /avatar = núcleo; la ciudad orbital se retiró
        self.assertNotIn(b"\xc3\x93RBITA", body); self.assertNotIn(b"PISOS", body)

    def test_avatar_does_not_advertise_the_view(self):
        """Con la bandera apagada, /avatar no enseña el enlace al holograma."""
        _, body = self.get("/avatar", self.login())
        self.assertNotIn(b"/avatar/ironman", body)
        self.assertNotIn(b"<!--ironman-->", body)


class RouteOn(Route):
    flag = "1"

    def test_off_by_default(self):
        self.assertTrue(self.app.avatar_ironman)
        status, body = self.get("/avatar/ironman", self.login())
        self.assertEqual(status, 200)
        self.assertIn(b"/ui/nucleo.js", body); self.assertNotIn(b"AINCRAD", body.upper())

    def test_vendor_hidden_while_off(self):
        status, body = self.get("/ui/vendor/three/three.module.js", self.login())
        self.assertEqual(status, 200)
        self.assertIn(b"three.core.js", body[:4000])

    def test_state_reports_the_flag(self):
        status, body = self.get("/api/state", self.login())
        self.assertIs(json.loads(body)["avatar_ironman"], True)

    def test_avatar_does_not_advertise_the_view(self):
        """Con la bandera encendida /avatar sigue siendo el núcleo; el holograma vive en /avatar/ironman."""
        _, body = self.get("/avatar", self.login())
        self.assertIn(b"/ui/nucleo.js", body)

    def test_needs_a_session(self):
        self.assertEqual(self.get("/avatar/ironman")[0], 401)
        self.assertEqual(self.get("/ui/ironman.js")[0], 401)
        self.assertEqual(self.get("/ui/vendor/three/three.core.js")[0], 401)

    def test_no_path_escape(self):
        cookie = self.login()
        for path in ("/ui/vendor/three/../../app.py", "/ui/vendor/../app.py",
                     "/ui/vendor/three/controls/../three.module.js", "/ui/vendor/three/LICENSE"):
            with self.subTest(path=path):
                self.assertEqual(self.get(path, cookie)[0], 404)


if __name__ == "__main__":
    unittest.main()


class JarvisCombinadoV2(unittest.TestCase):
    def test_voice_mouse_and_status(self):
        import sys as _s
        from pathlib import Path as P
        root = P(__file__).resolve().parent.parent
        _s.path.insert(0, str(root / "desktop"))
        import intents, mouse_autonomo
        self.assertEqual(intents.parse("open safari"), ("mouse", {"action": "open_app", "app": "Safari"}))
        self.assertEqual(intents.parse("scroll down")[0], "mouse")
        self.assertIn("concedido", mouse_autonomo.accesibilidad())
        js = (root / "desktop" / "ui" / "app.js").read_text("utf-8")
        for k in ("function ack()", "resumeConversation()", "jarvis-convo", "silenceMs: 350", "st-ax"):
            self.assertIn(k, js)
        gl = (root / "desktop" / "ui" / "nucleo-gl.js").read_text("utf-8")
        self.assertIn("const HB = 66 / 60", gl)
