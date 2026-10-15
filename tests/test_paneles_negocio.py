"""Paneles visuales de negocio: solo datos reales locales; sin datos -> 'sin datos'/'pendiente', nunca cifras inventadas."""
import json, pathlib, sys, tempfile, unittest
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
import paneles as p  # noqa: E402


class Paneles(unittest.TestCase):
    def setUp(self):
        self.root = pathlib.Path(tempfile.mkdtemp())

    def test_vacio_no_inventa(self):
        r = p.resumen(root=self.root, now=1_000_000)
        self.assertFalse(r["inventado"])
        for n in r["negocios"]:
            self.assertFalse(n["datos"]); self.assertIsNone(n["progreso"]); self.assertIsNone(n["real"]); self.assertEqual(n["serie"], [])
            self.assertIn(n["estado"], (p.SIN_DATOS, p.PENDIENTE))
        est = {n["id"]: n["estado"] for n in r["negocios"]}
        self.assertEqual(est["amazon"], p.PENDIENTE); self.assertEqual(est["youtube"], p.PENDIENTE)
        self.assertEqual(r["actividad"]["estado"], p.SIN_DATOS); self.assertEqual(sum(r["actividad"]["por_hora"]), 0)
        self.assertEqual(r["evidencia"]["estado"], p.SIN_DATOS)

    def test_datos_reales(self):
        (self.root / "negocios").mkdir()
        (self.root / "negocios" / "islafix.json").write_text(json.dumps({"meta": 1000, "real": 250, "serie": [1, 2, "x", 3],
                                                                         "hitos": [{"t": "web", "ok": True}]}))
        now = 1_800_000_000.0
        at = datetime.fromtimestamp(now - 60, timezone.utc).isoformat()
        (self.root / "audit.jsonl").write_text(json.dumps({"at": at, "agent": "jarvis", "action": "move", "verdict": "HECHO"}) + "\nbasura\n")
        r = p.resumen(root=self.root, now=now)
        isla = r["negocios"][0]
        self.assertEqual(isla["progreso"], 0.25); self.assertEqual(isla["serie"], [1.0, 2.0, 3.0]); self.assertTrue(isla["datos"])
        self.assertEqual(r["actividad"]["por_hora"][23], 1); self.assertEqual(r["actividad"]["total"], 1)

    def test_servidor_y_cripto(self):
        r = p.resumen(servidor_cobros={"lineas": ["Cliente A: $100"], "as_of": "2026-10-14"},
                      cripto={"conectado": True, "precios": [{"par": "BTC-USD", "usd": 1.5}]}, root=self.root)
        isla = r["negocios"][0]; tr = [n for n in r["negocios"] if n["id"] == "trading"][0]
        self.assertTrue(isla["datos"]); self.assertIn("Cliente A: $100", isla["lineas"]); self.assertIsNone(isla["progreso"])
        self.assertIn("BTC-USD $1.50", tr["lineas"])

    def test_captura_segura(self):
        (self.root / "capturas").mkdir(); (self.root / "capturas" / "123.png").write_bytes(b"png")
        self.assertEqual(p.captura(self.root, "123.png"), b"png")
        for bad in ("../x.png", "a.png", "123.jpg", ""):
            self.assertIsNone(p.captura(self.root, bad))
        self.assertEqual(p.evidencia(self.root)["capturas"][0]["nombre"], "123.png")

    def test_ui_cableada(self):
        app = (ROOT / "desktop" / "app.py").read_text("utf-8")
        for k in ('"/api/paneles-negocio"', '"paneles.js"', '"paneles.css"', "/api/evidencia/"):
            self.assertIn(k, app)
        for page in ("nucleo.html", "index.html"):
            html = (ROOT / "desktop" / "ui" / page).read_text("utf-8")
            self.assertIn("/ui/paneles.js", html); self.assertIn("/ui/paneles.css", html)
        js = (ROOT / "desktop" / "ui" / "paneles.js").read_text("utf-8")
        self.assertIn("REFRESCO = 45000", js); self.assertNotIn("Math.random", js)
        self.assertNotIn("requestAnimationFrame(frame", js)   # no se mete en el bucle del núcleo
        self.assertNotIn("negocios.torre", (ROOT / "desktop" / "paneles.py").read_text("utf-8"))  # cifras DEMO fuera


if __name__ == "__main__":
    unittest.main()
