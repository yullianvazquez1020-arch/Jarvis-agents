"""Ejecutor del mouse de la Mac (desktop/mac/agent_executor.py). Puntero falso: aquí nunca se mueve el mouse.
Banco bloqueado aunque se confirme, permiso de un uso que vence, sin turno no hay movimiento."""
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
spec = importlib.util.spec_from_file_location("agent_executor", ROOT / "agent_executor.py")
ae = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ae)

ORDENES = [
    {"agent": "jarvis", "action": "move", "x": 720, "y": 450},
    {"agent": "chatgpt", "action": "screenshot"},
    {"agent": "grok", "action": "scroll", "dy": -3},
    {"agent": "claude", "action": "wait", "seconds": 1},
]


class Pointer:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name,) + args)


def quiet(fn, *a, **kw):
    with contextlib.redirect_stdout(io.StringIO()) as out:
        rc = fn(*a, **kw)
    return rc, out.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self.ctl = tempfile.TemporaryDirectory(); self.own = tempfile.TemporaryDirectory()
        self.addCleanup(self.ctl.cleanup); self.addCleanup(self.own.cleanup)
        env = patch.dict(os.environ, {"JARVIS_CONTROL_DIR": self.ctl.name, "JARVIS_OWNER_DIR": self.own.name})
        env.start(); self.addCleanup(env.stop)
        self.dir = Path(self.ctl.name)

    def file(self, rows, name="o.jsonl"):
        path = self.dir / name
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        return path

    def turn(self, agent):
        quiet(ae.release_lock, "yullian")
        self.assertEqual(quiet(ae.take_lock, agent, 5)[0], 0)
        (self.dir / "session.json").unlink(missing_ok=True)



class Executor(Base):
    def test_builtin_self_test_passes(self):
        self.assertEqual(quiet(ae.self_test)[0], 0)

    def test_confirmed_file_is_exactly_the_four_orders(self):
        rows = [json.loads(x) for x in (ROOT / "ordenes_confirmadas.jsonl").read_text().splitlines() if x.strip()]
        self.assertEqual(rows, ORDENES)

    def test_dry_run_without_turn_says_rechazado_turno_and_never_touches_pointer(self):
        p = Pointer()
        rc, out = quiet(ae.run_actions, ROOT / "ordenes_confirmadas.jsonl", dry=True, libre=False, pointer=p)
        self.assertEqual(rc, 2)
        self.assertEqual(out.count("RECHAZADO turno"), 4)
        self.assertEqual(p.calls, [])

    def test_owner_grants_once_then_pointer_runs_the_four_alone(self):
        orders = self.file(ORDENES)
        shown = {}
        rc, _ = quiet(ae.otorgar, orders, tty=True,
                      ask=lambda prompt: shown.setdefault("c", prompt.rstrip(": ").split()[-1]))
        self.assertEqual(rc, 0)
        p = Pointer()
        for row in ORDENES:
            self.turn(row["agent"])
            self.assertEqual(quiet(ae.run_actions, self.file([row], "una.jsonl"), dry=False, libre=False, pointer=p)[0], 0)
        self.assertEqual([c[0] for c in p.calls], ["move", "shot", "scroll", "wait"])
        self.assertEqual(p.calls[0], ("move", 720, 450))
        self.turn("grok")                                   # el permiso murió: la segunda vez espera
        self.assertEqual(quiet(ae.run_actions, self.file([ORDENES[2]], "una.jsonl"), dry=False, libre=False, pointer=p)[0], 3)
        self.assertEqual(len(p.calls), 4)

    def test_bank_stays_blocked_even_with_turn_and_owner_code(self):
        for url in ("https://www.1firstbank.com/pr/es", "https://www.bancopopular.com", "https://www.coinbase.com",
                    "https://www.paypal.com/checkout"):
            row = {"agent": "claude", "action": "open_url", "url": url}
            rc, out = quiet(ae.otorgar, self.file([row]), tty=True, ask=lambda pr: pr.rstrip(": ").split()[-1])
            self.assertEqual(rc, 3); self.assertIn("BLOQUEADO", out)
            self.assertFalse(ae.grant_once(row))
            self.turn("claude")
            p = Pointer()
            self.assertEqual(quiet(ae.run_actions, self.file([row]), dry=False, libre=False, pointer=p)[0], 3)
            self.assertEqual(p.calls, [])

    def test_no_turn_no_movement_even_with_valid_grant(self):
        self.assertTrue(ae.grant_once(ORDENES[0]))
        self.turn("claude")                                 # el turno es de otro agente
        p = Pointer()
        rc, out = quiet(ae.run_actions, self.file([ORDENES[0]]), dry=False, libre=False, pointer=p)
        self.assertEqual(rc, 2); self.assertIn("RECHAZADO turno", out)
        self.assertEqual(p.calls, [])

    def test_hand_written_or_reused_grant_does_not_move(self):
        self.turn("grok")
        ae._save_grants([{"key": ae.action_key(ORDENES[2]), "used": False}])
        p = Pointer()
        self.assertEqual(quiet(ae.run_actions, self.file([ORDENES[2]]), dry=False, libre=False, pointer=p)[0], 3)
        self.assertTrue(ae.grant_once(ORDENES[2]))
        saved = ae._grants()
        self.assertEqual(ae.consume_grant(ORDENES[2]), "codigo")
        ae._save_grants(saved)
        self.assertIsNone(ae.consume_grant(ORDENES[2]))
        self.assertEqual(p.calls, [])

    def test_otorgar_needs_terminal_and_code(self):
        orders = self.file(ORDENES)
        self.assertEqual(quiet(ae.otorgar, orders, tty=False)[0], 2)
        self.assertEqual(quiet(ae.otorgar, orders, tty=True, ask=lambda _p: "nope")[0], 3)
        self.assertEqual(ae._grants(), [])

    def test_real_mode_without_mouse_library_does_nothing(self):
        with patch.dict("sys.modules", {"pyautogui": None}):
            rc, out = quiet(ae.main, ["--file", str(ROOT / "ordenes_confirmadas.jsonl")])
        self.assertEqual(rc, 2); self.assertIn("Usa --dry-run", out)

    def test_audit_keeps_length_and_hash_only(self):
        self.turn("claude")
        quiet(ae.run_actions, self.file([{"agent": "claude", "action": "type", "text": "nota secreta"}]),
              dry=True, libre=False)
        audit = (self.dir / "audit.jsonl").read_text(encoding="utf-8")
        self.assertNotIn("nota secreta", audit); self.assertIn('"text_len": 12', audit)


