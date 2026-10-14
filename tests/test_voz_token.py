"""/ws/voz acepta el token de dispositivo jd1 (emparejado con /emparejar). Tokens ficticios."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests')); sys.path.insert(0, str(ROOT / 'desktop'))
import desktop_helpers as h
import voz_continua as client
from starlette.websockets import WebSocketDisconnect

j, D = h.j, h.D


class VozToken(h.DesktopBase):
    def ws_ok(self, headers):
        with patch.dict(os.environ, {'VOZ_CONTINUA_ENABLED': 'true'}):
            try:
                with self.client.websocket_connect('/ws/voz', headers=headers) as ws:
                    return ws.receive_json()['type'] == 'listo'
            except WebSocketDisconnect:
                return False

    def test_paired_device_token_opens_voice(self):
        tok, _ = self.pair()
        self.assertTrue(self.ws_ok({'Authorization': f'Bearer {tok}'}))

    def test_bad_revoked_expired_or_off(self):
        tok, dev = self.pair()
        self.assertFalse(self.ws_ok({'Authorization': 'Bearer jd1.999.' + 'x' * 40}))
        self.assertFalse(self.ws_ok({}))
        with patch.object(D, '_expired', lambda d: True):
            self.assertFalse(self.ws_ok({'Authorization': f'Bearer {tok}'}))
        with patch.object(D, 'ENABLED', False):
            self.assertFalse(self.ws_ok({'Authorization': f'Bearer {tok}'}))
        d = D.load(); d['devices'][str(dev)]['revoked'] = True; D.save(d)
        self.assertFalse(self.ws_ok({'Authorization': f'Bearer {tok}'}))


class ClientAuth(unittest.TestCase):
    TOK = 'jd1.7.' + 'f' * 40   # ficticio

    def test_env_token_first(self):
        self.assertEqual(client.auth_headers({'JARVIS_DEVICE_TOKEN': self.TOK, 'JARVIS_ENCARGO_SECRET': 's'}, '/nope'),
                         {'Authorization': 'Bearer ' + self.TOK})

    def test_device_json_then_secret(self):
        with tempfile.TemporaryDirectory() as home:
            Path(home, 'device.json').write_text(json.dumps({'token': self.TOK}))
            self.assertEqual(client.auth_headers({}, home), {'Authorization': 'Bearer ' + self.TOK})
        with tempfile.TemporaryDirectory() as home:
            self.assertEqual(client.auth_headers({'JARVIS_ENCARGO_SECRET': 'secreto-ficticio'}, home),
                             {'X-Jarvis-Secret': 'secreto-ficticio'})
            with self.assertRaises(ValueError):
                client.auth_headers({}, home)


if __name__ == '__main__':
    unittest.main()
