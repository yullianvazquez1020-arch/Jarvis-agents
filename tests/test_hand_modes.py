"""Mode isolation and button release, with a fake pointer only."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop'))
from hand_mouse import HandMouse

class Pointer:
    def __init__(self): self.pos=(500,500); self.esc=False; self.events=[]
    def size(self): return (3840,1080)
    def position(self): return self.pos
    def escape(self): return self.esc
    def move(self,x,y): self.pos=(x,y); self.events.append('move')
    def down(self): self.events.append('down')
    def up(self): self.events.append('up')
    def click(self): raise AssertionError('unexpected click')
    def scroll(self,n): self.events.append(n)

class Modes(unittest.TestCase):
    def setUp(self):
        self.now=1000.;self.p=Pointer()
        self.c=HandMouse(True,lambda:self.p,lambda:self.now,lambda:self.now,False)
        self.seq=0
    def arm(self,mode): self.lease=self.c.arm('owner',{'confirm':mode})['lease']
    def frame(self,**extra):
        self.seq+=1
        data=dict(lease=self.lease,seq=self.seq,x=.5,y=.5,captured_ms=self.now*1000)
        data.update(extra);self.c.frame('owner',data);self.c.tick()
    def drag(self):
        self.arm('ARRASTRAR_60S');self.frame(pinch_ratio=.9)
        for _ in range(4): self.now+=.13;self.frame(pinch_ratio=.2)
        self.assertEqual(self.p.events.count('down'),1)
    def test_drag_moves_and_release_never_clicks(self):
        self.drag();self.now+=.1;self.frame(pinch_ratio=.2,x=.8)
        self.assertEqual(self.p.events[-1],'move')
        self.now+=.1;self.frame(pinch_ratio=.8)
        self.assertIn('up',self.p.events);self.assertFalse(self.c.dragging)
    def test_release_on_all_stop_paths(self):
        for reason in ['escape','edge','expired','missing','stale','stop','close','invalid','gap']:
            with self.subTest(reason=reason):
                self.setUp();self.drag()
                if reason=='escape': self.p.esc=True;self.c.tick()
                elif reason=='edge': self.p.pos=(0,0);self.c.tick()
                elif reason=='expired': self.now+=61;self.c.tick()
                elif reason=='missing': self.now+=.1;self.frame(pinch_ratio=None)
                elif reason=='stale': self.now+=.41;self.c.tick()
                elif reason=='stop': self.c.stop('owner',self.lease)
                elif reason=='close': self.c.close()
                elif reason=='gap': self.now+=.5;self.frame(pinch_ratio=.2)
                else:
                    with self.assertRaises(ValueError): self.frame(pinch_ratio=.2,x=3)
                self.assertEqual(self.p.events.count('up'),1)
                self.assertFalse(self.c.dragging)
    def test_scroll_requires_two_fingers_and_no_backlog(self):
        self.arm('DESPLAZAR_60S');self.frame(two_fingers=False)
        self.now+=.1;self.frame(two_fingers=True,y=.4)
        self.now+=.13;self.frame(two_fingers=True,y=.5)
        self.assertEqual(self.p.events,[-1])
        for _ in range(10): self.c.tick()
        self.assertEqual(self.p.events,[-1])
        self.now+=.13;self.frame(two_fingers=False,y=.2)
        self.assertEqual(self.p.events,[-1])
    def test_scroll_anchor_recovers_after_stationary_hand(self):
        self.arm('DESPLAZAR_60S');self.frame(two_fingers=True)
        self.now+=.6;self.frame(two_fingers=True)
        self.now+=.13;self.frame(two_fingers=True,y=.6)
        self.assertEqual(self.p.events,[-1])
    def test_slow_continuous_motion_accumulates(self):
        self.arm('DESPLAZAR_60S');self.frame(two_fingers=True,y=.3)
        for i in range(1,31):
            self.now+=.1;self.frame(two_fingers=True,y=.3+i*.002)
        self.assertGreaterEqual(len(self.p.events),3)
        self.assertTrue(all(n==-1 for n in self.p.events))
    def test_rate_limit_retains_step_then_loss_discards_it(self):
        self.arm('DESPLAZAR_60S');self.frame(two_fingers=True,y=.3)
        self.now+=.1;self.frame(two_fingers=True,y=.32)
        self.now+=.05;self.frame(two_fingers=True,y=.34)
        self.assertEqual(self.p.events,[-1])
        self.now+=.08;self.c.tick();self.assertEqual(self.p.events,[-1,-1])
        self.now+=.02;self.frame(two_fingers=False)
        self.now+=.2;self.c.tick();self.assertEqual(self.p.events,[-1,-1])
    def test_modes_reject_other_actions(self):
        self.arm('DESPLAZAR_60S')
        with self.assertRaises(ValueError): self.frame(two_fingers=True,pinch_ratio=.1)
        self.assertEqual(self.p.events,[])
    def test_failed_release_cancels_and_retries_release_only(self):
        self.drag();original=self.p.up
        def fail(): raise RuntimeError('device')
        self.p.up=fail;self.c.stop('owner',self.lease)
        self.assertFalse(self.c.lease)
        self.p.up=original;self.c.tick()
        self.assertFalse(self.c.dragging)
        self.assertEqual(self.p.events[-1],'up')

class NativeDrag(unittest.TestCase):
    def test_drag_uses_drag_event_and_release_bypasses_corner_check(self):
        from hand_mouse import MacPointer
        from unittest.mock import Mock
        p=MacPointer.__new__(MacPointer);p.gui=Mock();p.quartz=Mock()
        p.down();p.move(600,400)
        p.gui.failSafeCheck.assert_called_once()
        p.quartz.CGEventCreateMouseEvent.assert_called_with(None,p.quartz.kCGEventLeftMouseDragged,(600,400),p.quartz.kCGMouseButtonLeft)
        p.gui.failSafeCheck.side_effect=RuntimeError('corner')
        p.up()
        self.assertFalse(p.button_held)
        self.assertEqual(p.quartz.CGEventPost.call_count,2)
