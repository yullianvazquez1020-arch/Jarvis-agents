"""Display de terminal y orbe: datos ficticios, sin red."""
import io, pathlib, sys, unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
import jarvis_display as jd  # noqa: E402
from rich.console import Console  # noqa: E402

FAKE = {"jarvis": "online", "version": "9.9.9", "telegram_ready": True, "storage": "prueba",
        "ai": {"configured": True, "model": "modelo-ficticio"},
        "money_gate": {"max_order_usd": 100.0, "max_day_usd": 300.0},
        "telegram_queue": {"interrupted": 0, "stale": 0}, "scheduler": {"last_error": None},
        "builtin": ["modulo-a"], "aincrad": {"status": "activo", "landing": "/kit"}}
MAIN = 'HELP_TEXT = ("x:\\n"\n  "/hoy — resumen · /calendario\\n"\n  "/enviar N · /noenviar N\\n")\n'
BRAIN = "# B\n1. Tarea uno.\n2. Tarea dos.\n12. Tarea doce.\n"


class Display(unittest.TestCase):
    def test_parse_brain(self):
        self.assertEqual(jd.parse_brain(BRAIN), [(1, "Tarea uno."), (2, "Tarea dos."), (12, "Tarea doce.")])

    def test_parse_powers_from_help_text(self):
        p = jd.parse_powers(MAIN)
        self.assertEqual(p[0], ("/hoy /calendario", "resumen · /calendario"))
        self.assertEqual(p[1][0], "/enviar /noenviar")
        self.assertEqual(jd.parse_powers("nada"), [])

    def test_real_main_has_powers(self):
        self.assertTrue(any("/diagnostico" in c for c, _ in jd.parse_powers((ROOT / "main.py").read_text("utf-8"))))

    def test_status_rows_flags(self):
        rows = {k: ok for k, _, ok in jd.status_rows(FAKE)}
        self.assertTrue(all(rows.values()))
        bad = dict(FAKE, money_gate={"max_order_usd": 500.0, "max_day_usd": 300.0})
        self.assertFalse({k: ok for k, _, ok in jd.status_rows(bad)}["Tope por operación"])

    def test_render_ok_and_offline(self):
        for args in ((FAKE, [("/hoy", "x")], [(1, "t")]), (None, [], [], "URLError")):
            con = Console(file=io.StringIO(), width=120, height=40)
            con.print(jd.render(*args))
            out = con.file.getvalue()
            self.assertIn("ESTADO", out)
        self.assertIn("Sin conexión", out)

    def test_load_is_get_only(self):
        with mock.patch.object(jd, "fetch", side_effect=OSError("sin red")):
            h, p, b, err = jd.load("http://x")
        self.assertIsNone(h); self.assertEqual(err, "OSError")


class Orbe(unittest.TestCase):
    def test_orbe_safe_and_light(self):
        js = (ROOT / "desktop/ui/orbe.js").read_text("utf-8")
        for sink in ("innerHTML", "eval(", "https://", "method:"):
            self.assertNotIn(sink, js)
        self.assertIn('"/api/state"', js)
        self.assertNotIn("<style", (ROOT / "desktop/ui/orbe.html").read_text("utf-8"))

    def test_orbe_served(self):
        src = (ROOT / "desktop/app.py").read_text("utf-8")
        self.assertIn('"/orbe": "orbe.html"', src)
        self.assertIn('"orbe.js"', src)


if __name__ == "__main__":
    unittest.main()
