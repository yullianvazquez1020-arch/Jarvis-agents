"""Torre de Aincrad local y cripto pública: datos ficticios, sin red real."""
import pathlib, sys, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
import negocios as n  # noqa: E402


class Torre(unittest.TestCase):
    def test_cien_pisos_y_negocios(self):
        t = n.torre()
        self.assertEqual(t["total_pisos"], 100); self.assertEqual(len(t["pisos"]), 100)
        self.assertEqual(t["controlador"], "Jarvis"); self.assertTrue(t["demo"])
        nombres = " ".join(x["nombre"] for x in t["negocios"])
        for k in ("Side hustle", "Renta", "Trading", "Agencia de contenido", "Contesta Ya"):
            self.assertIn(k, nombres)
        self.assertEqual([p["piso"] for p in t["pisos"]], list(range(1, 101)))

    def test_cripto_ok_y_sin_conexion(self):
        n._cache.update(t=0.0, data=None)
        ok = n.mercado(fetch=lambda par: 100.0, now=lambda: 1000.0)
        self.assertTrue(ok["conectado"]); self.assertFalse(ok["trading_real"])
        self.assertEqual(ok["precios"][0]["usd"], 100.0)
        n._cache.update(t=0.0, data=None)
        def boom(par): raise OSError("sin red")
        off = n.mercado(fetch=boom, now=lambda: 5000.0)
        self.assertFalse(off["conectado"]); self.assertEqual(off["error"], "OSError")
        self.assertIsNone(off["precios"][0]["usd"])

    def test_cache(self):
        n._cache.update(t=0.0, data=None); calls = []
        f = lambda par: calls.append(par) or 1.0
        n.mercado(fetch=f, now=lambda: 10.0); n.mercado(fetch=f, now=lambda: 20.0)
        self.assertEqual(len(calls), len(n.PARES))

    def test_ui_wired(self):
        app = (ROOT / "desktop" / "app.py").read_text("utf-8")
        for k in ('"/api/negocios"', '"/api/cripto"', '"negocios.js"', '"torre-pisos.js"', '"negocios.css"'):
            self.assertIn(k, app)
        self.assertIn("negocios.js", (ROOT / "desktop/ui/index.html").read_text("utf-8"))
        self.assertIn("torre-pisos.js", (ROOT / "desktop/ui/torre.html").read_text("utf-8"))


class ModoNucleo(unittest.TestCase):
    def setUp(self):
        import importlib
        try:
            self.app = importlib.import_module("app")
        except Exception as e:  # dependencias opcionales del escritorio
            self.skipTest(f"app no importable: {e}")

    def test_jarvis_normal_y_ultron_con_aviso(self):
        m = self.app.core_mode
        self.assertEqual(m("ok", 0.0, 1000.0), "jarvis")
        self.assertEqual(m("unconfigured", 0.0, 1000.0), "jarvis")
        self.assertEqual(m("ok", 900.0, 1000.0), "ultron")
        self.assertEqual(m("ok", 1.0, 1.0 + self.app.ALERT_MODE_S + 1), "jarvis")
        for bad in ("error", "down", "offline"):
            self.assertEqual(m(bad, 0.0, 1000.0), "ultron")

    def test_orbe_ui_tiene_ambos_modos(self):
        js = (ROOT / "desktop/ui/orbe.js").read_text("utf-8")
        for k in ("ringJarvis", "ringUltron", "j.mode", '"ultron"'):
            self.assertIn(k, js)
        self.assertIn("nucleo-modo.js", (ROOT / "desktop/ui/ironman.html").read_text("utf-8"))
        self.assertIn("body.ultron", (ROOT / "desktop/ui/ironman.css").read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()
