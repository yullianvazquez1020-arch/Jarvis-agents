"""Modo autónomo del mouse (desktop/mac/autonomo.py). pyautogui simulado: aquí nunca se mueve el mouse."""
import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1] / "desktop" / "mac"
spec = importlib.util.spec_from_file_location("autonomo", ROOT / "autonomo.py")
au = importlib.util.module_from_spec(spec)
spec.loader.exec_module(au)
ae = au.ae


class FakePointer:
    """Imita AutoPointer; cada orden recibida queda en calls."""

    def __init__(self, front="Safari", script=None):
        self.calls, self.front, self.script = [], front, list(script or [])

    def shot(self, path):
        Path(path).write_bytes(b"png")
        if self.script:  # el "agente" mira la pantalla y deja la próxima orden
            (au.auto_dir() / "siguiente.json").write_text(json.dumps(self.script.pop(0)))

    def size(self):
        return (1440, 900)

    def position(self):
        return (10, 10)

    def frontmost(self):
        return self.front

    def page_url(self):
        return ""  # leer la página no es una orden: no entra en calls

    def __getattr__(self, name):
        return lambda *a: self.calls.append((name,) + a)


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        rc = fn(*a, **kw)
    return rc, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        env = {"JARVIS_CONTROL_DIR": self.tmp.name + "/c", "JARVIS_OWNER_DIR": self.tmp.name + "/o"}
        self.env = patch.dict(os.environ, env)
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def open(self, agent="claude", minutes=10):
        captured = {}

        def ask(prompt):
            captured["code"] = prompt.split("Escribe ")[1].split(" ")[0]
            return captured["code"]
        rc, _ = quiet(au.start, agent, minutes, ask=ask, tty=True)
        self.assertEqual(rc, 0)

    def go(self, script, front="Safari", steps=None):
        p = FakePointer(front, script)
        quiet(au.run, p, sleep=lambda s: None, max_steps=steps or len(script))
        return p


class StartTests(Base):
    def test_requires_terminal(self):
        self.assertEqual(quiet(au.start, "claude", 10, ask=lambda p: "x", tty=False)[0], 2)
        self.assertIsNone(au.read_session())

    def test_wrong_code(self):
        self.assertEqual(quiet(au.start, "claude", 10, ask=lambda p: "000000", tty=True)[0], 3)
        self.assertIsNone(au.read_session())

    def test_unknown_agent(self):
        self.assertEqual(quiet(au.start, "intruso", 10, ask=lambda p: "x", tty=True)[0], 2)

    def test_cap_30_minutes(self):
        self.open(minutes=999)
        s = au.read_session()
        span = ae.parse_stamp(s["expires"]) - ae.parse_stamp(s["started"])
        self.assertLessEqual(span.total_seconds(), 30 * 60)

    def test_agent_cannot_forge_session_in_control_dir(self):
        (ae.control_dir() / "autonomo.json").write_text(json.dumps({"agent": "claude", "expires": "2999-01-01T00:00:00+00:00"}))
        self.assertIsNone(au.read_session())
        self.assertEqual(quiet(au.run, FakePointer(), sleep=lambda s: None)[0], 2)

    def test_stop_blocks_start(self):
        (ae.control_dir() / "STOP").touch()
        self.assertEqual(quiet(au.start, "claude", 10, ask=lambda p: "x", tty=True)[0], 3)


