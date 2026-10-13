"""Script local de refresh token YouTube: datos ficticios, sin red."""
import io, json, os, sys, tempfile, unittest, urllib.parse
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import youtube_refresh_token as y


class Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): pass


class T(unittest.TestCase):
    def _json(self, data):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False); json.dump(data, f); f.close()
        self.addCleanup(os.unlink, f.name); return f.name

    def test_desktop_client_loads(self):
        p = self._json({"installed": {"client_id": "fake-id.apps.googleusercontent.com", "client_secret": "FAKE-SECRET"}})
        self.assertEqual(y.load_client(p), ("fake-id.apps.googleusercontent.com", "FAKE-SECRET"))

    def test_web_client_rejected(self):
        p = self._json({"web": {"client_id": "x", "client_secret": "y"}})
        with self.assertRaises(SystemExit): y.load_client(p)

    def test_auth_url_offline_full_scope_pkce(self):
        v, c = y.pkce_pair()
        q = urllib.parse.parse_qs(urllib.parse.urlparse(y.build_auth_url("cid", "http://127.0.0.1:5", c, "st")).query)
        self.assertEqual(q["scope"], ["https://www.googleapis.com/auth/youtube"])
        self.assertEqual(q["access_type"], ["offline"]); self.assertEqual(q["prompt"], ["consent"])
        self.assertEqual(q["code_challenge_method"], ["S256"]); self.assertNotIn(v, q["code_challenge"][0])

    def test_exchange_requires_refresh(self):
        with self.assertRaises(SystemExit):
            y.exchange("c", "s", "code", "r", "v", opener=lambda req: Resp(json.dumps({"access_token": "a"}).encode()))
        seen = {}
        def op(req):
            seen.update(urllib.parse.parse_qs(req.data.decode())); return Resp(b'{"access_token":"a","refresh_token":"1//FAKE"}')
        self.assertEqual(y.exchange("c", "s", "code", "r", "v", opener=op)["refresh_token"], "1//FAKE")
        self.assertEqual(seen["code_verifier"], ["v"]); self.assertEqual(seen["grant_type"], ["authorization_code"])

    def test_channel_and_render_lines(self):
        op = lambda req: Resp(b'{"items":[{"id":"UCfake123","snippet":{"title":"Canal Ficticio"}}]}')
        self.assertEqual(y.channel_of("tok", opener=op), ("UCfake123", "Canal Ficticio"))
        with self.assertRaises(SystemExit): y.channel_of("tok", opener=lambda r: Resp(b'{"items":[]}'))
        lines = y.render_lines("cid", "sec", "1//r", "UCfake123")
        self.assertEqual([l.split("=")[0] for l in lines],
                         ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN", "YOUTUBE_CHANNEL_ID"])

    def test_env_example_lists_all_upload_vars(self):
        env = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
        for k in ("YOUTUBE_CLIENT_ID=", "YOUTUBE_CLIENT_SECRET=", "YOUTUBE_REFRESH_TOKEN=", "YOUTUBE_CHANNEL_ID="):
            self.assertIn(k, env)


if __name__ == "__main__":
    unittest.main()
