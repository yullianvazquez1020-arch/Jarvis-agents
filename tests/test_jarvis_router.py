"""Pruebas del enrutador. Usan un servidor HTTP falso en 127.0.0.1, sin red, con claves y datos ficticios."""
import asyncio, json, logging, os, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import test_jarvis as base
import jarvis_router as jr

j = base.j
FAKE_KEY = "clave-ficticia-123"
KEY_VARS = ("DEEPSEEK_API_KEY", "DASHSCOPE_API_KEY", "MOONSHOT_API_KEY")
CALLS = []          # (path, Authorization, body)
FAIL = set()        # path prefixes that answer 500
REPLY = {}          # path prefix -> reply text


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        CALLS.append((self.path, self.headers.get("Authorization"), body))
        prefix = "/" + self.path.strip("/").split("/")[0]
        if prefix == "/redir":
            self.send_response(302); self.send_header("Location", "/stolen/chat/completions")
            self.send_header("Content-Length", "0"); self.end_headers(); return
        if prefix in FAIL:
            self.send_response(500); self.send_header("Content-Length", "0"); self.end_headers(); return
        text = REPLY.get(prefix)
        if self.path == "/api/chat":
            out = {"message": {"content": text or "local-ok"}, "prompt_eval_count": 3, "eval_count": 4}
        else:
            out = {"choices": [{"message": {"content": text or f"api-ok{prefix}"}}], "usage": {"total_tokens": 9}}
        d = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(d))); self.end_headers(); self.wfile.write(d)


class RouterBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), Fake)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()

    def setUp(self):
        CALLS.clear(); FAIL.clear(); REPLY.clear()
        env = {"OLLAMA_URL": self.url, "DEEPSEEK_API_KEY": FAKE_KEY, "DASHSCOPE_API_KEY": "", "MOONSHOT_API_KEY": "", "VENICE_API_KEY": "",
               "JARVIS_API_ORDER": "deepseek,qwen,kimi", "JARVIS_LOCAL_MODEL": "", "JARVIS_ROUTER_ENABLED": "0"}
        for p in (patch.dict(os.environ, env),
                  patch.dict(jr.BASE_URLS, {n: f"{self.url}/{n}" for n in ("deepseek", "qwen", "kimi")})):
            p.start(); self.addCleanup(p.stop)

    def ollama_down(self):
        os.environ["OLLAMA_URL"] = "http://127.0.0.1:1"


