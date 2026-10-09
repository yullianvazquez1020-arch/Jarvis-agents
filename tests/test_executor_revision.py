import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

source = Path(__file__).resolve().parents[1] / 'desktop/mac/agent_executor.py'
spec = importlib.util.spec_from_file_location('executor', source)
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)

class Pointer:
    def __init__(self): self.calls=[]
    def scroll(self, dy): self.calls.append(('scroll',dy))

class Revision(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ, {'JARVIS_CONTROL_DIR': self.tmp.name})
        self.env.start(); e._MEMORY_GRANTS.clear()
    def tearDown(self): self.env.stop();self.tmp.cleanup()
    def action(self): return {'agent':'grok','action':'scroll','dy':-3}
    def test_embedded_financial_names(self):
        for host in ['1firstbank.com','bancopopular.com','orientalbank.com','mibanco.pr','venmo.com','zellepay.com','pagos']:
            with self.subTest(host=host): self.assertEqual(e.denial({'action':'open_url','url':host}),'denylist')
    def test_hotkeys_with_extra_modifier(self):
        for keys in [['cmd','shift','q'],['cmd','alt','q'],['cmd','alt','backspace']]:
            self.assertEqual(e.denial({'action':'hotkey','keys':keys}),'atajo')
    def test_forged_json_never_authorizes(self):
        a=self.action();(Path(self.tmp.name)/'usos.json').write_text(json.dumps({'grants':[{'key':e.action_key(a),'used':False}]}))
        self.assertIsNone(e.consume_grant(a))
    def test_expiry_and_one_use(self):
        a=self.action()
        with patch.object(e.time,'monotonic',return_value=100): self.assertTrue(e.grant_once(a))
        with patch.object(e.time,'monotonic',return_value=161): self.assertIsNone(e.consume_grant(a))
        self.assertTrue(e.grant_once(a));self.assertIsNotNone(e.consume_grant(a));self.assertIsNone(e.consume_grant(a))
    def test_real_path_wrong_turn_no_pointer(self):
        a=self.action();e.write_lock('claude',1);self.assertTrue(e.grant_once(a))
        path=Path(self.tmp.name)/'actions.jsonl';path.write_text(json.dumps(a)+'\n')
        pointer=Pointer()
        self.assertEqual(e.run_actions(path,dry=False,libre=False,pointer=pointer),2)
        self.assertEqual(pointer.calls,[])
    def test_valid_once(self):
        a=self.action();e.write_lock('grok',1);e.grant_once(a)
        pointer=Pointer();self.assertEqual(e.finish(a,e.consume_grant(a),pointer),'HECHO')
        self.assertEqual(e.finish(a,e.consume_grant(a),pointer),'CANCELADO');self.assertEqual(pointer.calls,[('scroll',-3)])
    def test_rate_persists_after_module_reload(self):
        for _ in range(20): self.assertTrue(e.claim_rate())
        other=importlib.util.module_from_spec(spec);spec.loader.exec_module(other)
        self.assertFalse(other.claim_rate())
    def test_corrupt_rate_fails_closed(self):
        (Path(self.tmp.name)/'rate.json').write_text('bad');self.assertFalse(e.claim_rate())
    def test_fixed_batch_one_confirmation_four_actions(self):
        class BatchPointer(Pointer):
            def move(self,x,y): self.calls.append(('move',x,y))
            def shot(self,path): self.calls.append(('shot',))
            def wait(self,seconds): self.calls.append(('wait',seconds))
        pointer=BatchPointer()
        with patch.object(e.sys.stdin,'isatty',return_value=True), patch.object(e,'wait_confirm',return_value='tecla') as confirm:
            self.assertEqual(e.run_confirmed_batch(pointer),0)
        self.assertEqual(confirm.call_count,1)
        self.assertEqual(pointer.calls,[('move',720,450),('shot',),('scroll',-3),('wait',1)])
        self.assertIsNone(e.read_lock())
    def test_plain_string_cannot_approve(self):
        a=self.action();e.write_lock('grok',1);pointer=Pointer()
        self.assertEqual(e.finish(a,'codigo',pointer),'BLOQUEADO');self.assertEqual(pointer.calls,[])
    def test_gesture_cannot_approve(self):
        a=self.action();e.write_lock('grok',1);pointer=Pointer()
        self.assertEqual(e.finish(a,'gesto',pointer),'BLOQUEADO');self.assertEqual(pointer.calls,[])

if __name__=='__main__': unittest.main()