class ReviewFixes(Base):
    """Revisión del 10 oct: lo que apruebas se ve completo, los archivos de los agentes no confirman,
    un permiso no se gasta dos veces en paralelo y la sesión se revisa justo antes de mover."""

    def test_approval_shows_coordinates_text_and_url(self):
        rows = ORDENES + [{"agent": "claude", "action": "type", "text": "hola mundo"},
                          {"agent": "claude", "action": "open_url", "url": "https://github.com/"}]
        buf, seen = io.StringIO(), {}

        def owner(prompt):                                  # lo que había en pantalla ANTES de escribir el código
            seen["before"] = buf.getvalue()
            return prompt.rstrip(": ").split()[-1]

        with contextlib.redirect_stdout(buf):
            rc = ae.otorgar(self.file(rows), tty=True, ask=owner)
        self.assertEqual(rc, 0)
        out = seen["before"]
        for shown in ("jarvis move x=720 y=450", "grok scroll dy=-3", "claude wait 1 s", "chatgpt screenshot",
                      "«hola mundo» (10 caracteres)", "https://github.com/"):
            self.assertIn(shown, out)

    def test_agent_written_decision_cannot_confirm(self):
        self.turn("jarvis")
        pending = ae.begin_pending(ORDENES[0])
        self.assertNotIn(pending["code"], (self.dir / "pendiente.json").read_text(encoding="utf-8"))
        public = json.loads((self.dir / "pendiente.json").read_text(encoding="utf-8"))["pending"]
        (self.dir / "decision.json").write_text(json.dumps({"id": public["id"], "ok": True}), encoding="utf-8")
        r, w = os.pipe(); self.addCleanup(os.close, w)
        with open(r, "r") as fake_stdin, patch.object(ae.sys, "stdin", fake_stdin), \
             patch.object(ae, "CONFIRM_SECONDS", 2):
            how = quiet(ae.wait_confirm, pending)[0]
        self.assertEqual(how, "cancelar")
        p = Pointer()
        self.assertEqual(ae.finish(ORDENES[0], how, p), "CANCELADO")
        self.assertEqual(ae.finish(ORDENES[0], "gesto", p), "BLOQUEADO")
        self.assertIsNone(ae.answer_of(pending, "s"))
        self.assertEqual(p.calls, [])

    def test_parallel_consumers_spend_a_grant_once(self):
        import subprocess, sys, time
        self.assertTrue(ae.grant_once(ORDENES[2]))
        go = self.dir / "go"
        code = ("import importlib.util,json,os,sys,time;"
                f"spec=importlib.util.spec_from_file_location('ae',{str(ROOT / 'agent_executor.py')!r});"
                "ae=importlib.util.module_from_spec(spec);spec.loader.exec_module(ae);"
                f"go={str(go)!r}\n"
                "while not os.path.exists(go): time.sleep(0.001)\n"
                f"print(ae.consume_grant({ORDENES[2]!r}))")
        procs = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True,
                                  env=dict(os.environ)) for _ in range(8)]
        time.sleep(0.5); go.write_text("1")
        results = [p.communicate(timeout=60)[0].strip() for p in procs]
        self.assertEqual(results.count("codigo"), 1, results)
        self.assertEqual(results.count("None"), 7, results)

    def test_second_executor_is_refused_while_one_runs(self):
        self.turn("grok")
        self.assertTrue(ae.grant_once(ORDENES[2]))
        p = Pointer()
        with ae._owner_flock("ejecutor.lock"):
            rc, out = quiet(ae.run_actions, self.file([ORDENES[2]]), dry=False, libre=False, pointer=p)
        self.assertEqual(rc, 2); self.assertIn("OCUPADO", out)
        self.assertEqual(p.calls, [])
        self.assertEqual(ae.consume_grant(ORDENES[2]), "codigo")          # el permiso sigue entero

    def test_session_expiring_after_judge_blocks_the_move(self):
        self.turn("grok")
        self.assertTrue(ae.grant_once(ORDENES[2]))
        p = Pointer()
        with patch.object(ae, "session_open", side_effect=[True, False]):
            rc, out = quiet(ae.run_actions, self.file([ORDENES[2]]), dry=False, libre=False, pointer=p)
        self.assertEqual(rc, 3); self.assertIn("BLOQUEADO", out)
        self.assertEqual(p.calls, [])

    def test_stop_or_lost_turn_after_judge_blocks_the_move(self):
        self.turn("grok")
        p = Pointer()
        (self.dir / "STOP").write_text("1")
        self.assertEqual(ae.finish(ORDENES[2], "codigo", p), "BLOQUEADO")
        (self.dir / "STOP").unlink()
        self.turn("claude")
        self.assertEqual(ae.finish(ORDENES[2], "codigo", p), "RECHAZADO")
        self.assertEqual(p.calls, [])

    def test_hotkey_keeps_press_order(self):
        self.turn("claude")
        p = Pointer()
        ae.perform({"agent": "claude", "action": "hotkey", "keys": ["cmd", "c"]}, p)
        self.assertEqual(p.calls, [("hotkey", ["command", "c"])])


