"""Pruebas de la memoria de conocimiento local (jarvis_knowledge) y su enganche en jarvis_router.

Sin red: los servidores HTTP falsos escuchan en 127.0.0.1. Solo datos y claves ficticios.
Corren con solo la librería estándar (Python 3.9+), sin importar main.py.
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import jarvis_knowledge as jk  # noqa: E402
import jarvis_router as jr  # noqa: E402

FAKE = {
    "a.md": "# Sockets en Python\nUsa socket.create_connection para abrir TCP. El cliente Pepe Ficticio prueba.",
    "b.html": "<html><title>DNS basico</title><script>x=1</script><p>DNS resuelve nombres a direcciones IP "
              "con registros A y AAAA.</p></html>",
    "c.txt": "Validacion de entradas: usa listas permitidas (allowlist) y consultas parametrizadas contra inyeccion SQL.",
    "d.py": "API_KEY = 'sk-ficticio-1234567890'\ndef tope():\n    return 100  # tope por operacion",
    ".env": "TELEGRAM_BOT_TOKEN=ficticio999999",
}
KNOWLEDGE_VARS = ("JARVIS_KNOWLEDGE_ENABLED", "JARVIS_KNOWLEDGE_EMBED", "JARVIS_KNOWLEDGE_DB",
                  "JARVIS_EMBED_MODEL", "JARVIS_OLLAMA_URL", "OLLAMA_URL")


def clean_env(test):
    """Quita las variables de la memoria del entorno durante la prueba."""
    p = mock.patch.dict(os.environ, {})
    p.start()
    test.addCleanup(p.stop)
    for v in KNOWLEDGE_VARS:
        os.environ.pop(v, None)


def write_tree(root: Path, files: dict):
    for name, text in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        clean_env(self)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        write_tree(self.root, FAKE)
        self.kb = jk.Knowledge(":memory:")
        self.addCleanup(self.kb.close)
        self.res = self.kb.ingest_dir(self.root, "prueba")

    def bodies(self):
        return " ".join(r[0] for r in self.kb.db.execute("SELECT body FROM chunks"))


class Ingest(Base):
    def test_ingest_counts_skip_env(self):
        self.assertEqual(self.res["files"], 4)
        self.assertNotIn("repo/.env", {r[0] for r in self.kb.db.execute("SELECT source FROM docs")})

    def test_search_cites(self):
        h = self.kb.search("como resolver nombres DNS")[0]
        self.assertEqual(h.title, "DNS basico")
        self.assertIn("b.html", h.cite())
        self.assertNotIn("x=1", h.snippet)
        self.assertNotIn("x=1", h.body)

    def test_source_is_relative_no_home_path(self):
        h = self.kb.search("DNS")[0]
        self.assertEqual(h.source, "repo/b.html")
        self.assertNotIn(self.tmp.name, self.bodies() + " ".join(r[0] for r in self.kb.db.execute("SELECT source FROM docs")))

    def test_redact_secret(self):
        b = self.bodies()
        self.assertNotIn("sk-ficticio", b)
        self.assertIn("API_KEY=[REDACTADO]", b)
        self.assertNotIn("ficticio999999", b)

    def test_topic_filter_and_empty(self):
        self.assertEqual(self.kb.search("DNS", topic="otro"), [])
        self.assertEqual(self.kb.search("?!"), [])
        self.assertTrue(self.kb.search("DNS", topic="prueba"))

    def test_reingest_replaces(self):
        p = self.root / "c.txt"
        p.write_text("texto nuevo sobre firewall")
        self.kb.ingest_file(p, "prueba", "repo/c.txt")
        self.assertEqual(self.kb.search("allowlist"), [])
        self.assertTrue(self.kb.search("firewall"))

    def test_incremental_and_prune(self):
        again = self.kb.ingest_dir(self.root, "prueba")
        self.assertEqual((again["files"], again["unchanged"], again["removed"]), (0, 4, 0))
        (self.root / "c.txt").unlink()
        st = self.kb.ingest_dir(self.root, "prueba")
        self.assertEqual(st["removed"], 1)
        self.assertEqual(self.kb.search("allowlist"), [])

    def test_chunking_overlap(self):
        cs = jk.chunk("linea\n" * 600, 300, 50)
        self.assertGreater(len(cs), 5)
        self.assertTrue(all(len(c) <= 300 for c in cs))
        self.assertEqual(jk.chunk(""), [])

    def test_skips_private_dirs_relative_to_root(self):
        # El repo vive dentro de una carpeta llamada "data": aun así se indexa. Dentro, data/ venv/ .git se saltan.
        outer = Path(self.tmp.name) / "data" / "Jarvis-ficticio"
        write_tree(outer, {
            "ok.md": "documento visible sobre firewall ficticio",
            "data/oculto.md": "firewall dentro de data",
            "venv/lib/x.py": "firewall en venv",
            ".venv/y.py": "firewall en .venv",
            ".git/HEAD.txt": "firewall en git",
            "node_modules/z.md": "firewall en node",
            ".env.local": "OWNER_TOKEN=ficticio-local-123",
            "sub/.env.prod.md": "firewall en env",
        })
        secret_dir = Path(self.tmp.name) / "fuera"
        write_tree(secret_dir, {"privado.md": "firewall fuera del repo"})
        try:
            os.symlink(secret_dir / "privado.md", outer / "enlace.md")
            os.symlink(secret_dir, outer / "carpeta_enlace")
        except (OSError, NotImplementedError):
            pass
        kb = jk.Knowledge(":memory:")
        self.addCleanup(kb.close)
        res = kb.ingest_dir(outer, "jarvis")
        self.assertEqual(res["files"], 1)
        self.assertEqual([h.source for h in kb.search("firewall", k=10)], ["Jarvis-ficticio/ok.md"])

    def test_large_and_other_extensions_skipped(self):
        write_tree(self.root, {"foto.png": "no", "notas.json": "{}"})
        big = self.root / "grande.txt"
        big.write_text("x" * (jk.MAX_FILE_BYTES + 1))
        self.assertEqual(self.kb.ingest_file(big, "prueba"), 0)
        self.assertEqual(self.kb.ingest_file(self.root / "foto.png", "prueba"), 0)
        self.assertEqual(self.kb.ingest_file(self.root / "notas.json", "prueba"), 0)


class Redaction(unittest.TestCase):
    def setUp(self):
        clean_env(self)

    def test_formats(self):
        os.environ["FICTICIO_SERVICE_TOKEN"] = "valor-ficticio-777-abc"
        text = (
            '{"api_key": "abcd1234efgh"}\n'
            "password: ficticia-clave-1\n"
            "TWILIO_AUTH_TOKEN=ficticio0011223344\n"
            "Authorization: Bearer ficticiobearer1234567890\n"
            "-----BEGIN RSA PRIVATE KEY-----\nMIIficticio\nlinea2\n-----END RSA PRIVATE KEY-----\n"
            "otro texto con sk-ficticio0123456789abcdef y ghp_ficticio0123456789abcdefgh\n"
            "copia: valor-ficticio-777-abc\n"
        )
        out = jk.redact(text)
        for leaked in ("abcd1234efgh", "ficticia-clave-1", "ficticio0011223344", "ficticiobearer",
                       "MIIficticio", "sk-ficticio0123", "ghp_ficticio", "valor-ficticio-777"):
            self.assertNotIn(leaked, out)
        self.assertIn("TWILIO_AUTH_TOKEN=[REDACTADO]", out)
        self.assertIn("api_key=[REDACTADO]", out)

    def test_code_kept(self):
        code = 'key = os.environ.get("AGENT_API_KEY")\nHARD_MAX_DAY_USD = 300.0\n'
        self.assertEqual(jk.redact(code), code)


class Flags(Base):
    def test_disabled_by_default(self):
        self.assertFalse(jk.enabled())
        self.assertFalse(jk.embeddings_enabled())
        msgs = [{"role": "user", "content": "DNS"}]
        meta = {}
        self.assertIs(jk.augment_messages(msgs, kb=self.kb, meta=meta), msgs)
        self.assertEqual(meta, {"topics": [], "private": False})
        self.assertEqual(jk.build_context("DNS", kb=self.kb), "")

    def test_flag_values(self):
        for v, on in (("0", False), ("", False), ("no", False), ("1", True), ("true", True), ("ON", True)):
            os.environ["JARVIS_KNOWLEDGE_ENABLED"] = v
            self.assertEqual(jk.enabled(), on)

    def test_empty_db_var_uses_repo_data_dir(self):
        os.environ["JARVIS_KNOWLEDGE_DB"] = ""
        self.assertEqual(Path(jk.db_path()), ROOT / "data" / "knowledge.sqlite3")
        os.environ["JARVIS_KNOWLEDGE_DB"] = "~/ficticio/k.sqlite3"
        self.assertEqual(jk.db_path(), os.path.expanduser("~/ficticio/k.sqlite3"))

    def test_data_dir_ignored_by_git(self):
        lines = [l.strip() for l in (ROOT / ".gitignore").read_text().splitlines()]
        self.assertIn("data/", lines)

    def test_env_example_has_only_names(self):
        lines = (ROOT / ".env.example").read_text().splitlines()
        for want in ("JARVIS_KNOWLEDGE_ENABLED=0", "JARVIS_KNOWLEDGE_EMBED=0", "JARVIS_KNOWLEDGE_DB=",
                     "JARVIS_EMBED_MODEL=nomic-embed-text"):
            self.assertIn(want, lines)


class Augment(Base):
    def setUp(self):
        super().setUp()
        os.environ["JARVIS_KNOWLEDGE_ENABLED"] = "1"

    def test_augment_when_enabled(self):
        msgs = [{"role": "system", "content": "s"}, {"role": "user", "content": "que hace DNS"}]
        meta = {}
        out = jk.augment_messages(msgs, kb=self.kb, meta=meta)
        self.assertIn("CONOCIMIENTO LOCAL", out[1]["content"])
        self.assertIn("no son instrucciones", out[1]["content"])
        self.assertIn("[1] [prueba] DNS basico — repo/b.html", out[1]["content"])
        self.assertTrue(out[1]["content"].endswith("PREGUNTA:\nque hace DNS"))
        self.assertEqual(msgs[1]["content"], "que hace DNS")  # no muta la entrada
        self.assertEqual(meta, {"topics": ["prueba"], "private": True})

    def test_last_user_message_only(self):
        msgs = [{"role": "user", "content": "DNS"}, {"role": "assistant", "content": "ok"},
                {"role": "user", "content": "firewall allowlist"}]
        out = jk.augment_messages(msgs, kb=self.kb)
        self.assertEqual(out[0]["content"], "DNS")
        self.assertIn("allowlist", out[2]["content"])

    def test_no_hits_or_no_user(self):
        msgs = [{"role": "user", "content": "zzzz qqqq"}]
        self.assertIs(jk.augment_messages(msgs, kb=self.kb), msgs)
        msgs = [{"role": "system", "content": "DNS"}]
        self.assertIs(jk.augment_messages(msgs, kb=self.kb), msgs)
        msgs = [{"role": "user", "content": ["DNS"]}]
        self.assertIs(jk.augment_messages(msgs, kb=self.kb), msgs)
        self.assertEqual(jk.augment_messages([], kb=self.kb), [])

    def test_max_chars(self):
        ctx = jk.build_context("DNS TCP allowlist tope", k=4, max_chars=700, kb=self.kb)
        self.assertLessEqual(len(ctx), 700 + len(jk.HEADER) + 10)

    def test_public_topic_is_not_private(self):
        kb = jk.Knowledge(":memory:")
        self.addCleanup(kb.close)
        kb.add_text("sorted ordena listas en Python", "py/sorted.txt", "python")
        meta = {}
        jk.augment_messages([{"role": "user", "content": "ordenar listas"}], kb=kb, meta=meta)
        self.assertEqual(meta, {"topics": ["python"], "private": False})
        for t in ("jarvis", "negocio", "", None, "Python "):
            self.assertEqual(jk.is_private_topic(t), t != "Python ")

    def test_missing_db_does_not_create_file(self):
        path = Path(self.tmp.name) / "no-existe" / "k.sqlite3"
        os.environ["JARVIS_KNOWLEDGE_DB"] = str(path)
        msgs = [{"role": "user", "content": "DNS"}]
        self.assertIs(jk.augment_messages(msgs), msgs)
        self.assertFalse(path.exists())
        self.assertFalse(path.parent.exists())

    def test_broken_db_falls_back_silently(self):
        path = Path(self.tmp.name) / "rota.sqlite3"
        path.write_bytes(b"esto no es sqlite " * 100)
        os.environ["JARVIS_KNOWLEDGE_DB"] = str(path)
        msgs = [{"role": "user", "content": "DNS"}]
        with self.assertLogs("jarvis.knowledge", "WARNING") as logs:
            self.assertIs(jk.augment_messages(msgs), msgs)
        self.assertNotIn("DNS", " ".join(logs.output))

    def test_db_file_round_trip(self):
        path = Path(self.tmp.name) / "data" / "knowledge.sqlite3"
        with jk.Knowledge(str(path)) as kb:
            kb.ingest_dir(self.root, "redes")
        os.environ["JARVIS_KNOWLEDGE_DB"] = str(path)
        meta = {}
        out = jk.augment_messages([{"role": "user", "content": "DNS"}], meta=meta)
        self.assertIn("DNS basico", out[0]["content"])
        self.assertEqual(meta["topics"], ["redes"])


# ------------------------------------------------------------ servidor falso (Ollama + API)

CALLS = []
STATE = {"embed_fail": False}


class FakeServer(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj=None):
        data = json.dumps(obj).encode() if obj is not None else b""
        self.send_response(code)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        CALLS.append((self.path, body))
        if self.path == "/api/embed":
            if STATE["embed_fail"]:
                return self._send(500)
            vecs = [[1.0, 0.0] if "dns" in t.lower() else [0.0, 1.0] for t in body["input"]]
            return self._send(200, {"model": body["model"], "embeddings": vecs})
        if self.path == "/api/chat":
            return self._send(200, {"message": {"content": "local-ok"}, "prompt_eval_count": 1, "eval_count": 1})
        return self._send(200, {"choices": [{"message": {"content": "api-ok"}}], "usage": {"total_tokens": 2}})


class ProxyRecorder(BaseHTTPRequestHandler):
    hits = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        ProxyRecorder.hits.append(self.path)
        self.send_response(502)
        self.send_header("Content-Length", "0")
        self.end_headers()


def serve(handler):
    srv = HTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class ServerCase(Base):
    @classmethod
    def setUpClass(cls):
        cls.srv = serve(FakeServer)
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        super().setUp()
        CALLS.clear()
        STATE["embed_fail"] = False


class Embeddings(ServerCase):
    def test_rerank_with_fake_ollama(self):
        os.environ.update({"JARVIS_KNOWLEDGE_EMBED": "1", "JARVIS_OLLAMA_URL": self.url})
        hits = self.kb.search("DNS TCP")
        self.assertEqual(hits[0].title, "DNS basico")
        self.assertGreater(self.kb.db.execute("SELECT count(*) FROM vectors").fetchone()[0], 0)
        self.assertEqual(CALLS[0][1]["model"], "nomic-embed-text")
        n = len(CALLS)
        self.kb.search("DNS TCP")  # los vectores se reutilizan: solo se embebe la consulta
        self.assertEqual(len(CALLS), n + 1)
        self.assertEqual(CALLS[-1][1]["input"], ["DNS TCP"])

    def test_ollama_url_fallback_name(self):
        os.environ.update({"JARVIS_KNOWLEDGE_EMBED": "1", "OLLAMA_URL": self.url})
        self.assertEqual(jk.embed(["dns"]), [[1.0, 0.0]])

    def test_ollama_error_falls_back_to_bm25(self):
        os.environ.update({"JARVIS_KNOWLEDGE_EMBED": "1", "JARVIS_OLLAMA_URL": self.url})
        STATE["embed_fail"] = True
        with self.assertLogs("jarvis.knowledge", "WARNING"):
            hits = self.kb.search("DNS")
        self.assertEqual(hits[0].title, "DNS basico")

    def test_ollama_down_falls_back_to_bm25(self):
        os.environ.update({"JARVIS_KNOWLEDGE_EMBED": "1", "JARVIS_OLLAMA_URL": "http://127.0.0.1:1"})
        with self.assertLogs("jarvis.knowledge", "WARNING") as logs:
            self.assertTrue(self.kb.search("DNS"))
        self.assertNotIn("DNS", " ".join(logs.output))

    def test_remote_embed_refused_and_fallback(self):
        bad = ("http://ejemplo.invalid", "http://127.0.0.1.ejemplo.invalid", "http://localhost.ejemplo.invalid",
               "http://usuario@ejemplo.invalid", "http://localhost@ejemplo.invalid", "ftp://127.0.0.1",
               "https://10.0.0.5:11434", "http://[::ffff:8.8.8.8]")
        os.environ["JARVIS_KNOWLEDGE_EMBED"] = "1"
        for url in bad:
            os.environ["JARVIS_OLLAMA_URL"] = url
            self.assertRaises(jk.KnowledgeError, jk.embed, ["x"])
            with self.assertLogs("jarvis.knowledge", "WARNING"):
                self.assertTrue(self.kb.search("DNS"))
        for url in ("http://127.0.0.1:11434", "http://localhost:11434", "http://[::1]:11434"):
            self.assertTrue(jk._is_loopback(url), url)

    def test_embed_ignores_proxy_env(self):
        proxy = serve(ProxyRecorder)
        self.addCleanup(proxy.server_close)
        self.addCleanup(proxy.shutdown)
        ProxyRecorder.hits.clear()
        purl = f"http://127.0.0.1:{proxy.server_port}"
        for v in ("NO_PROXY", "no_proxy"):
            os.environ.pop(v, None)
        os.environ.update({"HTTP_PROXY": purl, "http_proxy": purl, "HTTPS_PROXY": purl, "https_proxy": purl,
                           "JARVIS_OLLAMA_URL": self.url})
        self.assertEqual(jk.embed(["dns"]), [[1.0, 0.0]])
        self.assertEqual(ProxyRecorder.hits, [])

    def test_bad_embed_response(self):
        os.environ["JARVIS_OLLAMA_URL"] = self.url
        with mock.patch.object(FakeServer, "do_POST", lambda s: FakeServer._send(s, 200, {"embeddings": [[]]})):
            self.assertRaises(jk.KnowledgeError, jk.embed, ["a"])


class RouterIntegration(ServerCase):
    """route(): la memoria va justo antes de ask_ollama/ask_api; contexto privado = solo local."""

    def setUp(self):
        super().setUp()
        os.environ.update({"OLLAMA_URL": self.url, "DEEPSEEK_API_KEY": "clave-ficticia-123",
                           "JARVIS_API_ORDER": "deepseek", "JARVIS_LOCAL_MODEL": "modelo-ficticio:1b",
                           "JARVIS_KNOWLEDGE_ENABLED": "1"})
        for v in ("DASHSCOPE_API_KEY", "MOONSHOT_API_KEY", "VENICE_API_KEY"):
            os.environ.pop(v, None)
        p = mock.patch.dict(jr.BASE_URLS, {"deepseek": f"{self.url}/deepseek"})
        p.start()
        self.addCleanup(p.stop)
        self.db = Path(self.tmp.name) / "data" / "knowledge.sqlite3"
        os.environ["JARVIS_KNOWLEDGE_DB"] = str(self.db)

    def index(self, topic, text):
        with jk.Knowledge(str(self.db)) as kb:
            kb.add_text(text, f"{topic}/doc.md", topic, "Doc ficticio")

    def api_calls(self):
        return [c for c in CALLS if c[0].startswith("/deepseek")]

    def chat_calls(self):
        return [c for c in CALLS if c[0] == "/api/chat"]

    PROMPT = "Escribe código que explique el tope diario ficticio"  # COMPLEX: normalmente iría a la API

    def test_without_knowledge_complex_goes_to_api(self):
        os.environ["JARVIS_KNOWLEDGE_ENABLED"] = "0"
        self.index("jarvis", "El tope diario ficticio es de 300 dolares de prueba.")
        r = jr.route(self.PROMPT)
        self.assertTrue(r["backend"].startswith("deepseek"))
        self.assertEqual(self.api_calls()[0][1]["messages"][-1]["content"], self.PROMPT)

    def test_jarvis_context_goes_only_local(self):
        self.index("jarvis", "El tope diario ficticio es de 300 dolares de prueba.")
        r = jr.route(self.PROMPT, force="api")
        self.assertTrue(r["backend"].startswith("ollama:"))
        self.assertEqual(self.api_calls(), [])
        content = self.chat_calls()[0][1]["messages"][-1]["content"]
        self.assertIn("CONOCIMIENTO LOCAL", content)
        self.assertIn("[jarvis] Doc ficticio", content)

    def test_jarvis_context_and_ollama_down_is_error(self):
        self.index("jarvis", "El tope diario ficticio es de 300 dolares de prueba.")
        os.environ["OLLAMA_URL"] = "http://127.0.0.1:1"
        with self.assertRaises(jr.RouterError) as cm, self.assertLogs("jarvis.router", "WARNING"):
            jr.route(self.PROMPT)
        self.assertIn("no se envían a APIs externas", str(cm.exception))
        self.assertEqual(self.api_calls(), [])
        self.assertNotIn("tope", str(cm.exception))

    def test_unknown_topic_is_private_too(self):
        self.index("negocio", "El tope diario ficticio del negocio de prueba.")
        jr.route(self.PROMPT)
        self.assertEqual(self.api_calls(), [])

    def test_public_context_may_go_to_api(self):
        self.index("python", "Para explicar el tope diario ficticio usa sorted y listas.")
        r = jr.route(self.PROMPT)
        self.assertTrue(r["backend"].startswith("deepseek"))
        sent = self.api_calls()[0][1]["messages"][-1]["content"]
        self.assertIn("[python] Doc ficticio", sent)
        self.assertTrue(sent.endswith("PREGUNTA:\n" + self.PROMPT))

    def test_sensitive_prompt_still_local_with_public_context(self):
        self.index("python", "Factura ficticia y listas en Python.")
        jr.route("Analiza la factura 77 del cliente Ficticio")
        self.assertEqual(self.api_calls(), [])

    def test_router_survives_broken_db(self):
        self.db.parent.mkdir(parents=True, exist_ok=True)
        self.db.write_bytes(b"no es sqlite " * 50)
        with self.assertLogs("jarvis.knowledge", "WARNING"):
            r = jr.route(self.PROMPT)
        self.assertTrue(r["backend"].startswith("deepseek"))
        self.assertEqual(self.api_calls()[0][1]["messages"][-1]["content"], self.PROMPT)

    def test_venice_gets_no_knowledge(self):
        self.index("jarvis", "El tope diario ficticio es de 300 dolares de prueba.")
        with mock.patch.object(jr, "ask_api", return_value=("ok", 1)) as api, \
                mock.patch.object(jr, "venice_ready", return_value=True):
            jr.ask_venice("Hola, explica el tope diario ficticio")
        sent = api.call_args[0][1][-1]["content"]
        self.assertNotIn("CONOCIMIENTO LOCAL", sent)


class Packaging(unittest.TestCase):
    def test_stdlib_only(self):
        import ast
        tree = ast.parse((ROOT / "jarvis_knowledge.py").read_text(encoding="utf-8"))
        mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        std = getattr(sys, "stdlib_module_names", None)
        if std is None:  # Python 3.9: comprobar que cada módulo viene de la instalación estándar
            import importlib.util
            import sysconfig
            stdlib = sysconfig.get_paths()["stdlib"]
            for m in mods - {"__future__"}:
                spec = importlib.util.find_spec(m)
                self.assertTrue(spec.origin in ("built-in", "frozen") or spec.origin.startswith(stdlib), m)
        else:
            self.assertTrue(mods <= set(std) | {"__future__"}, mods)

    def test_download_script_syntax(self):
        script = ROOT / "scripts" / "descargar_conocimiento.sh"
        subprocess.run(["bash", "-n", str(script)], check=True)
        text = script.read_text()
        self.assertIn("--proto '=https'", text)
        self.assertNotIn("http://", text)

    def test_cli_search_on_temp_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "docs"
            write_tree(src, {"tcp.md": "TCP usa un saludo de tres pasos ficticio."})
            db = str(Path(tmp) / "k.sqlite3")
            env = {k: v for k, v in os.environ.items() if k not in KNOWLEDGE_VARS}
            run = lambda *a: subprocess.run([sys.executable, str(ROOT / "jarvis_knowledge.py"), "--db", db, *a],
                                           capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(run("ingest", str(src), "--topic", "redes").returncode, 0)
            out = run("search", "saludo tres pasos", "-k", "1")
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("[redes] tcp.md — docs/tcp.md", out.stdout)
            self.assertIn("'redes': 1", run("stats").stdout)


if __name__ == "__main__":
    unittest.main()
