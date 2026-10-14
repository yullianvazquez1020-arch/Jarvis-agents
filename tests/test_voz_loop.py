"""desktop/voz_loop.py: nada se aprueba por voz; barge-in. Datos ficticios."""
import sys, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop'))
import voz_loop as v


class FakeSpeaker(v.Speaker):
    def __init__(self): super().__init__(); self.on = True; self.stops = 0
    def speaking(self): return self.on
    def stop(self): self.stops += 1; self.on = False


class VozLoop(unittest.TestCase):
    def test_say_voice_british_default_and_override(self):
        import os
        from unittest.mock import patch
        with patch.dict(os.environ, {'JARVIS_REPLY_LANGUAGE': 'en-GB', 'JARVIS_SAY_VOICE': ''}):
            self.assertEqual(v.say_voice(), 'Daniel')
        with patch.dict(os.environ, {'JARVIS_REPLY_LANGUAGE': 'es', 'JARVIS_SAY_VOICE': ''}):
            self.assertEqual(v.say_voice(), 'Paulina')
        with patch.dict(os.environ, {'JARVIS_REPLY_LANGUAGE': 'en-GB', 'JARVIS_SAY_VOICE': 'Oliver'}):
            self.assertEqual(v.say_voice(), 'Oliver')

    def test_refuses_commands_and_codes(self):
        for t in ('/confirmar 1 123456', '  /aprobar 3', 'barra enviar 2', 'confirmar el pago a Cliente Ficticio',
                  'aprueba no, apruébalo: confirmar', 'el código es 4 8 2 9 1 7', 'mi pin es uno dos', ''):
            self.assertIsNotNone(v.refusal(t), t)

    def test_allows_normal_requests(self):
        for t in ('Prepara una propuesta para Cliente Ficticio SA', '¿Cómo van las ventas de hoy?'):
            self.assertIsNone(v.refusal(t), t)

    def test_refused_text_never_sent(self):
        calls = []
        post = lambda *a, **k: calls.append(k) or type('R', (), {'status_code': 200})()
        self.assertFalse(v.send_to_jarvis('/confirmar 9 000000', 'https://ejemplo.invalid', 'x', post))
        self.assertEqual(calls, [])
        self.assertTrue(v.send_to_jarvis('Resume mis tareas', 'https://ejemplo.invalid/', 'secreto-ficticio', post))
        self.assertEqual(calls[0]['headers'], {'X-Jarvis-Secret': 'secreto-ficticio'})

    def test_barge_in_and_segmentation(self):
        spk = FakeSpeaker()
        frames = [b'S'] * 3 + [b'.'] * 30 + [b'S'] * 2
        out = list(v.segment(frames, lambda f: f == b'S', spk))
        self.assertEqual(spk.stops, 1); self.assertEqual(len(out), 2)


if __name__ == '__main__':
    unittest.main()
