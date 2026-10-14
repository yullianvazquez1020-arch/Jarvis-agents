"""Voz continua (/ws/voz): VAD, turnos, barge-in, rechazo de aprobaciones por voz, auth. Datos ficticios."""
import array, asyncio, json, math, os, sys, unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'desktop'))
sys.path.insert(0, str(ROOT / 'tests'))
import jarvis_voz_continua as v
import voz_continua as client

SILENCE = array.array('h', [0] * 480).tobytes()
VOICE = array.array('h', [int(6000 * math.sin(i / 3)) for i in range(480)]).tobytes()


def speech(ms=600):
    return VOICE * (ms // 30)


def quiet(ms=900):
    return SILENCE * (ms // 30)


class Harness:
    def __init__(self, text='¿Cómo van las ventas de Tienda Ficticia?', answer='Van bien. Todo en orden.', slow=0.0):
        self.events, self.audio, self.replies, self.langs = [], [], [], []
        self.text, self.answer, self.slow = text, answer, slow
        async def transcribe(wav):
            assert wav[:4] == b'RIFF'; return self.text
        async def reply(t, lang="es"):
            self.replies.append(t); self.langs.append(lang)
            if self.slow: await asyncio.sleep(self.slow)
            return self.answer
        async def speak(t, lang="es"): return b'RIFF' + lang.encode() + t.encode()
        async def sj(d): self.events.append(d)
        async def sb(b): self.audio.append(b)
        self.s = v.VozSession(transcribe=transcribe, reply=reply, speak=speak, send_json=sj, send_bytes=sb,
                              redact=lambda s: s.replace('4111 1111 1111 1111', '[TARJETA]'))

    def types(self): return [e['type'] for e in self.events]


def run(coro): return asyncio.run(coro)


class VozContinua(unittest.TestCase):
    def test_vad_separates_voice_and_silence(self):
        d = v.VAD()
        self.assertFalse(d.is_speech(SILENCE)); self.assertTrue(d.is_speech(VOICE))

    def test_full_turn_streams_sentences(self):
        h = Harness()
        async def go():
            await h.s.feed(quiet(300) + speech() + quiet()); await h.s.task
        run(go())
        self.assertEqual(h.types()[:3], ['escuchando', 'transcripcion', 'respuesta'])
        self.assertEqual(h.types()[-1], 'audio_fin')
        self.assertEqual(len(h.audio), 2)                    # una trama por frase
        self.assertEqual(h.replies, ['¿Cómo van las ventas de Tienda Ficticia?'])
        self.assertEqual(h.langs, ['es'])

    def test_english_turn_keeps_its_language(self):
        h = Harness(text='Please call me tomorrow about the appointment', answer='Thursday works.')
        async def go():
            await h.s.feed(speech() + quiet()); await h.s.task
        run(go())
        self.assertEqual(h.langs, ['en'])
        self.assertEqual(h.events[1]['idioma'], 'en')
        self.assertTrue(h.audio[0].startswith(b'RIFFen'))

    def test_english_refusal_is_in_english(self):
        self.assertIn('Telegram', v.refusal('approve the payment', 'en'))
        self.assertIn('voz', v.refusal('aprobar el pago'))
        self.assertEqual(v.idioma('¿Cómo van las ventas?'), 'es')
        self.assertEqual(v.idioma('ok', 'en'), 'en')
        self.assertEqual(v.voz_de('es'), 'es')
        self.assertEqual(v.voz_de('en'), 'alan')
        import jarvis_local_tts as tts
        self.assertEqual(tts.profile('es')[0], 'es_MX-ald-medium.onnx')
        self.assertEqual(tts.profile('alan')[0], 'en_GB-alan-medium.onnx')

    def test_short_noise_is_not_a_turn(self):
        h = Harness()
        run(h.s.feed(quiet(300) + speech(60) + quiet()))
        self.assertIsNone(h.s.task); self.assertEqual(h.events, [])

    def test_barge_in_cancels_reply(self):
        h = Harness(slow=5)
        async def go():
            await h.s.feed(speech() + quiet()); await asyncio.sleep(0.01)
            self.assertTrue(h.s.responding)
            await h.s.feed(speech(150))                       # el dueño interrumpe
            self.assertFalse(h.s.responding)
            await h.s.close()
        run(go())
        self.assertIn('interrumpido', h.types()); self.assertNotIn('respuesta', h.types())

    def test_voice_cannot_approve_or_dictate_codes(self):
        for t in ('/aprobar 3', 'confirmar el pago de 90 dólares a Cliente Ficticio', 'el código es 4 8 2 9', 'barra enviar 2'):
            h = Harness(text=t)
            async def go():
                await h.s.feed(speech() + quiet()); await h.s.task
            run(go())
            self.assertIn('rechazado', h.types(), t); self.assertEqual(h.replies, [], t)

    def test_transcript_is_redacted(self):
        h = Harness(text='Guarda la tarjeta 4111 1111 1111 1111 de Cliente Ficticio')
        async def go():
            await h.s.feed(speech() + quiet()); await h.s.task
        run(go())
        tr = [e for e in h.events if e['type'] == 'transcripcion'][0]['texto']
        self.assertNotIn('4111 1111', tr)

    def test_tts_failure_still_shows_text(self):
        h = Harness()
        async def bad(t): raise RuntimeError('sin piper')
        h.s.speak = bad
        async def go():
            await h.s.feed(speech() + quiet()); await h.s.task
        run(go())
        self.assertIn('respuesta', h.types()); self.assertIn('error', h.types()); self.assertEqual(h.audio, [])

    def test_disabled_by_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('VOZ_CONTINUA_ENABLED', None); self.assertFalse(v.enabled())


class Client(unittest.TestCase):
    def test_ws_url_requires_tls_outside_localhost(self):
        self.assertEqual(client.ws_url('https://jarvis.ejemplo.invalid/'), 'wss://jarvis.ejemplo.invalid/ws/voz')
        self.assertEqual(client.ws_url('http://localhost:8000'), 'ws://localhost:8000/ws/voz')
        with self.assertRaises(ValueError): client.ws_url('http://jarvis.ejemplo.invalid')
        with self.assertRaises(ValueError): client.headers('')

    def test_interrupt_event_clears_player(self):
        p = client.Player(); p.push(v.pcm_to_wav(SILENCE))
        client.handle_event(json.dumps({'type': 'interrumpido'}), p)
        self.assertEqual(p.queue, [])


class Endpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import test_hardening as h
        cls.j = h.j

    def test_ws_auth_and_turn(self):
        j = self.j
        from fastapi.testclient import TestClient
        from starlette.websockets import WebSocketDisconnect
        old = j.ENCARGO_SECRET; j.ENCARGO_SECRET = 'secreto-ficticio-voz-123'
        async def tr(w): return 'Resume mis tareas de hoy'
        async def rp(t): return 'Tienes dos tareas.'
        async def sp(t, lang="es"): return b'RIFFfake'
        try:
            c = TestClient(j.app)
            with patch.dict(os.environ, {'VOZ_CONTINUA_ENABLED': 'true'}), \
                 patch.object(j, '_voz_c_transcribe', tr), patch.object(j, '_voz_c_reply', rp), patch.object(j, '_voz_c_speak', sp):
                with self.assertRaises(WebSocketDisconnect):
                    with c.websocket_connect('/ws/voz', headers={'X-Jarvis-Secret': 'otro'}) as ws: ws.receive_json()
                with c.websocket_connect('/ws/voz', headers={'X-Jarvis-Secret': 'secreto-ficticio-voz-123'}) as ws:
                    self.assertEqual(ws.receive_json()['type'], 'listo')
                    ws.send_bytes(speech() + quiet())
                    got = [ws.receive_json() for _ in range(3)]
                    self.assertEqual([g['type'] for g in got], ['escuchando', 'transcripcion', 'respuesta'])
                    self.assertEqual(ws.receive_bytes(), b'RIFFfake')
                    self.assertEqual(ws.receive_json()['type'], 'audio_fin')
                    ws.send_text(json.dumps({'type': 'fin'}))
            with self.assertRaises(WebSocketDisconnect):                     # apagado por defecto
                with c.websocket_connect('/ws/voz', headers={'X-Jarvis-Secret': 'secreto-ficticio-voz-123'}) as ws: ws.receive_json()
        finally:
            j.ENCARGO_SECRET = old

    def test_reply_is_read_only_voice(self):
        j = self.j; seen = {}
        async def fake_run(session, message, **kw): seen.update(kw); return 'ok'
        with patch.object(j, 'run', fake_run):
            asyncio.run(j._voz_c_reply('Hola Jarvis'))
        self.assertEqual(seen.get('read_only'), 'voice')


if __name__ == '__main__':
    unittest.main()
