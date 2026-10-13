"""AUTO_PUBLISH_OWN_SOCIAL: el agente publica SUS posts en las páginas propias del dueño. Datos ficticios."""
import asyncio, os, unittest
from unittest.mock import AsyncMock, patch
import test_jarvis as base
from test_connections import META
j = base.j; c = j._connections
ON = {**META, 'AUTO_PUBLISH_OWN_SOCIAL': 'true', 'BRAIN_ENABLED': 'true', 'AUTO_PUBLISH_MAX_DAY': '2'}


class AutoPublicar(unittest.TestCase):
    def setUp(self): base.Tests.setUp(self)
    def run_(self, co): return asyncio.run(co)
    def draft(self): return c.prepare_social_post('facebook', 'Post ficticio de Empresa Ejemplo', '')['id']

    def test_off_by_default_and_tool_refuses(self):
        with patch.dict(os.environ, {**META, 'AUTO_PUBLISH_OWN_SOCIAL': ''}), patch.object(c, 'graph', new=AsyncMock()) as g:
            with self.assertRaises(ValueError): self.run_(c.auto_publish_own_post(self.draft()))
            g.assert_not_called()

    def test_publishes_notifies_owner_with_link_and_caps(self):
        graph = AsyncMock(side_effect=lambda m, path, **k: {'id': 'remote-x'} if m == 'POST' else
                          {'permalink_url': 'https://www.facebook.com/ficticio/posts/1'})
        with patch.dict(os.environ, ON), patch.object(c, 'graph', new=graph), \
             patch.object(j, '_tg_safe_send', new=AsyncMock()) as note:
            r = self.run_(c.auto_publish_own_post(self.draft()))
            self.assertEqual(r['status'], 'published'); self.assertIn('facebook.com', r['link'])
            self.assertEqual(note.await_args.args[0], j.TG_OWNER); self.assertIn('https://', note.await_args.args[1])
            with self.assertRaises(ValueError): self.run_(c.auto_publish_own_post(r['id']))  # never repeats
            self.run_(c.auto_publish_own_post(self.draft()))
            with self.assertRaises(ValueError): self.run_(c.auto_publish_own_post(self.draft()))  # cap 2/day

    def test_brain_off_is_kill_switch(self):
        with patch.dict(os.environ, ON), patch.object(c, 'graph', new=AsyncMock()) as g:
            import jarvis_brain
            with patch.object(jarvis_brain, 'owner_enabled', return_value=False):
                with self.assertRaises(ValueError): self.run_(c.auto_publish_own_post(self.draft()))
            g.assert_not_called()

    def test_not_in_read_only_or_voice_and_caps_unchanged(self):
        self.assertNotIn('auto_publish_own_post', j.READ_ONLY_TOOLS)
        self.assertEqual((j.HARD_MAX_ORDER_USD, j.HARD_MAX_DAY_USD), (100.0, 300.0))

    def test_tiktok_private_by_default_and_capped(self):
        class R:
            status_code = 200
            def json(self): return {'data': {'publish_id': 'pub-ficticio-1'}}
        hc = AsyncMock(); hc.post = AsyncMock(return_value=R())
        hc.__aenter__ = AsyncMock(return_value=hc); hc.__aexit__ = AsyncMock(return_value=False)
        env = {**ON, 'TIKTOK_ACCESS_TOKEN': 'token-ficticio-tiktok-123456', 'AUTO_PUBLISH_MAX_DAY': '1'}
        with patch.dict(os.environ, env), patch.object(j.httpx, 'AsyncClient', return_value=hc), \
             patch.object(j, '_tg_safe_send', new=AsyncMock()) as note:
            r = self.run_(c.auto_publish_tiktok('Video ficticio', 'https://assets.example.com/v.mp4'))
            self.assertEqual((r['privacy'], r['publish_id']), ('SELF_ONLY', 'pub-ficticio-1'))
            self.assertEqual(hc.post.await_args.kwargs['json']['post_info']['privacy_level'], 'SELF_ONLY')
            self.assertIn('TikTok', note.await_args.args[1])
            with self.assertRaises(ValueError): self.run_(c.auto_publish_tiktok('Otro', 'https://assets.example.com/w.mp4'))
            self.assertEqual(hc.post.await_count, 1)

    def test_tiktok_and_youtube_off_without_flag_or_keys(self):
        with patch.dict(os.environ, {'AUTO_PUBLISH_OWN_SOCIAL': '', 'TIKTOK_ACCESS_TOKEN': 'token-ficticio-tiktok-123456'}):
            with self.assertRaises(ValueError): self.run_(c.auto_publish_tiktok('x', 'https://assets.example.com/v.mp4'))
        with patch.dict(os.environ, {**ON, 'YOUTUBE_CLIENT_ID': '', 'YOUTUBE_REFRESH_TOKEN': ''}):
            with self.assertRaises(ValueError): self.run_(c.auto_publish_youtube(1))

    def test_youtube_uses_existing_upload_and_publish(self):
        env = {**ON, 'YOUTUBE_CLIENT_ID': 'id-ficticio', 'YOUTUBE_CLIENT_SECRET': 's-ficticio', 'YOUTUBE_REFRESH_TOKEN': 'r-ficticio'}
        with patch.dict(os.environ, env), \
             patch.object(j._growth, 'upload_youtube', new=AsyncMock(return_value={'url': 'https://www.youtube.com/watch?v=FICT'})) as up, \
             patch.object(j._growth, 'publish_youtube', new=AsyncMock(return_value={'status': 'published', 'url': 'https://www.youtube.com/watch?v=FICT'})) as pub, \
             patch.object(j, '_tg_safe_send', new=AsyncMock()) as note:
            self.assertEqual(self.run_(c.auto_publish_youtube(7))['status'], 'published')
        up.assert_awaited_once_with(7); pub.assert_awaited_once_with(7); self.assertIn('youtube.com', note.await_args.args[1])


if __name__ == '__main__':
    unittest.main()