class Routing(RouterBase):
    def test_simple_local(self):
        r = jr.route("Hola, ¿cómo estás?")
        self.assertEqual(r["backend"], "ollama:qwen3:4b-instruct"); self.assertEqual(r["text"], "local-ok")
        self.assertEqual(CALLS[0][2]["model"], "qwen3:4b-instruct"); self.assertIsNone(CALLS[0][1])

    def test_complex_api(self):
        r = jr.route("Escribe código Python para ordenar una lista")
        self.assertTrue(r["backend"].startswith("deepseek:deepseek-flash"))
        self.assertEqual(CALLS[-1][0], "/deepseek/chat/completions")
        self.assertEqual(CALLS[-1][1], f"Bearer {FAKE_KEY}")
        self.assertEqual(r["tokens"], 9)

    def test_sensitive_never_api(self):
        self.ollama_down()
        with self.assertRaises(jr.RouterError):
            jr.route("Factura del cliente Juan Pérez Ficticio, tel 787-555-0100", force="api")
        self.assertEqual(CALLS, [])

    def test_sensitive_goes_local_even_if_complex(self):
        r = jr.route("Analiza la estrategia de cobro para la factura 77 del cliente Ficticio")
        self.assertTrue(r["backend"].startswith("ollama")); self.assertEqual([c[0] for c in CALLS], ["/api/chat"])

    def test_sensitive_system_prompt_forces_local(self):
        self.ollama_down()
        with self.assertRaises(jr.RouterError):
            jr.route("Escribe código para ordenar", system="Correo del dueño ficticio: demo@example.test")
        self.assertEqual(CALLS, [])

    def test_fallback_when_ollama_down(self):
        self.ollama_down()
        self.assertTrue(jr.route("Dime un chiste corto")["backend"].startswith("deepseek"))

    def test_order_is_configurable_and_skips_unknown(self):
        os.environ.update(JARVIS_API_ORDER="openai, qwen ,deepseek", DASHSCOPE_API_KEY=FAKE_KEY)
        self.assertEqual(jr.api_order(), ["qwen", "deepseek"])
        r = jr.route("Escribe un plan corto")
        self.assertTrue(r["backend"].startswith("qwen:qwen-flash"))
        self.assertTrue(all("openai" not in c[0] for c in CALLS))

    def test_next_provider_when_one_fails(self):
        os.environ.update(DASHSCOPE_API_KEY=FAKE_KEY); FAIL.add("/deepseek")
        r = jr.route("Traduce esta frase al inglés")
        self.assertTrue(r["backend"].startswith("qwen"))

    def test_complex_uses_ollama_last(self):
        FAIL.add("/deepseek")
        r = jr.route("Escribe código Python")
        self.assertTrue(r["backend"].startswith("ollama"))
        self.assertEqual([c[0] for c in CALLS], ["/deepseek/chat/completions", "/api/chat"])

    def test_missing_key_no_leak(self):
        os.environ.pop("DEEPSEEK_API_KEY"); self.ollama_down()
        with self.assertRaises(jr.RouterError) as c:
            jr.route("Dime un chiste corto")
        self.assertNotIn("clave-ficticia", str(c.exception)); self.assertIn("DEEPSEEK_API_KEY", str(c.exception))
        self.assertEqual(CALLS, [])

    def test_env_read_at_call_time(self):
        os.environ.update(JARVIS_LOCAL_MODEL="modelo-ficticio:1b", DEEPSEEK_MODEL="deepseek-ficticio")
        jr.route("Hola"); self.assertEqual(CALLS[-1][2]["model"], "modelo-ficticio:1b")
        jr.route("Escribe código"); self.assertEqual(CALLS[-1][2]["model"], "deepseek-ficticio")

    def test_api_urls_are_fixed(self):
        self.assertEqual(jr.provider("kimi").key_env, "MOONSHOT_API_KEY")
        with self.assertRaises(jr.RouterError):
            jr.provider("openai")

    def test_think_block_stripped(self):
        REPLY["/api"] = "<think>razonamiento</think>Respuesta final"
        self.assertEqual(jr.route("Hola")["text"], "Respuesta final")

    def test_max_tokens_forwarded(self):
        jr.route("Hola", max_tokens=50); self.assertEqual(CALLS[-1][2]["options"], {"num_predict": 50})
        jr.route("Escribe código", max_tokens=60); self.assertEqual(CALLS[-1][2]["max_tokens"], 60)

    def test_empty_prompt_rejected(self):
        with self.assertRaises(jr.RouterError):
            jr.route("   ")
        self.assertEqual(CALLS, [])


