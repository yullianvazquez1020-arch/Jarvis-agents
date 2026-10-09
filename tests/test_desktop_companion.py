"""Mac companion (desktop/): local security, windows, intents, idempotent forwarding, cancel, engines, demo.

Standard library only. Jarvis is a fake local server; whisper.cpp and `say` are fake scripts. No microphone,
no network beyond 127.0.0.1, no real Jarvis, no money."""
import http.client
import http.server
import json
import logging
import os
import stat
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "desktop"))
import app as desk                          # noqa: E402
import intents                              # noqa: E402
from audio import engines                   # noqa: E402
from audio.wav import AudioError, check_wav, make_wav   # noqa: E402
import jarvis_client                        # noqa: E402


class FakeJarvis:
    """Just enough of /desktop/v1 to test the companion. Records every effect by request_id."""
    def __init__(self):
        self.effects = {}; self.calls = []; self.drop_first = set(); self.delay = 0.0; self.reply = "Respuesta de Jarvis"
        self.events = [{"type": "reply.text"}, {"type": "turn.done"}]; self.token = "jd1.1." + "T" * 43
        self.approved = False; self.pulse_delay = 0.0
        self.alerts = [{"key": "rem:1:x", "kind": "recordatorio", "text": "Recordatorio: llamar a Pedro", "when": "2026-10-06 21:00"}]
        self.cards = [{"id": "cobros", "title": "Cobros pendientes", "value": "$800.00", "lines": ["Ana — Cocina: $800.00"],
                       "as_of": "2026-10-06T21:00:00", "sensitive": True, "detail": "cobros"},
                      {"id": "balances", "title": "Balances", "value": "1 cuenta", "lines": ["Negocio: $95.00"],
                       "as_of": "2026-09-20", "stale": True, "sensitive": True},
                      {"id": "<script>", "title": "x", "lines": []}]
        owner = self
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a): pass
            def _out(self, code, body):
                b = json.dumps(body).encode(); self.send_response(code)
                self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b)))
                self.end_headers(); self.wfile.write(b)
            def do_GET(self):
                owner.calls.append(("GET", self.path, self.headers.get("Authorization")))
                if self.path == "/desktop/v1/status":
                    return self._out(200, {"jarvis_version": "4.0.3"})
                self._out(404, {"detail": "no"})
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                owner.calls.append(("POST", self.path, self.headers.get("Authorization"), body))
                if self.path == "/desktop/v1/pair/start":
                    return self._out(200, {"pairing_id": "p1", "claim_secret": "s" * 32, "code": "123456", "expires_in": 600})
                if self.path == "/desktop/v1/pair/claim":
                    return self._out(200, {"status": "approved", "token": owner.token, "device_id": "1"} if owner.approved
                                     else {"status": "pending"})
                if self.headers.get("Authorization") != "Bearer " + owner.token:
                    return self._out(401, {"detail": "credencial inválida"})
                if self.path == "/desktop/v1/pulse":
                    time.sleep(owner.pulse_delay)
                    return self._out(200, {"jarvis_version": "4.0.5", "storage": "upstash", "ai_configured": True,
                                           "crypto_mode": "practice", "coinbase_connected": False,
                                           "real_trading_active": False, "alerts": owner.alerts})
                if self.path == "/desktop/v1/hud":
                    return self._out(200, {"cards": owner.cards})
                if self.path == "/desktop/v1/panel":
                    return self._out(200, {"panel": body["name"], "title": "Cobros", "lines": ["<b>$400.00</b> Ana"],
                                           "speak": "Tienes $400 por cobrar", "sensitive": True, "as_of": "2026-10-06T20:00:00"})
                if self.path == "/desktop/v1/turns":
                    rid = body["request_id"]
                    if rid not in owner.effects:
                        time.sleep(owner.delay)
                        owner.effects[rid] = {"state": "done", "reply": owner.reply, "speak": owner.reply,
                                              "events": owner.events, "llm_used": True, "sensitive": False}
                        if rid in owner.drop_first:          # effect happened, response lost
                            owner.drop_first.discard(rid); self.close_connection = True
                            self.connection.shutdown(2); return
                    return self._out(200, owner.effects[rid])
                if self.path == "/desktop/v1/turns/get":
                    r = owner.effects.get(body["request_id"])
                    return self._out(200, r) if r else self._out(404, {"detail": "no"})
                self._out(404, {"detail": "no"})
        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def turn_posts(self):
        return [c for c in self.calls if c[0] == "POST" and c[1] == "/desktop/v1/turns"]

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close()


class FakeTTS:
    name = "fake"
    def __init__(self): self.texts = []
    def problem(self): return ""
    def synthesize(self, text, rate=1.0):
        self.texts.append((engines.speakable(text), rate)); return b"RIFFfake", "audio/wav"