class FinalIntegration(Base):
    def test_complete_text_and_exact_hotkey_authorization(self):
        text = "a" * 250 + " final visible"
        action = {"agent": "claude", "action": "type", "text": text}
        self.assertIn(text, ae.describe(action))
        self.assertTrue(ae.grant_once(action))
        self.assertIsNone(ae.consume_grant(dict(action, text=text+" cambiado")))
        first = {"agent": "claude", "action": "hotkey", "keys": ["cmd", "c"]}
        reverse = dict(first, keys=["c", "cmd"])
        self.assertNotEqual(ae.action_key(first), ae.action_key(reverse))
        self.assertIn("command+c", ae.describe(first))
        self.assertTrue(ae.grant_once(first))
        self.assertIsNone(ae.consume_grant(reverse))
        self.assertEqual(ae.consume_grant(dict(first, keys=["command", "c"])), "codigo")

    def test_automatic_runs_approved_batch_once_without_prompt(self):
        for row in ORDENES: self.assertTrue(ae.grant_once(row))
        pointer = Pointer()
        with patch.object(ae.sys.stdin, "isatty", return_value=True), patch.object(ae, "wait_confirm", side_effect=AssertionError("prompt")):
            self.assertEqual(quiet(ae.run_actions, self.file(ORDENES), dry=False, libre=False, pointer=pointer, automatic=True)[0], 0)
            self.assertIsNone(ae.read_lock())
            self.assertEqual([c[0] for c in pointer.calls], ["move", "shot", "scroll", "wait"])
            self.assertEqual(quiet(ae.run_actions, self.file(ORDENES), dry=False, libre=False, pointer=pointer, automatic=True)[0], 3)
        self.assertEqual(len(pointer.calls), 4)

    def test_automatic_stop_expired_session_and_existing_turn(self):
        row = ORDENES[0]; self.assertTrue(ae.grant_once(row)); pointer = Pointer()
        path = self.file([row])
        (self.dir / "STOP").touch()
        self.assertEqual(quiet(ae.run_actions, path, dry=False, libre=False, pointer=pointer, automatic=True)[0], 3)
        (self.dir / "STOP").unlink()
        self.turn("grok")
        self.assertEqual(quiet(ae.run_actions, path, dry=False, libre=False, pointer=pointer, automatic=True)[0], 2)
        self.assertEqual(ae.read_lock()["agent"], "grok")
        quiet(ae.release_lock, "grok")
        (self.dir / "session.json").write_text(json.dumps({"started": ae.stamp(ae.now()-ae.timedelta(seconds=ae.SESSION_SECONDS+1))}))
        self.assertEqual(quiet(ae.run_actions, path, dry=False, libre=False, pointer=pointer, automatic=True)[0], 3)
        self.assertEqual(pointer.calls, [])

    def test_native_failure_stops_remaining_batch(self):
        for row in ORDENES: ae.grant_once(row)
        pointer = Pointer()
        pointer.move = lambda *args: (_ for _ in ()).throw(RuntimeError("native"))
        self.assertEqual(quiet(ae.run_actions, self.file(ORDENES), dry=False, libre=False, pointer=pointer, automatic=True)[0], 3)
        self.assertTrue(ae.stopped()); self.assertIsNone(ae.read_lock())
        self.assertEqual(pointer.calls, [])

    def test_native_mouse_moves_with_warp(self):
        from types import SimpleNamespace
        from test_mouse_warp import quartz
        q, st = quartz(front_x=200)
        fake = SimpleNamespace(size=lambda: (1920, 1080))
        with patch.dict("sys.modules", {"pyautogui": fake, "Quartz": q}):
            pointer = ae.MacPointer(); pointer.move(720, 450)
        self.assertEqual(fake.PAUSE, 0); self.assertTrue(fake.FAILSAFE)
        self.assertEqual(st["pos"], (720.0, 450.0))


