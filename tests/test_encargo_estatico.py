"""/api/encargo: revisión estática con ast (sin dependencias, sin importar main.py)."""
import ast, unittest
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf-8')
TREE = ast.parse(SRC)
FUNCS = {n.name: n for n in ast.walk(TREE) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def calls(node):
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            f = n.func
            out.append(f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else '')
    return out


def const(name):
    for n in TREE.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in n.targets):
            return n.value
    raise AssertionError(name)


class EncargoEstatico(unittest.TestCase):
    def test_route_once(self):
        self.assertEqual(SRC.count('@app.post("/api/encargo")'), 1)

    def test_secret_from_env_and_constant_time(self):
        v = const('ENCARGO_SECRET')
        self.assertIn('JARVIS_ENCARGO_SECRET', ast.unparse(v)); self.assertIn('getenv', ast.unparse(v))
        self.assertIn('compare_digest', calls(FUNCS['_key_ok']))
        self.assertIn('_key_ok', calls(FUNCS['encargo']))

    def test_min_secret_and_max(self):
        self.assertGreaterEqual(const('ENCARGO_MIN_SECRET').value, 16)
        self.assertEqual(const('ENCARGO_MAX').value, 4000)

    def test_401_first_raise_and_before_add_task(self):
        f = FUNCS['encargo']; src = ast.unparse(f)
        raises = [n for n in ast.walk(f) if isinstance(n, ast.Raise)]
        first = min(raises, key=lambda n: (n.lineno, n.col_offset))
        first_if = next(n for n in f.body if isinstance(n, ast.If))   # first check = the secret
        self.assertIn('_key_ok', ast.unparse(first_if.test)); self.assertIn(first, list(ast.walk(first_if)))
        self.assertIn('401', ast.unparse(first_if))
        self.assertLess(src.index('401'), src.index('503')); self.assertLess(src.index('401'), src.index('422'))
        self.assertLess(src.index('401'), src.index('add_task'))

    def test_slash_refused_and_both_buckets(self):
        src = ast.unparse(FUNCS['encargo'])
        self.assertIn("startswith('/')", src); self.assertIn('422', src)
        self.assertIn("_rate_ok('encargo')", src); self.assertIn("_rate_ok('encargo-mal')", src)

    def test_run_goes_to_owner_free_text_only(self):
        f = FUNCS['_encargo_run']; c = calls(f); src = ast.unparse(f)
        self.assertIn('_handle_tg', c); self.assertIn('_handle_tg(TG_OWNER, ', src); self.assertIn("'[Encargo", src)
        for bad in ('_tg_route', '_cb', '_tg_cb_cmd', '_real_execute'):
            self.assertNotIn(bad, c)

    def test_caps_unchanged(self):
        self.assertIn('HARD_MAX_ORDER_USD = 100', SRC.replace('100.0', '100'))
        self.assertIn('HARD_MAX_DAY_USD = 300', SRC.replace('300.0', '300'))

    def test_logger_never_gets_secret_or_text(self):
        for name in ('encargo', '_encargo_run'):
            for n in ast.walk(FUNCS[name]):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and ast.unparse(n.func.value) == 'logger':
                    args = ast.unparse(n)
                    self.assertNotIn('x_jarvis_secret', args); self.assertNotIn('ENCARGO_SECRET', args)
                    self.assertNotRegex(args, r',\s*texto\s*\)')


if __name__ == '__main__':
    unittest.main()
