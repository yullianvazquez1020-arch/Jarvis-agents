"""/publicaryoutube: lo que dice Google queda guardado; nunca se da por publicado; nunca se reintenta solo.
/mejorarvideo: no deja revisiones huérfanas. Sin red real: Google simulado."""
import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_jarvis as base
j = base.j
G = j._growth


class FakeResp:
    def __init__(self, status, body):
        self.status_code = status; self._body = body; self.content = json.dumps(body).encode(); self.headers = {}
    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Google:
    """Token, channel and videos.update. `update` decides the PUT answer."""
    def __init__(self, update):
        self.update = update; self.calls = []
    def client(self):
        g = self
        class C:
            def __init__(self, *a, **k): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *a): pass
            async def request(self, method, url, **kw):
                g.calls.append((method, url, kw))
                if "oauth2" in url:
                    return FakeResp(200, {"access_token": "ya29.SECRET-TOKEN"})
                if url.endswith("/channels"):
                    return FakeResp(200, {"items": [{"id": "UC123"}]})
                if method == "PUT":
                    if isinstance(g.update, Exception):
                        raise g.update
                    return FakeResp(*g.update)
                raise AssertionError(url)
        return C


class Publish(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True)
        self.env = patch.dict(os.environ, {"YOUTUBE_CLIENT_ID": "cid", "YOUTUBE_CLIENT_SECRET": "csecret",
                                           "YOUTUBE_REFRESH_TOKEN": "1//refresh-SECRET", "YOUTUBE_CHANNEL_ID": "UC123"})
        self.env.start(); self.addCleanup(self.env.stop)
        with j._data_lock:
            d = G.load()
            d["video_plans"] = [{"id": 51, "title": "Plan 51", "status": "uploaded_private", "channel_id": "UC123",
                                 "youtube_id": "vid51"},
                                {"id": 5, "title": "Video 5", "status": "published", "channel_id": "UC123",
                                 "youtube_id": "vid5"}]
            G.save(d)

    def run_publish(self, update, pid=51):
        g = Google(update)
        with patch.object(j.httpx, "AsyncClient", g.client()):
            try:
                return asyncio.run(G.publish_youtube(pid)), g
            except ValueError as e:
                return str(e), g

    def plan(self, pid):
        return next(x for x in G.load()["video_plans"] if x["id"] == pid)

    def test_google_rejection_is_saved_and_shown(self):
        body = {"error": {"code": 403, "message": "The request cannot be completed because you have exceeded your quota.",
                          "errors": [{"reason": "quotaExceeded", "domain": "youtube.quota"}]}}
        msg, g = self.run_publish((403, body))
        self.assertIn("Publicación sin confirmar", msg); self.assertIn("HTTP 403", msg); self.assertIn("quotaExceeded", msg)
        p = self.plan(51)
        self.assertEqual(p["status"], "unknown_publish")                                  # never "published"
        self.assertEqual((p["publish_error"]["http_status"], p["publish_error"]["reason"]), (403, "quotaExceeded"))
        self.assertIn("exceeded your quota", p["publish_error"]["message"])
        raw = json.dumps(G.load())
        for secret in ("ya29.SECRET-TOKEN", "1//refresh-SECRET", "csecret"):
            self.assertNotIn(secret, raw); self.assertNotIn(secret, msg)
        self.assertEqual(sum(1 for c in g.calls if c[0] == "PUT"), 1)                     # no automatic retry

    def test_network_failure_is_saved(self):
        msg, _ = self.run_publish(j.httpx.ConnectError("boom"))
        self.assertIn("red", msg); self.assertEqual(self.plan(51)["publish_error"]["kind"], "network")
        self.assertEqual(self.plan(51)["status"], "unknown_publish")

    def test_ok_but_still_private_is_explained(self):
        out, _ = self.run_publish((200, {"id": "vid51", "status": {"privacyStatus": "private"}}))
        self.assertEqual(out["status"], "uploaded_private"); self.assertEqual(out["youtube_privacy"], "private")
        self.assertIn("privacyStatus=private", self.plan(51)["publish_note"])

    def test_public_clears_previous_error(self):
        with j._data_lock:
            d = G.load(); d["video_plans"][0]["publish_error"] = {"kind": "http"}; G.save(d)
        out, _ = self.run_publish((200, {"id": "vid51", "status": {"privacyStatus": "public"}}))
        self.assertEqual(out["status"], "published"); self.assertNotIn("publish_error", self.plan(51))

    def test_unknown_publish_cannot_be_republished_and_video_5_untouched(self):
        self.run_publish((500, {"error": {"code": 500, "message": "backend"}}))
        msg, g = self.run_publish((200, {"status": {"privacyStatus": "public"}}))
        self.assertIn("no encontrado", msg); self.assertFalse([c for c in g.calls if c[0] == "PUT"])
        self.assertEqual(self.plan(5), {"id": 5, "title": "Video 5", "status": "published", "channel_id": "UC123",
                                        "youtube_id": "vid5"})

    def test_error_is_still_a_value_error_with_same_text(self):
        e = G.ServiceHTTPError("El servicio respondió HTTP 403; revisa permisos/cuota/configuración", 403, "forbidden", "x")
        self.assertIsInstance(e, ValueError); self.assertTrue(str(e).startswith("El servicio respondió HTTP 403"))


class ImproveVideo(unittest.TestCase):
    def setUp(self):
        j.DATA_DIR = Path(tempfile.mkdtemp()); j.USE_REDIS = False
        j._fence.update(mode="off", leader=True)

    def test_no_orphan_revision_while_rendering(self):
        sent = []
        async def tg(chat, text): sent.append(text)
        with j._data_lock:
            d = G.load(); d["video_plans"] = [{"id": 1, "title": "Cuento", "status": "published", "youtube_id": "v1",
                                               "language": "es", "scenes": []}]; G.save(d)
        async def go():
            async with G._video_lock:
                await G.growth_command(1, "/mejorarvideo", "1")
        with patch.object(j, "_tg_safe_send", new=tg):
            asyncio.run(go())
        self.assertIn("Ya estoy produciendo", sent[-1])
        self.assertEqual([p["id"] for p in G.load()["video_plans"]], [1])
        self.assertEqual(G.load()["video_plans"][0]["status"], "published")


if __name__ == "__main__":
    unittest.main()
