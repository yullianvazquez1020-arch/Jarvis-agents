"""Resident STT lifecycle/protocol and guarded qualification; no real models or cloud."""
import math
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock, patch
from desktop.audio.resident import ResidentWhisper, EngineError
from desktop.audio.wav import make_wav, RATE
from scripts.qualify_resident_voice import qualifies, accuracy, replace_settings, patched_engine

FAKE = r'''#!/usr/bin/env python3
import sys,json
from http.server import BaseHTTPRequestHandler,HTTPServer
from email.parser import BytesParser
from email import policy
if '--help' in sys.argv:
 print('--host --request-path --no-context --public');raise SystemExit(0)
def arg(name): return sys.argv[sys.argv.index(name)+1]
prefix=arg('--request-path')
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*a): pass
 def send(self,code,value):
  data=json.dumps(value).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
 def do_GET(self):
  self.send(200 if self.path==prefix+'/health' else 404,{'status':'ok'})
 def do_POST(self):
  if self.path!=prefix+'/inference':return self.send(404,{})
  raw=self.rfile.read(int(self.headers['Content-Length']))
  message=BytesParser(policy=policy.default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+raw)
  fields={part.get_param('name',header='content-disposition'):part for part in message.iter_parts()}
  assert fields['file'].get_filename()=='phrase.wav'
  assert fields['language'].get_content().strip() in ('auto','es')
  assert fields['audio_ctx'].get_content().strip()=='512'
  assert fields['translate'].get_content().strip()=='false'
  self.send(200,{'text':'Jarvis, hola'})
HTTPServer(('127.0.0.1',int(arg('--port'))),Handler).serve_forever()
'''

class ResidentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.binary=self.root/'whisper-server';self.binary.write_text(FAKE);self.binary.chmod(0o700)
        self.model=self.root/'ggml-base.bin';self.model.write_bytes(b'fake model')
        self.wav=make_wav([int(3000*math.sin(2*math.pi*220*i/RATE)) for i in range(RATE)])
        self.engine=ResidentWhisper(self.binary,self.model);self.addCleanup(self.engine.close)

    def test_one_process_reused_and_owner_pipe_closes_server(self):
        with patch.dict(os.environ,{'HTTP_PROXY':'http://invalid.invalid:1','HTTPS_PROXY':'http://invalid.invalid:1'}):
            first=self.engine.transcribe(self.wav);pid=self.engine._proc.pid;url=self.engine._url
            second=self.engine.transcribe(self.wav)
        self.assertEqual(first['text'],'Jarvis, hola');self.assertEqual(second['engine'],'whisper_resident')
        self.assertEqual(self.engine._proc.pid,pid)
        self.assertIn('127.0.0.1',url);self.assertIn('/jarvis-',url)
        from urllib.parse import urlsplit
        port=urlsplit(url).port;self.engine.close()
        with socket.socket() as sock:self.assertNotEqual(sock.connect_ex(('127.0.0.1',port)),0)

    def test_silence_does_not_start_a_model(self):
        silence=make_wav([0]*RATE)
        with patch.object(self.engine,'start',side_effect=AssertionError('must not load')):
            self.assertEqual(self.engine.transcribe(silence)['reason'],'no_voice_energy')

    def test_invalid_input_and_failed_resident_use_explicit_fallback(self):
        with self.assertRaises(ValueError):self.engine.transcribe(b'invalid')
        fallback=Mock();fallback.transcribe.return_value={'text':'Listo','engine':'whisper_cpp'}
        self.engine.fallback=fallback
        with patch.object(self.engine,'start',side_effect=EngineError('failed')):
            self.assertEqual(self.engine.transcribe(self.wav)['engine'],'whisper_cpp')
        fallback.transcribe.assert_called_once()

    def test_qualification_requires_bilingual_accuracy_and_speed(self):
        baseline=[{'seconds':7,'accuracy':1}]*4
        good=[{'seconds':2,'accuracy':1}]*4
        self.assertTrue(qualifies(baseline,good))
        self.assertFalse(qualifies(baseline,[{'seconds':6,'accuracy':1}]*4))
        self.assertFalse(qualifies(baseline,good[:3]+[{'seconds':1,'accuracy':.7}]))
        self.assertFalse(qualifies(baseline,good[:2]))
        self.assertEqual(accuracy('La puerta está abierta.','la puerta esta abierta'),1)

    def test_settings_and_unknown_source_preserved(self):
        result=replace_settings(b'OTHER_SECRET=keep\nVOICE_STT_BACKEND=whisper_cpp\n',{'VOICE_STT_BACKEND':'whisper_resident'})
        self.assertIn(b'OTHER_SECRET=keep',result)
        with self.assertRaises(ValueError):patched_engine(b'custom = True\n')

if __name__=='__main__':unittest.main()