class Safety(RouterBase):
    def test_detects_sensitive_fictitious_data(self):
        for t in ("escribe a demo@example.test", "llama al (787) 555-0100", "tel 939.555.0199",
                  "SSN 000-00-0000", "tarjeta 4111 1111 1111 1111", "la contraseña es ficticia",
                  "api_key de prueba", "token del bot", "dirección: Calle Ficticia 1", "invoice for customer",
                  "sk-ficticia1234567890", "el cliente pidió", "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"):
            with self.subTest(t=t):
                self.assertTrue(jr.is_sensitive(t))

    def test_plain_text_not_sensitive(self):
        for t in ("Dime un chiste corto", "¿Qué tiempo hace hoy?", "Hoy es 2026-10-10. Resume el mercado de acero."):
            with self.subTest(t=t):
                self.assertFalse(jr.is_sensitive(t))

    def test_remote_ollama_rejected_without_network(self):
        os.environ.update(OLLAMA_URL="http://10.0.0.5:11434", JARVIS_LOCAL_TIMEOUT="5")
        with patch.object(jr, "_post", wraps=jr._post) as post, self.assertRaises(jr.RouterError) as c:
            jr.route("El cliente Ficticio pidió precio")
        self.assertIn("no se envían", str(c.exception)); self.assertEqual(CALLS, [])
        post.assert_not_called()   # rejected before opening any connection
        with self.assertRaises(jr.RouterError) as c:
            jr.ask_ollama([{"role": "user", "content": "hola"}])
        self.assertIn("OLLAMA_URL", str(c.exception))

    def test_loopback_check(self):
        for u, ok in (("http://127.0.0.1:11434", True), ("http://localhost:11434", True), ("http://[::1]:1", True),
                      ("http://10.0.0.5", False), ("http://example.test", False), ("file:///etc", False)):
            with self.subTest(u=u):
                self.assertEqual(jr._is_loopback(u), ok)

    def test_redirect_not_followed(self):
        os.environ["DASHSCOPE_API_KEY"] = ""
        with patch.dict(jr.BASE_URLS, {"deepseek": f"{self.url}/redir"}):
            self.ollama_down()
            with self.assertRaises(jr.RouterError) as c:
                jr.route("Escribe código")
        self.assertIn("HTTP 302", str(c.exception))
        self.assertFalse(any(p.startswith("/stolen") for p, _, _ in CALLS))

    def test_logs_have_no_key_or_prompt(self):
        FAIL.add("/deepseek"); self.ollama_down()
        secret_prompt = "Escribe código con la frase ficticia ZAPATO-AZUL-42"
        with self.assertLogs("jarvis.router", level="WARNING") as logs, self.assertRaises(jr.RouterError) as c:
            jr.route(secret_prompt)
        text = "\n".join(logs.output) + str(c.exception)
        self.assertNotIn(FAKE_KEY, text); self.assertNotIn("ZAPATO-AZUL-42", text)

    def test_disabled_by_default(self):
        os.environ.pop("JARVIS_ROUTER_ENABLED")
        self.assertFalse(jr.enabled())
        for v, on in (("0", False), ("", False), ("no", False), ("1", True), ("true", True)):
            os.environ["JARVIS_ROUTER_ENABLED"] = v
            self.assertEqual(jr.enabled(), on)

    def test_status_has_no_values(self):
        s = jr.status()
        self.assertEqual(s["keys_present"], {"venice": False, "deepseek": True, "qwen": False, "kimi": False})
        self.assertNotIn(FAKE_KEY, json.dumps(s))

    def test_stdlib_only(self):
        # jarvis_knowledge (memoria local) is the only local import allowed, and it must be stdlib-only too.
        import ast, sys
        import jarvis_knowledge
        for path, local in ((jr.__file__, {"jarvis_knowledge"}), (jarvis_knowledge.__file__, set())):
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read())
            mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
            self.assertTrue(mods <= set(sys.stdlib_module_names) | {"__future__"} | local, mods)


