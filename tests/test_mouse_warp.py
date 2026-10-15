"""MacPointer con un Quartz falso: warp a coordenadas globales de la pantalla de la ventana al frente."""
import sys
import types
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

from test_agent_executor import Base, ae


def quartz(front_x=-1500, cursor_follows=True):
    q = types.ModuleType("Quartz"); st = {"pos": (100.0, 100.0), "posts": []}
    q.kCGWindowListOptionOnScreenOnly, q.kCGWindowListExcludeDesktopElements = 1, 16
    for n in ("kCGNullWindowID",
              "kCGEventMouseMoved", "kCGMouseButtonLeft", "kCGHIDEventTap", "kCGEventLeftMouseDown",
              "kCGEventLeftMouseUp", "kCGMouseEventClickState"):
        setattr(q, n, n)
    q.CGWindowListCopyWindowInfo = lambda *a: [{"kCGWindowLayer": 0, "kCGWindowOwnerName": "Notes",
                                                "kCGWindowBounds": {"X": front_x, "Y": 100, "Width": 800, "Height": 600}}]
    q.CGGetActiveDisplayList = lambda *a: (0, [1, 2], 2)
    q.CGDisplayBounds = lambda d: NS(origin=NS(x=0, y=0), size=NS(width=1920, height=1080)) if d == 1 else \
        NS(origin=NS(x=-1920, y=0), size=NS(width=1920, height=1080))
    def warp(p):
        if cursor_follows: st["pos"] = p
    q.CGWarpMouseCursorPosition = warp
    q.CGAssociateMouseAndMouseCursorPosition = lambda v: None
    q.CGEventCreateMouseEvent = lambda _s, kind, p, b: [kind, p]
    q.CGEventSetIntegerValueField = lambda ev, f, v: ev.append(v)
    q.CGEventPost = lambda tap, ev: st["posts"].append(ev)
    q.CGEventCreate = lambda s: None
    q.CGEventGetLocation = lambda e: NS(x=st["pos"][0], y=st["pos"][1])
    return q, st


class Warp(Base):
    def pointer(self, **kw):
        q, st = quartz(**kw)
        p = patch.dict(sys.modules, {"Quartz": q}); p.start(); self.addCleanup(p.stop)
        mp = ae.MacPointer.__new__(ae.MacPointer); mp.pg = NS(size=lambda: (1920, 1080)); return mp, st

    def test_stop_prevents_all_motion(self):
        mp, st = self.pointer()
        (self.dir / "STOP").touch()
        with self.assertRaises(RuntimeError): mp.move(600, 400)
        self.assertEqual(st["posts"], [])

    def test_stop_interrupts_smooth_motion(self):
        mp, st = self.pointer()
        def interrupt(_seconds): (self.dir / "STOP").touch()
        with patch.object(ae.time, "sleep", side_effect=interrupt):
            with self.assertRaises(RuntimeError): mp.move(600, 400)
        self.assertEqual(len(st["posts"]), 1)
        self.assertNotEqual(st["pos"], (-1320.0, 400.0))

    def test_emergency_corner_on_secondary_monitor(self):
        mp, st = self.pointer(); st["pos"] = (-1920, 0)
        with self.assertRaises(RuntimeError): mp.move(600, 400)
        self.assertEqual(st["posts"], [])

    def test_window_switch_aborts_before_click(self):
        mp, st = self.pointer(front_x=200)
        with patch.object(mp, "frontmost", side_effect=["Notes", "Notes", "Mail"]):
            with self.assertRaises(RuntimeError): mp.click(600, 400)
        self.assertNotIn("kCGEventLeftMouseDown", [e[0] for e in st["posts"]])

    def test_pantalla_izquierda(self):
        mp, st = self.pointer()
        with patch.object(ae.sys, "platform", "darwin"):
            self.assertEqual(mp.frontmost(), "Notes")
        mp.move(600, 400)
        self.assertEqual(st["pos"], (-1320.0, 400.0))
        self.assertTrue(ae.json.loads((self.dir / "ultimo_move.json").read_text())["ok"])

    def test_pantalla_principal_y_clic(self):
        mp, st = self.pointer(front_x=200)
        mp.click(600, 400)
        self.assertEqual(st["pos"], (600.0, 400.0))
        kinds = [e[0] for e in st["posts"]]
        self.assertEqual(kinds, ["kCGEventMouseMoved"] * 12 + ["kCGEventLeftMouseDown", "kCGEventLeftMouseUp"])

    def test_no_llega_no_clica(self):
        mp, st = self.pointer(cursor_follows=False)
        mp.move(600, 400)
        self.assertFalse(ae.json.loads((self.dir / "ultimo_move.json").read_text())["ok"])
        with self.assertRaises(RuntimeError):
            mp.click(600, 400)
        self.assertNotIn("kCGEventLeftMouseDown", [e[0] for e in st["posts"]])


if __name__ == "__main__":
    unittest.main()
