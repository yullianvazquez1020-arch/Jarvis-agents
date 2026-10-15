"""Bitácora Friday<->Jarvis: datos ficticios, sin red."""
import datetime, pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import jarvis_bitacora as b


class BitacoraTest(unittest.TestCase):
    def setUp(self):
        self.store = {}
        b.configurar(lambda k, d: self.store.get(k, d), lambda k, v: self.store.__setitem__(k, v),
                     lambda: datetime.datetime(2026, 10, 14, 20, 0), lambda t: t.replace("SECRETO", "[x]"))

    def test_orden_y_limite(self):
        for i in range(12):
            b.registrar("telegram", f"msg {i}", 123)
        last = b.leer(10)
        self.assertEqual([r["text"] for r in last], [f"msg {i}" for i in range(2, 12)])
        self.assertEqual(last[-1]["seq"], 12)

    def test_anillo(self):
        for i in range(b.MAX + 5):
            b.registrar("telegram", f"m{i}")
        self.assertEqual(len(self.store[b.KEY]), b.MAX)
        self.assertEqual(b.leer(1)[0]["text"], f"m{b.MAX + 4}")

    def test_friday_y_filtro_y_redaccion(self):
        b.registrar("telegram", "hola", 1)
        b.registrar("friday", "nota SECRETO", None, "friday")
        fr = b.leer(10, "friday")
        self.assertEqual(len(fr), 1); self.assertEqual(fr[0]["text"], "nota [x]")

    def test_seguro_no_rompe(self):
        b.configurar(lambda k, d: [], lambda k, v: (_ for _ in ()).throw(OSError()), lambda: datetime.datetime.now())
        self.assertIsNone(b.registrar_seguro("telegram", "x"))
        with self.assertRaises(ValueError): b.registrar("raro", "x")

    def test_main_integra(self):
        src = (ROOT / "main.py").read_text()
        for s in ('@app.get("/api/bitacora")', '@app.post("/api/bitacora/friday")', '"leer_bitacora"',
                  'registrar_seguro, "telegram"'):
            self.assertIn(s, src)
        import jarvis_seal
        self.assertIn(b.KEY, jarvis_seal.SEALED_KEYS)


if __name__ == "__main__":
    unittest.main()
