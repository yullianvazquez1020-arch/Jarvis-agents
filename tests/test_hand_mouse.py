"""Physical movement policy checked with a fake pointer; never moves the test host."""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "desktop"))
from hand_mouse import HandMouse, MacPointer


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
        self.assertLessEqual(math.dist((1900,500),self.pointer.pos),91)

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




class PinchPolicy(unittest.TestCase):
    """Click policy uses a fake pointer: no input is sent to this machine."""
    def setUp(self):
        self.now = 1000.0
        self.pointer = Pointer()
        self.pointer.clicks = []
        self.pointer.click = lambda: self.pointer.clicks.append(self.pointer.pos)
        self.control = HandMouse(True, lambda: self.pointer, lambda: self.now, lambda: self.now, False)
        self.seq = 0
        self.arm()

    def arm(self, confirm="MOVER_Y_CLIC_60S"):
        self.lease = self.control.arm("owner", {"confirm": confirm})["lease"]

    def data(self, ratio=.1):
        self.seq += 1
        return dict(lease=self.lease, seq=self.seq, x=.6, y=.5,
                    captured_ms=self.now*1000, pinch_ratio=ratio)

    def sample(self, ratio, dt=.2, tick=True):
        self.now += dt
        self.control.frame("owner", self.data(ratio))
        if tick: self.control.tick()

    def pinch(self, tick=True):
        self.sample(.1)
        self.sample(.1)
        self.sample(.1, tick=tick)

    def test_explicit_click_mode_and_legacy_never_click(self):
        self.assertTrue(self.control.status()["click_enabled"])
        self.control.stop("owner", self.lease)
        self.arm("SOLO_MOVER_60S")
        self.assertFalse(self.control.status()["click_enabled"])
        for ratio in [.8,.1,.1,.1]:
            with self.assertRaises(ValueError): self.control.frame("owner", self.data(ratio))
        data=self.data(); del data["pinch_ratio"]
        self.control.frame("owner",data); self.control.tick()
        self.assertEqual(self.pointer.clicks, [])

    def test_starting_closed_does_not_click_and_requires_open(self):
        self.pinch(); self.pinch()
        self.assertEqual(self.pointer.clicks, [])
        self.sample(.8); self.pinch()
        self.assertEqual(len(self.pointer.clicks), 1)

    def test_hold_three_frames_one_click_and_no_repeat(self):
        self.sample(.8)
        self.sample(.1); self.sample(.1)
        self.assertEqual(self.pointer.clicks, [])
        self.sample(.1)
        self.assertEqual(len(self.pointer.clicks), 1)
        for _ in range(12): self.sample(.1)
        self.assertEqual(len(self.pointer.clicks), 1)

    def test_time_without_distinct_frames_cannot_click(self):
        self.sample(.8); self.sample(.1)
        self.now += .36; self.control.tick()
        self.assertEqual(self.pointer.clicks, [])

    def test_cooldown_and_reopen(self):
        self.sample(.8); self.pinch()
        self.sample(.8, dt=.01); self.pinch()
        self.assertEqual(len(self.pointer.clicks), 1)
        for _ in range(8): self.sample(.1)
        self.assertEqual(len(self.pointer.clicks), 1)  # cooldown cannot release a latent click
        self.sample(.8, dt=1.1); self.pinch()
        self.assertEqual(len(self.pointer.clicks), 2)

    def test_stale_tracking_requires_new_open(self):
        self.sample(.8); self.sample(.1)
        self.now += .41; self.control.tick()
        self.pinch()
        self.assertEqual(self.pointer.clicks, [])
        self.sample(.8); self.pinch()
        self.assertEqual(len(self.pointer.clicks), 1)

    def test_explicit_tracking_loss_cancels_pending_click(self):
        self.sample(.8); self.pinch(tick=False)
        self.sample(None)
        self.pinch()
        self.assertEqual(self.pointer.clicks, [])
        self.sample(.8); self.pinch()
        self.assertEqual(len(self.pointer.clicks), 1)

    def test_invalid_ratio_resets_and_cannot_arm_click(self):
        for ratio in [True, "0.1", -1, float('nan'), float('inf'), {}, []]:
            with self.subTest(ratio=ratio):
                self.sample(.8); self.pinch(tick=False)
                with self.assertRaises(ValueError): self.control.frame("owner", self.data(ratio))
                self.control.tick(); self.pinch()
                self.assertEqual(self.pointer.clicks, [])

    def test_wrong_owner_or_nonce_never_clicks(self):
        for owner,lease in [("other",self.lease),("owner","forged")]:
            for ratio in [.8,.1,.1,.1]:
                self.now += .2
                data=self.data(ratio);data['lease']=lease
                with self.assertRaises(ValueError): self.control.frame(owner,data)
                self.control.tick()
        self.assertEqual(self.pointer.clicks, [])

    def test_escape_edge_expiry_stop_block_pending_click(self):
        for stop in ('escape','edge','expiry','stop'):
            with self.subTest(stop=stop):
                if not self.control.status()['active']: self.arm()
                self.sample(.8); self.pinch(tick=False)
                if stop=='escape': self.pointer.esc=True
                elif stop=='edge': self.pointer.pos=(0,500)
                elif stop=='expiry': self.now += 60
                else: self.control.stop('owner',self.lease)
                self.control.tick()
                self.assertEqual(self.pointer.clicks, [])
                self.assertFalse(self.control.status()['active'])
                self.pointer.esc=False;self.pointer.pos=(1900,500)

    def test_pinch_freezes_motion(self):
        self.sample(.8)
        self.pointer.moves.clear()
        self.pinch()
        self.assertEqual(self.pointer.moves, [])
        self.assertEqual(len(self.pointer.clicks), 1)

if __name__ == '__main__': unittest.main()


class NativeMovementPacing(unittest.TestCase):
    def test_only_move_skips_library_pause(self):
        from unittest.mock import Mock
        pointer = MacPointer.__new__(MacPointer)
        pointer.gui = Mock()
        pointer.move(400, 300)
        pointer.gui.moveTo.assert_called_once_with(400, 300, duration=0, _pause=False)
        pointer.click()
        pointer.gui.click.assert_called_once_with(button="left", clicks=1)


class AdaptiveMovement(unittest.TestCase):
    def test_precision_tremor_and_long_reach(self):
        for offset in (1, 20, 300, 1600):
            p = Pointer()
            c = HandMouse(True, lambda:p, lambda:1000, lambda:1000, False)
            lease = c.arm("owner", {"confirm":"SOLO_MOVER_60S"})["lease"]
            start=p.pos
            c.frame("owner",dict(lease=lease,seq=1,x=(start[0]+offset-12)/(3840-25),
                                 y=(start[1]-12)/(1080-25),captured_ms=1000000))
            c.tick()
            moved=p.pos[0]-start[0]
            if offset==1: self.assertEqual(moved,0)
            elif offset==20: self.assertTrue(1<=moved<=5)
            else: self.assertTrue(60<moved<=90)
            self.assertLessEqual(moved,offset)