class SingleGate(RouterBase):
    """main.llm_text: the only gate for text-only calls. Off = the same Anthropic call as before."""

    def setUp(self):
        super().setUp(); base.Tests.setUp(self)

    def anthropic_reply(self, text="anthropic-ok"):
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=1, output_tokens=2))

    def test_off_uses_anthropic_unchanged(self):
        with patch.object(j.client.messages, "create", new=AsyncMock(return_value=self.anthropic_reply())) as llm:
            out = asyncio.run(j.llm_text("sys", "Hola", 300))
        self.assertEqual((out.text, out.backend, out.tokens), ("anthropic-ok", "anthropic", 3))
        self.assertEqual(llm.call_args.kwargs, {"model": j.MODEL, "max_tokens": 300, "system": "sys",
                                                "messages": [{"role": "user", "content": "Hola"}]})
        self.assertEqual(CALLS, [])

    def test_on_uses_router_not_anthropic(self):
        os.environ["JARVIS_ROUTER_ENABLED"] = "1"
        with patch.object(j.client.messages, "create", new=AsyncMock()) as llm:
            out = asyncio.run(j.llm_text("Eres breve.", "Hola", 300))
        llm.assert_not_called()
        self.assertEqual((out.text, out.backend), ("local-ok", "router"))

    def test_on_sensitive_and_ollama_down_errors(self):
        os.environ["JARVIS_ROUTER_ENABLED"] = "1"; self.ollama_down()
        with patch.object(j.client.messages, "create", new=AsyncMock()) as llm, self.assertRaises(jr.RouterError):
            asyncio.run(j.llm_text("sys", "Cotiza para el cliente Ficticio, tel 787-555-0100"))
        llm.assert_not_called(); self.assertEqual(CALLS, [])

    def test_research_fallback_goes_through_gate(self):
        os.environ["JARVIS_ROUTER_ENABLED"] = "1"
        with patch.object(j, "WEB_SEARCH_ON", False), patch.object(j.client.messages, "create", new=AsyncMock()) as llm:
            text, live = asyncio.run(j._claude_research("Analiza tendencias generales del acero"))
        llm.assert_not_called(); self.assertFalse(live); self.assertIn("api-ok/deepseek", text)

    def test_connections_text_review_goes_through_gate(self):
        os.environ["JARVIS_ROUTER_ENABLED"] = "1"
        c = j._connections
        with patch.object(j, "AI_READY", True), patch.object(j.client.messages, "create", new=AsyncMock()) as llm:
            r = asyncio.run(c.claude("Hola, una idea de nombre para un taller"))
        llm.assert_not_called(); self.assertEqual(r["provider"], "router"); self.assertFalse(r["web_search_used"])

    def test_connections_web_still_anthropic(self):
        os.environ["JARVIS_ROUTER_ENABLED"] = "1"
        c = j._connections
        with patch.object(j, "AI_READY", True), \
                patch.object(j.client.messages, "create", new=AsyncMock(return_value=self.anthropic_reply())) as llm:
            r = asyncio.run(c.claude("Busca precios de acero", web=True))
        self.assertEqual(r["provider"], "claude"); self.assertIn("tools", llm.call_args.kwargs); self.assertEqual(CALLS, [])

    def test_video_plan_goes_through_gate(self):
        os.environ["JARVIS_ROUTER_ENABLED"] = "1"
        plan = {"title": "Colores", "description": "d", "language": "es",
                "scenes": [{"character": "shapes", "text": "Rojo", "narration": "Rojo", "color": "#ff0000",
                            "shape": "circle", "count": 1, "seconds": 5}] * 3}
        REPLY["/api"] = json.dumps(plan)
        with patch.object(j.client.messages, "create", new=AsyncMock()) as llm:
            out = asyncio.run(j._growth.create_video_plan("colores"))
        llm.assert_not_called(); self.assertEqual(out["status"], "planned")

    def test_tool_loop_never_routed(self):
        """The conversation loop with tools (payments, messages, approvals) does not use the router."""
        import inspect
        self.assertNotIn("llm_text", inspect.getsource(j._ai_call))
        self.assertNotIn("jarvis_router", inspect.getsource(j.run))


if __name__ == "__main__":
    unittest.main()


class VeniceDirect(unittest.TestCase):
    def test_venice_endpoint_and_sensitive_block(self):
        sent = []
        def fake(url, payload, headers, timeout, use_proxy):
            sent.append((url, payload)); return {"choices": [{"message": {"content": "hola"}}], "usage": {}}
        with patch.dict(os.environ, {"VENICE_API_KEY": "k", "VENICE_MODEL": "", "VENICE_ENABLED": "1"}), patch.object(jr, "_post", fake):
            self.assertEqual(jr.ask_venice("Hola")["text"], "hola")
            self.assertEqual(sent[0][0], "https://api.venice.ai/api/v1/chat/completions")
            self.assertEqual(sent[0][1]["model"], "venice-uncensored")
            with self.assertRaises(jr.RouterError):
                jr.ask_venice("mi password es abc")
            self.assertEqual(len(sent), 1)
