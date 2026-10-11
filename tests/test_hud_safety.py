"""Guardas de seguridad de la HUD v2 (desktop/ui). Sin red, solo lectura de archivos."""
import pathlib, re, unittest

UI = pathlib.Path(__file__).resolve().parents[1] / "desktop" / "ui"
HUD_FILES = ["hud.html", "hud.js", "hudx.js"]


class HudSafety(unittest.TestCase):
    def read(self, name):
        with open(UI / name, encoding="utf-8") as f:
            return f.read()

    def test_no_html_injection_sinks(self):
        for name in HUD_FILES:
            src = self.read(name)
            for sink in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval("):
                with self.subTest(file=name, sink=sink):
                    self.assertNotIn(sink, src)

    def test_no_inline_script_or_style(self):
        html = self.read("hud.html")
        self.assertIsNone(re.search(r"<script(?![^>]*\bsrc=)[^>]*>\s*\S", html))
        self.assertNotIn("<style", html)
        self.assertNotIn(" style=", html)

    def test_no_external_resources(self):
        for name in HUD_FILES:
            with self.subTest(file=name):
                self.assertNotIn("https://", self.read(name))

    def test_uses_hud_api_only(self):
        js = self.read("hud.js")
        self.assertIn('"/api/hud"', js)
        self.assertNotIn("/desktop/v1/", js)


if __name__ == "__main__":
    unittest.main()
