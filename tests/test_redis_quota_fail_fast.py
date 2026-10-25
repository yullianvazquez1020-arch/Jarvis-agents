"""Regression: quota exhaustion must stop retrying without weakening Redis fencing."""
import ast
import pathlib
import unittest
from unittest.mock import Mock

SOURCE = pathlib.Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)
FN = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == "fence_take_leadership")

class TestQuotaFailFast(unittest.TestCase):
    def _run_probe(self, category):
        # Compile only the target function, with bounded fake dependencies.
        mod = ast.fix_missing_locations(ast.Module(body=[FN], type_ignores=[]))
        calls = []
        class RedisRequestFailed(RuntimeError):
            def __init__(self, c):
                self.category = c
                super().__init__("Redis request failed")
        def failed_redis(cmd):
            calls.append(cmd)
            raise RedisRequestFailed(category)
        env = {
            "USE_REDIS": True, "_fence": {"mode": "off", "leader": False},
            "_redis": failed_redis, "_TAKE_LEADER": "lua", "LEADER_KEY": "leader",
            "INSTANCE_ID": "id", "logger": Mock(), "math": __import__("math"),
            "time": Mock(),
        }
        exec(compile(mod, "<fence test>", "exec"), env)
        with self.assertRaises(RuntimeError):
            env["fence_take_leadership"](reintentos=5, espera_s=0)
        return calls, env

    def test_monthly_exhaustion_stops_after_single_request(self):
        calls, env = self._run_probe("http_400:monthly_request_limit")
        self.assertEqual(len(calls), 1)
        self.assertEqual(env["_fence"], {"mode": "unavailable", "leader": False})
        env["time"].sleep.assert_not_called()

    def test_daily_exhaustion_stops_after_single_request(self):
        calls, _ = self._run_probe("http_400:daily_request_limit")
        self.assertEqual(len(calls), 1)

    def test_transient_errors_remain_retryable(self):
        calls, env = self._run_probe("TimeoutException")
        self.assertEqual(len(calls), 6)
        self.assertEqual(env["time"].sleep.call_count, 5)

if __name__ == "__main__":
    unittest.main()