class CompanionBase(unittest.TestCase):
    demo = False

    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.jarvis = FakeJarvis(); self.addCleanup(self.jarvis.close)
        cfg = dict(desk.DEFAULTS, VOICE_HOME=self.home, VOICE_PORT="0", VOICE_DEMO="true" if self.demo else "false",
                   JARVIS_SERVER_URL=self.jarvis.url)
        self.app, self.httpd, self.port = desk.serve(cfg)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close); self.addCleanup(self.httpd.shutdown)
        self.host = f"127.0.0.1:{self.port}"
        self.cookie = self.login()

    def req(self, method, path, body=None, raw=None, headers=None, cookie=True, ctype=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        h = {"Host": self.host}
        if method == "POST":
            h.update({"X-Jarvis-UI": "1", "Origin": f"http://{self.host}"})
        if cookie and getattr(self, "cookie", None):
            h["Cookie"] = "jd_session=" + self.cookie
        if raw is not None:
            data = raw; h["Content-Type"] = ctype or "audio/wav"
        elif body is not None:
            data = json.dumps(body).encode(); h["Content-Type"] = "application/json"
        else:
            data = None
        h.update(headers or {})
        c.request(method, path, body=data, headers=h)
        r = c.getresponse(); b = r.read(); c.close()
        try:
            j = json.loads(b)
        except ValueError:
            j = None
        return r.status, j, r, b

    def login(self):
        tok = self.app.new_launch()
        st, _, r, _ = self.req("GET", f"/?launch={tok}", cookie=False)
        self.assertEqual(st, 303)
        return r.getheader("Set-Cookie").split(";")[0].split("=", 1)[1]

    def pair(self):
        self.app.tokens.save(self.jarvis.token, "1")

    def wait_events(self, pred, timeout=5.0):
        end = time.time() + timeout; seen = []
        while time.time() < end:
            seen = list(self.app.events)
            if pred(seen):
                return seen
            time.sleep(0.05)
        self.fail(f"event not seen; got {[e['type'] for e in seen]}")

    def turn(self, text, rid):
        st, j, _, _ = self.req("POST", "/conversation/turns", {"request_id": rid, "text": text})
        self.assertEqual(st, 202, j)
        return self.wait_events(lambda ev: any(e["type"] in ("turn.done", "turn.error", "turn.late") and e.get("turn") == rid
                                               for e in ev))


class LocalSecurity(CompanionBase):
    def test_launch_link_single_use_and_session_required(self):
        tok = self.app.new_launch()
        self.assertEqual(self.req("GET", f"/?launch={tok}", cookie=False)[0], 303)
        self.assertEqual(self.req("GET", f"/?launch={tok}", cookie=False)[0], 401)       # used
        self.assertEqual(self.req("GET", "/api/state", cookie=False)[0], 401)
        self.assertEqual(self.req("GET", "/", cookie=False)[0], 401)
        self.assertEqual(self.req("GET", "/api/state")[0], 200)
        _, _, r, _ = self.req("GET", f"/?launch={self.app.new_launch()}", cookie=False)
        cookie = r.getheader("Set-Cookie")
        for flag in ("HttpOnly", "SameSite=Strict", "Path=/"):
            self.assertIn(flag, cookie)

    def test_expired_launch_link(self):
        tok = self.app.new_launch(); self.app.launch[tok] = time.time() - 1
        self.assertEqual(self.req("GET", f"/?launch={tok}", cookie=False)[0], 401)

    def test_host_origin_and_csrf_header(self):
        self.assertEqual(self.req("GET", "/api/state", headers={"Host": "evil.example:80"})[0], 400)   # DNS rebinding
        self.assertEqual(self.req("POST", "/api/prefs", {"discreet": True}, headers={"Origin": "https://evil.example"})[0], 403)
        self.assertEqual(self.req("POST", "/api/prefs", {"discreet": True}, headers={"X-Jarvis-UI": "0"})[0], 403)
        self.assertEqual(self.req("POST", "/api/prefs", {"discreet": True})[0], 200)

    def test_bind_refuses_all_interfaces(self):
        for host in ("0.0.0.0", "::", ""):
            with self.assertRaises(SystemExit):
                desk.check_bind(host, allow_lan=True)
        with self.assertRaises(SystemExit):
            desk.check_bind("192.168.1.20", allow_lan=False)
        self.assertEqual(desk.check_bind("127.0.0.1", False), "127.0.0.1")

    def test_token_never_reaches_browser_or_logs(self):
        self.pair()
        buf = []
        handler = logging.Handler(); handler.emit = lambda rec: buf.append(rec.getMessage())
        logging.getLogger("jarvis.desktop").addHandler(handler); logging.getLogger("jarvis.desktop").setLevel(logging.INFO)
        try:
            _, j, _, raw = self.req("GET", "/api/state")
            self.turn("¿qué hay de nuevo?", "tok-check-01")
            self.req("GET", f"/?launch={self.app.new_launch()}", cookie=False)
        finally:
            logging.getLogger("jarvis.desktop").removeHandler(handler)
        self.assertTrue(j["paired"])
        self.assertNotIn(self.jarvis.token.encode(), raw)
        self.assertNotIn(self.jarvis.token, " ".join(buf)); self.assertNotIn("launch=", " ".join(buf))
        events = json.dumps(self.app.events)
        self.assertNotIn(self.jarvis.token, events)
        # the token travelled only in the Authorization header
        self.assertTrue(all(self.jarvis.token not in c[1] for c in self.jarvis.calls))

    def test_token_file_is_private(self):
        self.pair()
        mode = stat.S_IMODE(os.stat(Path(self.home) / "device.json").st_mode)
        self.assertEqual(mode, 0o600)

    def test_server_url_must_be_https(self):
        for bad in ("http://jarvis.example.com", "https://user:pw@x.com", "https://x.com/?k=1", "ftp://x"):
            with self.assertRaises(ValueError):
                jarvis_client.check_url(bad)
        self.assertEqual(jarvis_client.check_url("https://jarvis-agents.onrender.com/"),
                         "https://jarvis-agents.onrender.com")


class Windows(CompanionBase):
    def test_one_audio_window_others_display_only(self):
        a = self.req("POST", "/api/window/hello", {"window": "win-a"})[1]
        b = self.req("POST", "/api/window/hello", {"window": "win-b"})[1]
        self.assertTrue(a["owner"]); self.assertFalse(b["owner"])
        self.req("POST", "/api/audio/claim", {"window": "win-b"})
        self.assertEqual(self.app.owner, "win-b")
        self.assertFalse(self.req("GET", "/api/events?since=0&window=win-a")[1]["owner"])

    def test_reload_with_same_request_id_does_not_repeat(self):
        self.pair()
        self.turn("¿cómo va todo?", "reload-0001")
        st, j, _, _ = self.req("POST", "/conversation/turns", {"request_id": "reload-0001", "text": "¿cómo va todo?"})
        self.assertEqual(st, 202); self.assertEqual(j["state"], "done")
        self.assertEqual(len(self.jarvis.turn_posts()), 1)
        self.assertEqual(self.req("POST", "/conversation/turns", {"request_id": "reload-0001", "text": "otra"})[0], 400)


class Turns(CompanionBase):
    def test_interface_orders_are_local(self):
        self.pair()
        for i, text in enumerate(("Silencio", "Jarvis, repite", "habla más despacio", "Apaga el micrófono")):
            self.turn(text, f"local-{i:05d}")
        self.assertEqual(self.jarvis.turn_posts(), [])
        self.assertAlmostEqual(self.app.prefs["rate"], 0.85)
        self.assertFalse(self.app.prefs["mic"])
        types = [e["type"] for e in self.app.events]
        self.assertIn("audio.stop", types); self.assertIn("mic.off", types)

    def test_codes_and_approvals_never_leave_the_mac(self):
        self.pair()
        for i, text in enumerate(("Confirma 123456", "/confirmar 3 123456", "aprueba la orden 4", "activa modo real")):
            ev = self.turn(text, f"money-{i:05d}")
            reply = [e for e in ev if e["type"] == "reply.text" and e["turn"] == f"money-{i:05d}"][0]["text"]
            self.assertIn("Telegram", reply)
        self.assertEqual(self.jarvis.turn_posts(), [])

    def test_panel_by_voice_uses_panel_endpoint_not_ai(self):
        self.pair()
        ev = self.turn("muéstrame los cobros", "panel-00001")
        p = [e for e in ev if e["type"] == "panel.open"][0]["data"]
        self.assertEqual(p["panel"], "cobros"); self.assertEqual(p["lines"], ["<b>$400.00</b> Ana"])   # shown as text
        self.assertEqual(self.jarvis.turn_posts(), [])

    def test_forward_retry_same_request_id_single_effect(self):
        self.pair(); self.jarvis.drop_first.add("retry-00001")
        ev = self.turn("¿cómo voy este mes?", "retry-00001")
        self.assertIn("Respuesta de Jarvis", [e.get("text") for e in ev if e["type"] == "reply.text"])
        posts = self.jarvis.turn_posts()
        self.assertGreaterEqual(len(posts), 2)
        self.assertEqual({p[3]["request_id"] for p in posts}, {"retry-00001"})    # same id on every retry
        self.assertEqual(len(self.jarvis.effects), 1)

    def test_server_events_are_filtered(self):
        self.pair()
        self.jarvis.events = [{"type": "panel.open", "panel": "../../secret"}, {"type": "exec", "cmd": "rm"},
                              {"type": "panel.open", "panel": "agenda", "html": "<script>"}]
        ev = self.turn("hola jarvis, ¿qué tal la semana?", "filter-0001")
        panels = [e for e in ev if e["type"] == "panel.open"]
        self.assertEqual([p["data"]["panel"] for p in panels], ["agenda"])
        self.assertNotIn("exec", [e["type"] for e in ev])

    def test_cancel_drops_late_answer(self):
        self.pair(); self.app.tts = FakeTTS(); self.app.owner = "win-a"; self.jarvis.delay = 0.8
        self.req("POST", "/conversation/turns", {"request_id": "cancel-0001", "text": "pregunta larga"})
        time.sleep(0.2)
        st, j, _, _ = self.req("POST", "/conversation/turns/cancel-0001/cancel", {})
        self.assertEqual(st, 200); self.assertFalse(j["already_done"])
        ev = self.wait_events(lambda ev: any(e["type"] == "turn.late" for e in ev))
        self.assertFalse([e for e in ev if e["type"] in ("reply.text", "audio.play") and e.get("turn") == "cancel-0001"])
        self.assertEqual(self.app.tts.texts, [])

    def test_offline_server_degrades_to_text(self):
        self.pair(); self.jarvis.close()
        ev = self.turn("¿qué tengo pendiente?", "offline-001")
        reply = [e for e in ev if e["type"] == "reply.text"][0]["text"]
        self.assertIn("sin conexión", reply); self.assertIn("turn.error", [e["type"] for e in ev])

    def test_discreet_mode_never_reads_amounts(self):
        self.pair(); self.app.tts = FakeTTS(); self.app.owner = "win-a"
        self.app.set_prefs(discreet=True)
        self.turn("muéstrame los cobros", "discreet-01")
        self.assertEqual(self.app.tts.texts[-1][0], "Te lo dejé en pantalla.")

    def test_unpaired_device_gets_no_private_data(self):
        ev = self.turn("¿cuánto me deben?", "unpaired-01")
        self.assertEqual(self.jarvis.turn_posts(), [])
        self.assertTrue(all("$400" not in json.dumps(e) for e in ev))


class ExpiredOnServer(CompanionBase):
    """4.0.5 (2.2): if Jarvis says the token expired or was revoked, the Mac forgets it and offers pairing."""
    def test_401_forgets_token(self):
        self.pair(); self.jarvis.token = "jd1.1." + "Z" * 43          # server no longer accepts ours
        ev = self.turn("¿qué tal la semana?", "expired-001")
        self.assertFalse(self.app.tokens.load())
        self.assertIn("removed", [e.get("status") for e in ev if e["type"] == "pairing"])
        self.assertFalse(self.req("GET", "/api/state")[1]["paired"])


class Demo(CompanionBase):
    demo = True

    def test_demo_is_labeled_and_never_calls_jarvis(self):
        _, p, _, _ = self.req("GET", "/api/panels/cobros")
        self.assertTrue(p["demo"]); self.assertIn("DEMO", p["title"])
        ev = self.turn("¿cómo voy?", "demo-00001")
        self.assertIn("DEMO", [e for e in ev if e["type"] == "reply.text"][0]["text"])
        self.assertEqual(self.jarvis.calls, [])
        self.assertTrue(self.req("GET", "/api/state")[1]["demo"])


class Pairing(CompanionBase):
    def test_pairing_flow_saves_token_privately(self):
        self.jarvis.approved = True                      # the owner approves right away in Telegram
        st, j, _, _ = self.req("POST", "/api/pair/start", {})
        self.assertEqual((st, j["code"]), (200, "123456"))
        self.app._pair_poll(every=0.01)                  # a second poller exits at once: only one claims
        self.wait_events(lambda ev: any(e["type"] == "pairing" and e.get("status") == "approved" for e in ev))
        self.assertEqual(self.app.tokens.load(), self.jarvis.token)
        self.assertEqual(sum(1 for c in self.jarvis.calls if c[1] == "/desktop/v1/pair/claim"), 1)
        self.assertTrue(self.req("GET", "/api/state")[1]["paired"])
        self.assertNotIn("secret", json.dumps(self.req("GET", "/api/state")[1]))


class TokenFileRace(unittest.TestCase):
    """Found while testing 4.0.5: a reader must never see a half-written token file, and having no token is
    'not paired' (no request sent), never 'revoked by Jarvis'."""
    def test_atomic_save_under_concurrent_reads(self):
        store = jarvis_client.TokenStore(tempfile.mkdtemp()); store.save("jd1.1." + "A" * 43, "1")
        bad = []; stop = threading.Event()
        def reader():
            while not stop.is_set():
                if store.load() not in ("jd1.1." + "A" * 43, "jd1.1." + "B" * 43):
                    bad.append(1)
        t = threading.Thread(target=reader); t.start()
        for i in range(300):
            store.save("jd1.1." + ("A" if i % 2 else "B") * 43, "1")
        stop.set(); t.join()
        self.assertEqual(bad, []); self.assertEqual([p.name for p in store.folder.iterdir()], ["device.json"])

    def test_no_token_is_unpaired_not_revoked(self):
        c = jarvis_client.JarvisClient("https://jarvis.example.com", lambda: "")
        with self.assertRaises(jarvis_client.ServerError) as ctx:
            c.pulse()
        self.assertEqual(ctx.exception.status, jarvis_client.UNPAIRED)


class AudioInput(CompanionBase):
    def test_wav_validation(self):
        good = make_wav([0] * 16000)
        self.assertEqual(check_wav(good), 1.0)
        bad = [b"", b"RIFF" + b"\0" * 40, good[:30], good.replace(b"\x80\x3e\x00\x00", b"\x44\xac\x00\x00", 1),
               make_wav([0] * 100), b"RIFF" + b"\xff" * 2_000_000]
        for b in bad:
            with self.assertRaises(AudioError):
                check_wav(b)

    def test_transcribe_without_engine_is_honest(self):
        st, j, _, _ = self.req("POST", "/voice/transcribe", raw=make_wav([0] * 16000))
        self.assertEqual(st, 503); self.assertIn("no configurado", j["error"])
        st, _, _, _ = self.req("POST", "/voice/transcribe", raw=b"x" * 100, ctype="audio/mp4")
        self.assertEqual(st, 415)

    def test_whisper_cpp_adapter_and_cleanup(self):
        tmp = Path(tempfile.mkdtemp())
        fake = tmp / "whisper-cli"
        fake.write_text("#!/bin/sh\nwhile [ $# -gt 0 ]; do case $1 in -of) out=$2; shift;; -f) f=$2; shift;; esac; shift; done\n"
                        "echo \"$f\" > \"" + str(tmp) + "/seen\"\nprintf ' Hola [BLANK_AUDIO] Jarvis, léeme la agenda ' > \"$out.txt\"\n")
        fake.chmod(0o755); model = tmp / "ggml-base.bin"; model.write_bytes(b"m")
        w = engines.WhisperCpp(str(fake), str(model))
        self.assertEqual(w.problem(), "")
        out = w.transcribe(make_wav([1000, -1000] * 8000))
        self.assertEqual(out["text"], "Hola Jarvis, léeme la agenda"); self.assertEqual(out["language"], "es")
        used = Path((tmp / "seen").read_text().strip())
        self.assertFalse(used.exists())                                   # temporary audio deleted
        (tmp / "ggml-base.en.bin").write_bytes(b"m")
        self.assertIn("solo inglés", engines.WhisperCpp(str(fake), str(tmp / "ggml-base.en.bin")).problem())


class AudioOutput(unittest.TestCase):
    def test_macos_say_adapter_text_by_file_and_sanitized(self):
        tmp = Path(tempfile.mkdtemp()); say = tmp / "say"
        say.write_text("#!/bin/sh\nargs=\"$*\"\necho \"$args\" > \"" + str(tmp) + "/args\"\n"
                       "while [ $# -gt 0 ]; do case $1 in -o) out=$2; shift;; -f) f=$2; shift;; esac; shift; done\n"
                       "cp \"$f\" \"" + str(tmp) + "/text\"\nprintf 'RIFFwav' > \"$out\"\n")
        say.chmod(0o755)
        with patch.dict(os.environ, {"PATH": f"{tmp}:{os.environ['PATH']}"}), patch.object(sys, "platform", "darwin"):
            audio, ctype = engines.MacSay("Paulina").synthesize(
                "Listo 🎉 **tienes** https://x.com sk-ant-api03-" + "Z" * 30 + " jd1.4." + "Y" * 40, rate=0.85)
        self.assertEqual((audio, ctype), (b"RIFFwav", "audio/wav"))
        spoken = (tmp / "text").read_text()
        for bad in ("🎉", "**", "https", "ZZZZ", "YYYY"):
            self.assertNotIn(bad, spoken)
        args = (tmp / "args").read_text()
        self.assertIn("-v Paulina", args); self.assertIn("-r 148", args); self.assertNotIn("tienes", args)

    def test_no_engine_reports_unavailable(self):
        s, t = engines.build({"VOICE_STT_BACKEND": "none", "VOICE_TTS_BACKEND": "none"})
        self.assertTrue(s.problem()); self.assertTrue(t.problem())
        with patch.object(sys, "platform", "linux"):
            self.assertIn("macOS", engines.MacSay().problem())


class IntentTable(unittest.TestCase):
    def test_table_from_the_plan(self):
        cases = {"Jarvis, ¿cómo estás?": ("health", None), "Léeme la agenda": ("panel", "agenda"),
                 "Muéstrame los cobros": ("panel", "cobros"), "Abre práctica": ("panel", "practica"),
                 "Repite": ("repeat", None), "Habla más despacio": ("slower", None), "Silencio": ("stop_audio", None),
                 "Apaga el micrófono": ("mic_off", None), "Confirma 123456": "refuse",
                 "Anota un gasto de 25 dólares": "refuse", "Compra 100 dólares de bitcoin": "refuse",
                 "¿Cuánto le cobré a Ana el mes pasado por la cocina y cuánto me falta?": ("server", None), "": ("empty", None)}
        for text, want in cases.items():
            got = intents.parse(text)
            self.assertEqual(got[0] if want == "refuse" else got, want, text)


class ActionPhrasesStayOnTheMac(CompanionBase):
    """4.0.5 (1.3): action phrases are refused locally and never reach Jarvis."""
    PHRASES = ("confirma la orden", "aprueba la 3", "rechaza la orden 2", "activa modo real", "envíale el correo a Ana",
               "anota un gasto de 25", "apunta 40 de gasolina", "ejecuta la acción 1", "restaura la copia de ayer",
               "borra el recordatorio", "elimina el cliente Pedro", "código 482 913", "compra 100 de bitcoin",
               "/aprobar 3", "transfiere 50 a mi cuenta", "retira todo")

    def test_refused_locally(self):
        self.pair()
        for i, text in enumerate(self.PHRASES):
            ev = self.turn(text, f"act-{i:06d}")
            reply = [e for e in ev if e["type"] == "reply.text" and e["turn"] == f"act-{i:06d}"][0]["text"]
            self.assertIn("Telegram", reply, text)
        self.assertEqual(self.jarvis.turn_posts(), [])

    def test_questions_still_go_through(self):
        for text in ("¿cuánto me deben?", "¿qué opinas de mi semana?", "¿cómo van los trabajos de Ana?"):
            self.assertEqual(intents.parse(text)[0], "server", text)


class Displays(CompanionBase):
    """4.0.5 Part 3: top bar health, HUD, alerts once, local orders, DEMO."""
    def test_health_states_for_the_dot(self):
        self.pair(); self.app.pulse_once()
        h = self.req("GET", "/api/state")[1]["server"]
        self.assertEqual(h["state"], "ok"); self.assertEqual(h["info"]["crypto_mode"], "practice")
        self.assertFalse(h["info"]["real_trading_active"])
        with patch.object(desk, "SLOW_MS", 1):
            self.jarvis.pulse_delay = 0.05; self.app.pulse_once()
        self.assertEqual(self.app.health_view()["state"], "slow")
        self.jarvis.close(); self.app.pulse_once()
        self.assertEqual(self.app.health_view()["state"], "down")

    def test_alerts_shown_once_even_after_restart(self):
        self.pair(); self.app.tts = FakeTTS(); self.app.owner = "win-a"
        self.app.pulse_once(); self.app.pulse_once()
        alerts = [e for e in self.app.events if e["type"] == "alert"]
        self.assertEqual(len(alerts), 1); self.assertEqual(len(self.app.tts.texts), 1)
        again = desk.Companion(dict(self.app.cfg))            # restart: same home folder
        again.tokens.save(self.jarvis.token, "1"); again.pulse_once()
        self.assertEqual([e for e in again.events if e["type"] == "alert"], [])
        self.req("POST", "/api/alerts/repeat", {})
        self.assertEqual(len(self.app.tts.texts), 2)

    def test_discreet_alert_does_not_read_names(self):
        self.pair(); self.app.tts = FakeTTS(); self.app.owner = "win-a"; self.app.set_prefs(discreet=True)
        self.jarvis.alerts = [{"key": "bill:9", "kind": "cuenta", "text": "Cuenta vencida: Luz $120.50", "when": "x"}]
        self.app.pulse_once()
        self.assertEqual(self.app.tts.texts[-1][0], "Te lo dejé en pantalla.")

    def test_hud_filters_cards_and_opens_detail_in_main_window(self):
        self.pair()
        st, h, _, _ = self.req("GET", "/api/hud")
        self.assertEqual([c["id"] for c in h["cards"]], ["cobros", "balances"])        # unknown card dropped
        self.assertTrue(h["cards"][1]["stale"])
        self.req("POST", "/api/open", {"target": "balances"})
        ev = [e for e in self.app.events if e["type"] == "panel.open"][-1]
        self.assertEqual(ev["data"]["panel"], "hud:balances"); self.assertEqual(ev["data"]["lines"], ["Negocio: $95.00"])
        self.assertEqual(self.req("POST", "/api/open", {"target": "../x"})[0], 404)
        self.assertEqual(self.jarvis.turn_posts(), [])                                    # showing never writes

    def test_local_health_answer_has_no_balances(self):
        self.pair(); self.app.pulse_once()
        ev = self.turn("Jarvis, ¿cómo estás?", "health-0001")
        reply = [e for e in ev if e["type"] == "reply.text"][0]["text"]
        for word in ("Servidor", "Voz", "Micrófono", "Ventanas"):
            self.assertIn(word, reply)
        self.assertNotIn("$", reply); self.assertEqual(self.jarvis.turn_posts(), [])

    def test_mic_on_and_discreet_mode_by_voice(self):
        self.turn("apaga el micrófono", "mic-000001"); self.assertFalse(self.app.prefs["mic"])
        self.turn("enciende el micrófono", "mic-000002"); self.assertTrue(self.app.prefs["mic"])
        self.turn("modo discreto", "disc-00001"); self.assertTrue(self.app.prefs["discreet"])
        self.turn("desactiva el modo discreto", "disc-00002"); self.assertFalse(self.app.prefs["discreet"])

    def test_hud_page_requires_session(self):
        self.assertEqual(self.req("GET", "/hud", cookie=False)[0], 401)
        st, _, r, body = self.req("GET", "/hud")
        self.assertEqual(st, 200); self.assertIn(b"HUD", body)
        self.assertEqual(self.req("GET", "/ui/hud.js")[0], 200); self.assertEqual(self.req("GET", "/ui/mask.js")[0], 200)

    def test_avatar_preserves_session_guard_and_content_security_policy(self):
        self.assertEqual(self.req("GET", "/avatar", cookie=False)[0], 401)
        self.assertEqual(self.req("GET", "/ui/avatar.js", cookie=False)[0], 401)
        status, _, response, body = self.req("GET", "/avatar")
        self.assertEqual(status, 200)
        self.assertIn('Probar boca (sin audio)'.encode(), body)       # la frase de prueba se rotula como aproximada
        self.assertIn(b'id="voice-status"', body)
        self.assertNotIn(b'<script>', body)
        self.assertIn("script-src 'self'", response.getheader('Content-Security-Policy'))
        self.assertEqual(self.req("GET", "/ui/avatar.js")[0], 200)
        self.assertEqual(self.req("GET", "/ui/lipsync.js")[0], 200)
        self.assertEqual(self.req("GET", "/ui/lipsync.js", cookie=False)[0], 401)
        self.assertEqual(self.req("GET", "/ui/avatar.css")[0], 200)


class DemoDisplays(CompanionBase):
    demo = True

    def test_demo_cards_and_alerts_are_labeled_and_offline(self):
        h = self.req("GET", "/api/hud")[1]
        self.assertTrue(h["demo"]); self.assertTrue(all("DEMO" in c["title"] for c in h["cards"]))
        self.app.pulse_once()
        self.assertEqual(self.app.health_view()["state"], "demo")
        self.assertIn("DEMO", [e for e in self.app.events if e["type"] == "alert"][0]["text"])
        self.assertEqual(self.jarvis.calls, [])


class JavaScript(unittest.TestCase):
    def test_js_syntax_and_wav_encoder(self):
        import shutil, subprocess
        node = shutil.which("node")
        if not node:
            self.skipTest("node no está instalado")
        ui = ROOT / "desktop" / "ui"
        for f in ("app.js", "wav.js"):
            self.assertEqual(subprocess.run([node, "--check", str(ui / f)]).returncode, 0, f)
        script = ("const W=require(%r);const s=new Float32Array(48000).map((_,i)=>Math.sin(i/10)*0.5);"
                  "const d=W.downsample(s,48000);const b=Buffer.from(W.encodeWav(d));process.stdout.write(b.toString('base64'));"
                  "const det=new W.Detector({silenceMs:300});let r=null;for(let i=0;i<10;i++)r=det.push(new Float32Array(160).fill(0.2),10);"
                  "for(let i=0;i<40&&r!=='silence-end';i++)r=det.push(new Float32Array(160),10);if(r!=='silence-end')process.exit(3);"
                  ) % str(ui / "wav.js")
        mask = subprocess.run([node, "-e", "const M=require(%r);process.stdout.write(JSON.stringify(["
                               "M.mask('Tienes $1,234.56 y 120.50, código 482913, cuenta 1234567'),M.hasSensitive('hola')]))"
                               % str(ui / "mask.js")], stdout=subprocess.PIPE)
        masked, flag = json.loads(mask.stdout)
        for bad in ("1,234", "120.50", "482913", "1234567"):
            self.assertNotIn(bad, masked)
        self.assertFalse(flag)
        for f in ("hud.js", "mask.js"):
            self.assertEqual(subprocess.run([node, "--check", str(ui / f)]).returncode, 0, f)
        out = subprocess.run([node, "-e", script], stdout=subprocess.PIPE)
        self.assertEqual(out.returncode, 0)
        import base64
        self.assertEqual(check_wav(base64.b64decode(out.stdout)), 1.0)    # what Safari sends passes the Python check

    def test_lipsync_follows_known_bursts_and_robust_clock(self):
        """Envolvente de un WAV con ráfagas en instantes conocidos (la misma voz de prueba que usa la medición)."""
        import shutil, subprocess, tempfile
        node = shutil.which("node")
        if not node:
            self.skipTest("node no está instalado")
        ui = ROOT / "desktop" / "ui"
        for f in ("lipsync.js", "avatar.js", "app.js"):
            self.assertEqual(subprocess.run([node, "--check", str(ui / f)]).returncode, 0, f)
        fake = ROOT / "scripts" / "fake_tts_bursts.py"
        spans = json.loads(subprocess.run([sys.executable, str(fake), "--schedule"], stdout=subprocess.PIPE).stdout)["spans"]
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "b.wav"
            subprocess.run([sys.executable, str(fake), "--output_file", str(wav)], input=b"x", check=True)
            script = r"""
const L=require(%r),fs=require('fs');const b=fs.readFileSync(%r);const n=(b.length-44)/2,s=new Float32Array(n);
for(let i=0;i<n;i++)s[i]=b.readInt16LE(44+i*2)/32768;
const e=L.envelope(s,22050);let p=0,on=[],off=[];e.values.forEach((v,i)=>{if(v>=.5&&p<.5)on.push(i/e.fps);if(v<.5&&p>=.5)off.push(i/e.fps);p=v});
const c=new L.ClockFilter(),id='a';
for(let k=0;k<9;k++)c.push({id,t:k*.1,at:1000+k*100,rate:1,playing:true});
c.push({id,t:.9,at:1000+900+40,rate:1,playing:true});            // un mensaje tardío no mueve la mediana
const steady=c.position(2000);
c.push({id,t:5,at:2100,rate:1,playing:true});                      // salto: reinicia
const jumped=c.position(2100);
c.push({id,t:5.2,at:2300,rate:1,playing:false});
const paused=c.position(9999);
const f=new L.Follower();let v=0;for(let i=0;i<10;i++)v=f.step(1,16);const up=v;for(let i=0;i<10;i++)v=f.step(0,16);
process.stdout.write(JSON.stringify({on,off,steady,jumped,paused,up,down:v,
  ok:[L.valid({k:'clock',id:'x',t:1,at:2}),L.valid({k:'env',id:'x',fps:100,values:[0]}),L.valid({k:'stop',id:'x'})],
  bad:[L.valid({k:'env',id:'x',fps:0,values:[]}),L.valid({k:'run',id:'x'}),L.valid(null),L.valid({k:'clock',id:1,t:1,at:1})],
  outside:[L.level(e,-1),L.level(e,99)]}));""" % (str(ui / "lipsync.js"), str(wav))
            out = json.loads(subprocess.run([node, "-e", script], stdout=subprocess.PIPE, check=True).stdout)
        for (a, b), on, off in zip(spans, out["on"], out["off"]):
            self.assertLessEqual(abs(on - a), 0.011)                         # una muestra de 10 ms
            self.assertLessEqual(abs(off - b), 0.011)
        self.assertEqual(len(out["on"]), len(spans))
        self.assertAlmostEqual(out["steady"], 1.0, delta=0.005)
        self.assertAlmostEqual(out["jumped"], 5.0, delta=0.005)
        self.assertEqual(out["paused"], 5.2)
        self.assertGreater(out["up"], 0.95); self.assertLess(out["down"], 0.05)
        self.assertEqual(out["ok"], [True, True, True]); self.assertEqual(out["bad"], [False, False, False, False])
        self.assertEqual(out["outside"], [0, 0])


if __name__ == "__main__":
    unittest.main()
