import asyncio, os, tempfile, unittest, wave
from pathlib import Path
from unittest.mock import AsyncMock, patch
import test_growth as base
from jarvis_video import render_video

g=base.g

class VideoUpgradeTests(base.GrowthTests):
    def test_revision_keeps_uploaded_original(self):
        p=g.validate_plan(base.plan());p.update(id=1,title='Tres amigos de Puerto Rico: coquí, juey e iguana',status='uploaded_private',youtube_id='original')
        d=g.load();d['video_plans']=[p];g.save(d)
        r=g.improve_video_plan(1)
        self.assertNotEqual(r['id'],1)
        self.assertEqual(g._plan(1)['youtube_id'],'original')
        self.assertEqual(g._plan(1)['status'],'uploaded_private')
        self.assertEqual(r['revision_of'],1)
        self.assertEqual([s['character'] for s in r['scenes']],['friends','coqui','crab','iguana','friends','friends'])
        self.assertNotIn('sha256',r);self.assertNotIn('preview_sent',r)
    def test_character_validation(self):
        p=base.plan();p['scenes'][0]['character']='mickey'
        with self.assertRaises(ValueError):g.validate_plan(p)
    def test_video_voice_request_and_daily_budget(self):
        response=type('R',(),{'status_code':200,'headers':{'content-type':'audio/mpeg'},'content':b'audio'})()
        hc=AsyncMock();hc.post.return_value=response
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'OPENAI_API_KEY':'fake','TTS_AGENT_URL':'','VIDEO_TTS_PROVIDER':'openai'}),patch.object(g.core.httpx,'AsyncClient') as client,patch.object(g.core._connections,'reserve') as reserve:
            client.return_value.__aenter__.return_value=hc
            paths=asyncio.run(g.video_narration(base.plan(),temp))
            self.assertEqual(len(paths),3);self.assertEqual(reserve.call_count,3)
            body=hc.post.call_args.kwargs['json']
            self.assertEqual(body['voice'],'coral');self.assertIn('Latin American Spanish',body['instructions'])
            self.assertEqual(hc.post.call_args.args[0],'https://api.openai.com/v1/audio/speech')
    def test_voice_error_does_not_fall_back_to_silence(self):
        response=type('R',(),{'status_code':401,'headers':{},'content':b'error'})()
        hc=AsyncMock();hc.post.return_value=response
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'OPENAI_API_KEY':'fake','TTS_AGENT_URL':'','VIDEO_TTS_PROVIDER':'openai'}),patch.object(g.core.httpx,'AsyncClient') as client,patch.object(g.core._connections,'reserve'):
            client.return_value.__aenter__.return_value=hc
            with self.assertRaises(ValueError):asyncio.run(g.video_narration(base.plan(),temp))
    def test_voice_error_diagnostics_do_not_expose_provider_body(self):
        import httpx
        r=httpx.Response(429,json={'error':{'code':'insufficient_quota','message':'secret-key-private'}})
        error=g.voice_response_error(r)
        self.assertIn('saldo insuficiente',error);self.assertNotIn('secret-key',error)
        for status in (400,401,403,500):
            self.assertIn(f'HTTP {status}',g.voice_response_error(httpx.Response(status,text='private data')))
    def test_binary_json_is_rejected(self):
        import httpx
        for data in (b'{"error":"private"}',b'',b'not audio'):
            self.assertIsNotNone(g.voice_response_error(httpx.Response(200,content=data,headers={'content-type':'application/octet-stream'})))
        self.assertIsNone(g.voice_response_error(httpx.Response(200,content=b'\xff\xfb\x90\x00',headers={'content-type':'application/octet-stream'})))
    def test_actual_video_contains_audio(self):
        p=base.plan()
        for s in p['scenes']:s.update(character='coqui',seconds=4)
        with tempfile.TemporaryDirectory() as temp:
            audio=Path(temp)/'voice.wav'
            with wave.open(str(audio),'wb') as w:
                w.setparams((1,2,44100,0,'NONE','not compressed'));w.writeframes(b'\0\0'*44100)
            import subprocess, httpx
            from jarvis_video import _ffmpeg
            mp3=Path(temp)/'speech.mp3'
            subprocess.run([_ffmpeg(),'-y','-v','error','-i',str(audio),str(mp3)],check=True,timeout=30)
            response=httpx.Response(200,content=mp3.read_bytes(),headers={'content-type':'application/octet-stream'})
            hc=AsyncMock();hc.post.return_value=response
            with patch.dict(os.environ,{'OPENAI_API_KEY':'fake','TTS_AGENT_URL':'','VIDEO_TTS_PROVIDER':'openai'}),patch.object(g.core.httpx,'AsyncClient') as client,patch.object(g.core._connections,'reserve'):
                client.return_value.__aenter__.return_value=hc
                paths=asyncio.run(g.video_narration(p,temp))
            out=Path(temp)/'preview.mp4';r=render_video(p,out,paths)
            self.assertTrue(r['narration']);self.assertGreater(out.stat().st_size,1000)
            info=subprocess.run([_ffmpeg(),'-i',str(out)],capture_output=True,text=True).stderr
            self.assertIn('Audio: aac',info);self.assertIn('Video: h264',info)

if __name__=='__main__':unittest.main()
