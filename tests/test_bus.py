"""Bus de negocios: datos ficticios, sin red."""
import pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
import jarvis_bus as jb


class BusTest(unittest.TestCase):
    def setUp(self): self.b = jb.Bus(now=lambda: 1000.0)

    def test_emitir_y_leer(self):
        e = self.b.emitir("contesta-ya", "estado", "demo lista (ficticio)", estado="pr")
        self.assertEqual(e["seq"], 1)
        self.b.emitir("renta", "nota", "cliente ficticio", fuente="grokbot")
        self.assertEqual([x["seq"] for x in self.b.eventos(desde=1)], [2])
        self.assertEqual(len(self.b.eventos(negocio="renta")), 1)
        t = {n["id"]: n for n in self.b.tablero()["negocios"]}
        self.assertEqual(t["contesta-ya"]["estado"], "pr"); self.assertTrue(self.b.tablero()["solo_lectura"])

    def test_validacion(self):
        with self.assertRaises(KeyError): self.b.emitir("nope", "x")
        with self.assertRaises(ValueError): self.b.emitir("renta", "x", estado="rico")
        with self.assertRaises(ValueError): self.b.emitir("renta", "x", fuente="hacker")

    def test_redacta_secretos(self):
        e = self.b.emitir("amazon", "nota", "key sk_live_ABCDEFGH12345 tarjeta 4111111111111111 password=hunter2")
        for s in ("sk_live", "4111111111111111", "hunter2"): self.assertNotIn(s, e["texto"])

    def test_acotado(self):
        for i in range(jb.MAX_EVENTOS + 10): self.b.emitir("trading", "tick", str(i))
        self.assertEqual(len(self.b.eventos(limite=10**6)), jb.MAX_EVENTOS)

    def test_endpoints_con_secreto(self):
        src = (ROOT / "main.py").read_text("utf-8")
        for k in ('"/api/bus/negocios"', '"/api/bus/eventos"'): self.assertIn(k, src)
        i = src.index('"/api/bus/eventos"'); self.assertIn("_key_ok(x_jarvis_secret, ENCARGO_SECRET)", src[i:i+1500])


if __name__ == "__main__": unittest.main()
