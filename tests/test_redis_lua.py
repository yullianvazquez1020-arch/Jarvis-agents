"""v4.0.2: the REAL Lua scripts from main.py, run on a REAL local redis-server (no cjson needed).

Does not import main.py, so it needs no Python packages. Skipped when redis-server is not installed.
The same checks run against Upstash with: python3 scripts/check_redis_lua.py
"""
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import check_redis_lua as lua  # noqa: E402


class Resp:
    """Tiny Redis protocol client (enough for strings, ints, nil and errors)."""
    def __init__(self, port):
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=5)
        self.f = self.sock.makefile("rb")

    def __call__(self, cmd):
        parts = [str(c).encode() for c in cmd]
        self.sock.sendall(b"*%d\r\n" % len(parts) + b"".join(b"$%d\r\n%s\r\n" % (len(p), p) for p in parts))
        return self._read()

    def _read(self):
        line = self.f.readline()
        kind, rest = line[:1], line[1:-2]
        if kind == b"+": return rest.decode()
        if kind == b"-": raise RuntimeError(rest.decode())
        if kind == b":": return int(rest)
        if kind == b"$":
            n = int(rest)
            if n < 0: return None
            data = self.f.read(n + 2)[:-2]
            return data.decode()
        if kind == b"*":
            return [self._read() for _ in range(int(rest))]
        raise RuntimeError("bad reply")


@unittest.skipUnless(shutil.which("redis-server"), "redis-server not installed")
class RealRedisLua(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); cls.port = s.getsockname()[1]; s.close()
        cls.dir = tempfile.mkdtemp()
        cls.proc = subprocess.Popen(["redis-server", "--port", str(cls.port), "--save", "", "--appendonly", "no",
                                     "--dir", cls.dir], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                cls.r = Resp(cls.port); cls.r(["PING"]); break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("redis-server did not start")

    @classmethod
    def tearDownClass(cls):
        cls.r.sock.close(); cls.proc.terminate(); cls.proc.wait(5)

    def test_all_scripts_on_real_redis(self):
        results = lua.run_checks(self.r)
        failed = [f"{n} {d}" for n, ok, d in results if not ok]
        self.assertEqual(failed, []); self.assertGreaterEqual(len(results), 14)

    def test_selftest_leaves_no_keys(self):
        lua.run_checks(self.r)
        self.assertEqual(self.r(["KEYS", "jarvis:selftest:*"]), [])

    def test_claims_from_eight_connections_only_one_wins(self):
        s = lua.load_scripts()
        self.r(["SET", "L", "me"])
        raw = s["_tg_job_json"]({"id": 9, "msg": {"text": "hola"}, "state": "queued", "at": "t"})
        self.r(["SET", "J", raw])
        clients = [Resp(self.port) for _ in range(8)]
        replies = [c(["EVAL", s["_CLAIM_JOB"], "2", "L", "J", "me", "2026-10-06T18:00:00-04:00", "60",
                      s["_TG_QUEUED_PREFIX"]]) for c in clients]
        for c in clients: c.sock.close()
        self.assertEqual(sum(1 for x in replies if x), 1)


if __name__ == "__main__":
    unittest.main(verbosity=1)