class RunTests(Base):
    def test_autonomous_move_click_double_scroll_type(self):
        self.open()
        p = self.go([
            {"agent": "claude", "action": "move", "x": 700, "y": 400},
            {"agent": "claude", "action": "click", "x": 700, "y": 400},
            {"agent": "claude", "action": "double_click", "x": 300, "y": 200},
            {"agent": "claude", "action": "scroll", "dy": -3},
            {"agent": "claude", "action": "type", "text": "hola mundo"},
        ], front="Notes")                                           # app verificada (no navegador)
        names = [c[0] for c in p.calls]
        self.assertEqual(names, ["move", "click", "double_click", "scroll", "write"])
        estado = json.loads((au.auto_dir() / "estado.json").read_text())
        self.assertEqual(estado["ancho"], 1440)
        self.assertEqual(estado["ultimo"]["resultado"], "HECHO")

    def test_session_closed_after_run(self):
        self.open()
        self.go([{"agent": "claude", "action": "scroll", "dy": 1}])
        self.assertIsNone(au.read_session())
        self.assertIsNone(ae.read_lock())

    def test_blocked_actions_never_reach_pointer(self):
        self.open()
        p = self.go([
            {"agent": "claude", "action": "hotkey", "keys": ["command", "q"]},
            {"agent": "claude", "action": "open_url", "url": "https://www.bancopopular.com"},
            {"agent": "claude", "action": "open_url", "url": "https://ejemplo-no-permitido.com"},
            {"agent": "claude", "action": "open_app", "app": "Terminal"},
            {"agent": "claude", "action": "type", "text": "sudo rm -rf /"},
            {"agent": "claude", "action": "type", "text": "linea\n"},
            {"agent": "claude", "action": "type", "text": "x" * 500},
            {"agent": "grok", "action": "click", "x": 5, "y": 5},
            {"agent": "claude", "action": "click", "x": 2, "y": 2},
            {"agent": "claude", "action": "click", "x": 5000, "y": 10},
            "basura",
        ])
        self.assertEqual(p.calls, [])
        rows = [json.loads(l) for l in (ae.control_dir() / "audit.jsonl").read_text().splitlines()]
        self.assertTrue(all(r["verdict"] == "BLOQUEADO" for r in rows))

    def test_click_blocked_when_front_app_denied(self):
        for front in ("Terminal", "Mail", "WhatsApp", "Finder", "Banco Popular", ""):
            with self.subTest(front=front):
                self.open()
                p = self.go([{"agent": "claude", "action": "click", "x": 100, "y": 100}], front=front)
                self.assertEqual(p.calls, [])

    def test_scroll_ok_even_on_denied_front(self):
        self.open()
        p = self.go([{"agent": "claude", "action": "scroll", "dy": 2}], front="Terminal")
        self.assertEqual(p.calls, [("scroll", 2)])

    def test_stop_file_halts(self):
        self.open()
        (ae.control_dir() / "STOP").touch()
        p = self.go([{"agent": "claude", "action": "click", "x": 100, "y": 100}])
        self.assertEqual(p.calls, [])

    def test_ftp_no_apaga_la_sesion(self):
        self.open()
        p = self.go([{"agent": "claude", "action": "open_url", "url": "ftp://github.com/x"}])
        self.assertEqual(p.calls, [])
        self.assertFalse(ae.stopped())

    def test_cada_clic_revisa_la_url_de_safari(self):
        self.open()

        class Pages(FakePointer):
            def __init__(self):
                super().__init__("Safari", [
                    {"agent": "claude", "action": "open_url", "url": "https://github.com/x"},
                    {"agent": "claude", "action": "click", "x": 100, "y": 100},
                    {"agent": "claude", "action": "click", "x": 120, "y": 120},
                ])
                self.urls = iter([
                    "",
                    "https://github.com/x",
                    "https://github.com/x",
                    "https://mail.google.com/mail",
                ])

            def page_url(self):
                return next(self.urls)

        p = Pages()
        quiet(au.run, p, sleep=lambda s: None, max_steps=3)
        self.assertEqual([c[0] for c in p.calls], ["open_url", "click"])
        self.assertFalse(ae.stopped())

    def test_rate_limit(self):
        self.open()
        script = [{"agent": "claude", "action": "scroll", "dy": 1}] * (ae.MAX_PER_MINUTE + 5)
        p = self.go(script)
        self.assertEqual(len(p.calls), ae.MAX_PER_MINUTE)

    def msg_pointer(self, front, script, labels=None, titles=None, fronts=None):
        class Msg(FakePointer):
            def window_title(self_):
                return titles.pop(0) if titles else "Bandeja de entrada"

            def element_label(self_, x, y):
                return labels.pop(0) if labels else "Mensaje de Ana | fila"

            def frontmost(self_):
                return fronts.pop(0) if fronts else front
        return Msg(front, script)

    def run_msg(self, p, steps):
        quiet(au.run, p, sleep=lambda s: None, max_steps=steps)
        return [c[0] for c in p.calls]

    def reasons(self):
        rows = [json.loads(l) for l in (ae.control_dir() / "audit.jsonl").read_text().splitlines()]
        return [r["reason"] for r in rows]

    def test_outlook_and_slack_allow_move_click_scroll(self):
        for front in ("Microsoft Outlook", "Slack"):
            with self.subTest(front=front):
                self.open()
                p = self.msg_pointer(front, [
                    {"agent": "claude", "action": "move", "x": 400, "y": 300},
                    {"agent": "claude", "action": "click", "x": 400, "y": 300},
                    {"agent": "claude", "action": "scroll", "dy": -3},
                    {"agent": "claude", "action": "screenshot"},
                ])
                self.assertEqual(self.run_msg(p, 4)[:3], ["move", "click", "scroll"])
                self.assertFalse(ae.stopped())

    def test_outlook_and_slack_never_click_send_delete_or_settings(self):
        for front in ("Microsoft Outlook", "Slack"):
            for label in ("Send", "Enviar", "Responder a todos", "Reply", "Forward", "Delete", "Eliminar",
                          "Move to Trash", "Papelera", "Archivar", "Settings", "Preferencias", "Post message"):
                with self.subTest(front=front, label=label):
                    self.open()
                    p = self.msg_pointer(front, [{"agent": "claude", "action": "click", "x": 400, "y": 300}], labels=[label])
                    self.assertEqual(self.run_msg(p, 1), [])
                    self.assertIn("autonomo:accion_de_envio", self.reasons())

    def test_outlook_and_slack_never_type_enter_or_hotkeys(self):
        for front in ("Microsoft Outlook", "Slack"):
            for order in ({"agent": "claude", "action": "type", "text": "hola"},
                          {"agent": "claude", "action": "type", "text": "hola\n"},
                          {"agent": "claude", "action": "hotkey", "keys": ["cmd", "enter"]},
                          {"agent": "claude", "action": "hotkey", "keys": ["enter"]}):
                with self.subTest(front=front, order=order):
                    self.open()
                    p = self.msg_pointer(front, [order])
                    self.assertEqual(self.run_msg(p, 1), [])
        self.assertTrue(ae.dangerous_keys(["cmd", "enter"]))

    def test_outlook_click_needs_readable_element(self):
        self.open()
        p = self.msg_pointer("Microsoft Outlook", [{"agent": "claude", "action": "click", "x": 400, "y": 300}], labels=[None])
        self.assertEqual(self.run_msg(p, 1), [])
        self.assertIn("autonomo:elemento_no_verificado", self.reasons())
        self.open()
        p = FakePointer("Slack", [{"agent": "claude", "action": "click", "x": 400, "y": 300}])  # sin observadores
        quiet(au.run, p, sleep=lambda s: None, max_steps=1)
        self.assertEqual(p.calls, [])

    def test_slack_click_aborts_if_window_or_app_changes(self):
        self.open()
        p = self.msg_pointer("Slack", [{"agent": "claude", "action": "click", "x": 400, "y": 300}],
                             titles=["#general", "Preferences"])
        self.assertEqual(self.run_msg(p, 1), [])
        self.open()
        p = self.msg_pointer("Slack", [{"agent": "claude", "action": "click", "x": 400, "y": 300}],
                             fronts=["Slack", "Slack", "Mail"])
        self.assertEqual(self.run_msg(p, 1), [])

    def test_settings_window_blocks_even_move(self):
        self.open()
        p = self.msg_pointer("Microsoft Outlook", [{"agent": "claude", "action": "move", "x": 400, "y": 300}],
                             titles=["Configuración"])
        self.assertEqual(self.run_msg(p, 1), [])
        self.assertIn("autonomo:ventana_de_ajustes", self.reasons())

    def test_mail_and_messages_stay_blocked(self):
        for front in ("Mail", "Messages", "Mensajes"):
            with self.subTest(front=front):
                self.open()
                p = self.msg_pointer(front, [{"agent": "claude", "action": "move", "x": 400, "y": 300}])
                self.assertEqual(self.run_msg(p, 1), [])

    def test_stop_still_halts_in_slack(self):
        self.open()
        (ae.control_dir() / "STOP").touch()
        p = self.msg_pointer("Slack", [{"agent": "claude", "action": "move", "x": 400, "y": 300}])
        self.assertEqual(self.run_msg(p, 1), [])

    def test_click_aborts_when_safari_changes_page(self):
        self.open()

        class Pages(FakePointer):
            def __init__(self):
                super().__init__("Safari", [
                    {"agent": "claude", "action": "open_url", "url": "https://github.com/ejemplo/repo"},
                    {"agent": "claude", "action": "click", "x": 400, "y": 300},
                ])
                self.urls = [
                    "https://github.com/ejemplo/repo",
                    "https://github.com/ejemplo/repo",
                    "https://mail.google.com/mail/u/0",
                ]

            def page_url(self):
                return self.urls.pop(0) if self.urls else "https://mail.google.com/mail/u/0"

        p = Pages()
        quiet(au.run, p, sleep=lambda s: None, max_steps=2)
        self.assertNotIn("click", [c[0] for c in p.calls])
        rows = [json.loads(l) for l in (ae.control_dir() / "audit.jsonl").read_text().splitlines()]
        self.assertTrue(any(r["reason"] == "autonomo:sitio_no_verificado" for r in rows))

    def test_failsafe_exception_creates_stop(self):
        self.open()

        class Boom(FakePointer):
            def click(self, x, y):
                raise RuntimeError("FailSafeException")
        p = Boom("Notes", [{"agent": "claude", "action": "click", "x": 100, "y": 100}])
        quiet(au.run, p, sleep=lambda s: None, max_steps=1)
        self.assertTrue(ae.stopped())

    def test_audit_has_no_text(self):
        self.open()
        self.go([{"agent": "claude", "action": "type", "text": "texto-ficticio-123"}])
        log = (ae.control_dir() / "audit.jsonl").read_text()
        self.assertNotIn("texto-ficticio-123", log)

    def test_expired_session_halts(self):
        self.open()
        data = json.loads(au.session_path().read_text())
        data["expires"] = "2000-01-01T00:00:00+00:00"
        au.session_path().write_text(json.dumps(data))
        p = self.go([{"agent": "claude", "action": "click", "x": 100, "y": 100}])
        self.assertEqual(p.calls, [])


class PyautoguiMockTests(Base):
    def test_autopointer_uses_pyautogui(self):
        import sys
        import types
        fake = types.SimpleNamespace(FAILSAFE=False, PAUSE=1, calls=[])
        for n in ("moveTo", "click", "doubleClick", "scroll", "write", "screenshot"):
            setattr(fake, n, (lambda n: lambda *a, **k: fake.calls.append(n))(n))
        fake.easeOutQuad = None
        fake.size = lambda: (1440, 900)
        fake.position = lambda: (1, 2)
        with patch.dict(sys.modules, {"pyautogui": fake}):
            p = au.AutoPointer()
            self.assertTrue(fake.FAILSAFE)
            p.move(1, 2); p.click(3, 4); p.double_click(5, 6); p.scroll(-1)
            self.assertEqual(p.size(), (1440, 900))
        self.assertEqual(fake.calls, ["moveTo", "click", "doubleClick", "scroll"])


if __name__ == "__main__":
    unittest.main()
