"""Physical movement policy checked with a fake pointer; never moves the test host."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
from hand_mouse import HandMouse


class Pointer:
    def __init__(self):
        self.moves = []
        self.pos = (1900, 500)
        self.esc = False

    def size(self): return (3840, 1080)
    def position(self): return self.pos
    def escape(self): return self.esc
    def move(self, x, y): self.moves.append((x, y)); self.pos = (x, y)


class MovementPolicy(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.pointer = Pointer()
        self.control = HandMouse(True, lambda: self.pointer, lambda: self.now, lambda: self.now, False)
        self.lease = self.control.arm("owner", {"confirm":"SOLO_MOVER_60S"})["lease"]

    def frame(self, **overrides):
        data = dict(lease=self.lease, seq=1, x=1, y=1, captured_ms=self.now*1000)
        data.update(overrides)
        return data

    def test_default_is_disabled_and_does_not_initialize_pointer(self):
        control = HandMouse(pointer_factory=lambda: self.fail("native access"))
        with self.assertRaises(RuntimeError): control.arm("owner", {"confirm":"SOLO_MOVER_60S"})

    def test_only_latest_target_and_bounded_step(self):
        self.control.frame("owner", self.frame())
        self.control.frame("owner", self.frame(seq=2, x=0, y=0))
        self.control.tick()
        self.assertEqual(len(self.pointer.moves), 1)
        self.assertLess(self.pointer.pos[0], 1900)
        self.assertLessEqual(math.dist((1900,500),self.pointer.pos),61)

    def test_no_motion_without_frame_or_after_freshness_window(self):
        self.control.tick(); self.assertEqual(self.pointer.moves, [])
        self.control.frame("owner", self.frame())
        self.now += .41
        self.control.tick(); self.assertEqual(self.pointer.moves, [])

    def test_expiration_does_not_renew_by_frames(self):
        self.now += 59.9
        self.control.frame("owner", self.frame())
        self.now += .11
        self.control.tick(); self.assertEqual(self.pointer.moves, [])
        self.assertFalse(self.control.status()["active"])

    def test_escape_cancels_lease_and_cannot_resume(self):
        self.control.frame("owner", self.frame())
        self.pointer.esc = True
        self.control.tick(); self.pointer.esc = False
        with self.assertRaises(ValueError): self.control.frame("owner", self.frame(seq=2))
        self.assertEqual(self.pointer.moves, [])

    def test_border_or_other_monitor_stops(self):
        self.control.frame("owner", self.frame())
        self.pointer.pos = (-1, 500)
        self.control.tick()
        self.assertFalse(self.control.status()["active"])
        self.assertEqual(self.pointer.moves, [])

    def test_owner_and_lease_binding_and_order(self):
        for owner,data in [("other",self.frame()), ("owner",self.frame(lease="forged"))]:
            with self.assertRaises(ValueError): self.control.frame(owner, data)
        self.control.frame("owner", self.frame(seq=2))
        with self.assertRaises(ValueError): self.control.frame("owner", self.frame(seq=1))

    def test_invalid_and_stale_frames_rejected(self):
        for override in [dict(x=float('nan')),dict(y=float('inf')),dict(x=True),dict(x=2),
                         dict(captured_ms=(self.now-1)*1000),dict(captured_ms=(self.now+1)*1000),dict(seq=True)]:
            with self.subTest(override=override):
                with self.assertRaises(ValueError): self.control.frame("owner",self.frame(**override))
        self.control.tick(); self.assertEqual(self.pointer.moves, [])

    def test_no_click_key_or_command_payload(self):
        for key in ('click','action','key','command','scroll'):
            with self.assertRaises(ValueError): self.control.frame("owner",self.frame(**{key:'anything'}))
        self.control.tick(); self.assertEqual(self.pointer.moves, [])

    def test_stop_and_shutdown_invalidate_queued_motion(self):
        self.control.frame("owner",self.frame())
        self.control.stop("owner",self.lease)
        self.control.tick(); self.assertEqual(self.pointer.moves, [])
        self.control.close()
        with self.assertRaises(RuntimeError): self.control.arm("owner",{"confirm":"SOLO_MOVER_60S"})

    def test_pointer_error_fails_closed(self):
        def broken(*args): raise RuntimeError("native failure")
        self.pointer.move = broken
        self.control.frame("owner",self.frame()); self.control.tick()
        self.assertFalse(self.control.status()["active"])


if __name__ == '__main__': unittest.main()