class SessionRecovery(Base):
    def test_status_does_not_create_session(self):
        self.assertEqual(ae.session_status(), "sin sesión")
        self.assertFalse((self.dir / "session.json").exists())

    def test_renewal_requires_terminal_and_correct_code(self):
        self.assertEqual(quiet(ae.start_session, tty=False)[0], 2)
        self.assertEqual(quiet(ae.start_session, tty=True, ask=lambda _: "wrong")[0], 3)
        self.assertFalse((self.dir / "session.json").exists())

    def test_explicit_renewal_does_not_grant_actions(self):
        (self.dir / "session.json").write_text('{"started":"2020-01-01T00:00:00+00:00"}')
        self.assertEqual(ae.session_status(), "sesión vencida")
        self.assertEqual(quiet(ae.start_session, tty=True, ask=lambda p: p.rstrip(": ").split()[-1])[0], 0)
        self.assertIn("sesión activa", ae.session_status())
        pointer = Pointer()
        rc, out = quiet(ae.run_actions, self.file([ORDENES[0]]), dry=False, libre=False, pointer=pointer, automatic=True)
        self.assertEqual(rc, 3)
        self.assertIn("ESPERA", out)
        self.assertEqual(pointer.calls, [])

    def test_stop_and_existing_turn_prevent_renewal(self):
        approve = lambda p: p.rstrip(": ").split()[-1]
        (self.dir / "STOP").touch()
        self.assertEqual(quiet(ae.start_session, tty=True, ask=approve)[0], 3)
        self.assertFalse((self.dir / "session.json").exists())
        (self.dir / "STOP").unlink()
        quiet(ae.take_lock, "jarvis", 5)
        self.assertEqual(quiet(ae.start_session, tty=True, ask=approve)[0], 3)
        self.assertFalse((self.dir / "session.json").exists())

    def test_expired_automatic_attempt_explains_and_audits_without_using_grant(self):
        (self.dir / "session.json").write_text('{"started":"2020-01-01T00:00:00+00:00"}')
        self.assertTrue(ae.grant_once(ORDENES[0]))
        pointer = Pointer()
        rc, out = quiet(ae.run_actions, self.file([ORDENES[0]]), dry=False, libre=False, pointer=pointer, automatic=True)
        self.assertEqual(rc, 3)
        self.assertIn("--start-session", out)
        record = json.loads((self.dir / "audit.jsonl").read_text().splitlines()[-1])
        self.assertEqual(record["verdict"], "BLOQUEADO")
        self.assertIn("sesión", record["reason"])
        self.assertEqual(pointer.calls, [])
        self.assertEqual(ae.consume_grant(ORDENES[0]), "codigo")
