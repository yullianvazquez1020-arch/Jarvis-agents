"""Synthetic media; no external models, owner data or provider messages."""
import asyncio
import io
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import test_jarvis as base
import jarvis_mobile_media as m

j = base.j


class MobileMedia(unittest.TestCase):
    def setUp(self):
        base.Tests.setUp(self)
        self.env = patch.dict(os.environ, {'TELEGRAM_MEDIA_ENABLED': 'true'})
        self.env.start()
        self.addCleanup(self.env.stop)
        m._lock = asyncio.Lock()

    def photo(self):
        from PIL import Image
        out = io.BytesIO()
        Image.new('RGB', (1600, 900), 'blue').save(out, format='PNG')
        return out.getvalue()

    def test_resize_and_reencode(self):
        from PIL import Image
        with Image.open(io.BytesIO(m.image_bytes(self.photo()))) as img:
            self.assertEqual(img.format, 'JPEG')
            self.assertLessEqual(max(img.size), 1024)
            self.assertFalse(img.getexif())

    def test_invalid_and_oversize(self):
        for raw in (b'', b'<svg/>', b'x' * (m.MAX_BYTES + 1)):
            with self.assertRaises((ValueError, OSError)):
                m.image_bytes(raw)

    def test_secret_caption_rejected_before_download(self):
        with patch.object(j, 'AI_READY', True), patch.object(j, '_tg_file', AsyncMock()) as download, patch.object(j, '_tg_safe_send', AsyncMock()):
            asyncio.run(m.analyze(j, '123', {'file_id': 'demo'}, 'password=fictitious-only-123'))
            download.assert_not_awaited()

    def test_limits_and_disabled_reject_before_download(self):
        for media in ({'file_id': 'demo', 'file_size': m.MAX_BYTES + 1}, {'file_id': 'demo', 'duration': 61}):
            with patch.object(j, 'AI_READY', True), patch.object(j, '_tg_file', AsyncMock()) as download, patch.object(j, '_tg_safe_send', AsyncMock()):
                asyncio.run(m.analyze(j, '123', media, video=True))
                download.assert_not_awaited()
        with patch.dict(os.environ, {'TELEGRAM_MEDIA_ENABLED': 'false'}), patch.object(j, '_tg_file', AsyncMock()) as download, patch.object(j, '_tg_safe_send', AsyncMock()):
            asyncio.run(m.analyze(j, '123', {'file_id': 'demo'}))
            download.assert_not_awaited()

    def test_analysis_has_no_tools_or_history(self):
        response = SimpleNamespace(content=[SimpleNamespace(type='text', text='Un cuadro azul.')])
        with patch.object(j, 'AI_READY', True), patch.object(j, '_tg_file', AsyncMock(return_value=self.photo())), patch.object(j.client.messages, 'create', AsyncMock(return_value=response)) as model, patch.object(j, '_tg_send', AsyncMock()) as send:
            asyncio.run(m.analyze(j, '123', {'file_id': 'demo'}, 'Describe'))
            args = model.call_args.kwargs
            self.assertNotIn('tools', args)
            self.assertEqual(len(args['messages']), 1)
            self.assertNotIn('system_prompt', args['system'])
            self.assertIn('Un cuadro azul', send.call_args.args[1])

    def test_errors_never_disclose_exception(self):
        with patch.object(j, 'AI_READY', True), patch.object(j, '_tg_file', AsyncMock(side_effect=RuntimeError('secret-exception-payload'))), patch.object(j, '_tg_safe_send', AsyncMock()) as send, self.assertLogs(m.log, level='WARNING') as logs:
            asyncio.run(m.analyze(j, '123', {'file_id': 'demo'}))
            self.assertNotIn('secret-exception-payload', str(logs.output) + str(send.call_args))

    def test_low_memory_rejects_image_before_download(self):
        import jarvis_media_budget as budget
        with patch.object(j, 'AI_READY', True), patch.object(budget, 'memory_state', return_value=(350 * budget.MIB, 512 * budget.MIB)), patch.object(j, '_tg_file', AsyncMock()) as download, patch.object(j, '_tg_safe_send', AsyncMock()):
            asyncio.run(m.analyze(j, '123', {'file_id': 'demo'}))
            download.assert_not_awaited()

    def test_routing_private_and_receipt(self):
        def route(message):
            tasks = j._Tasks()
            asyncio.run(j._tg_route(message, tasks))
            return tasks.items
        msg = {'chat': {'id': 123, 'type': 'private'}, 'from': {'id': 123}, 'photo': [{'file_id': 'photo'}]}
        self.assertIs(route(msg)[0][0], m.analyze)
        self.assertIs(route({**msg, 'caption': '/recibo'})[0][0], j._extensions.receipt_photo)
        self.assertIs(route({**msg, 'chat': {'id': 123, 'type': 'group'}})[0][0], j._tg_safe_send)
        video = {'chat': msg['chat'], 'from': msg['from'], 'video': {'file_id': 'video'}}
        self.assertIs(route(video)[0][0], m.analyze)
        self.assertIs(route({**video, 'chat': {'id': 123, 'type': 'group'}})[0][0], j._tg_safe_send)
        self.assertIs(route({**msg, 'photo': [], 'text': '/movil'})[0][0], j._tg_safe_send)

    def test_short_video_real_decoder(self):
        import jarvis_chat_voice as voice
        async def scenario():
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / 'test.mp4'
                code = await voice._ffmpeg(['-f', 'lavfi', '-i', 'color=c=blue:s=64x64:d=1', '-threads', '1', '-pix_fmt', 'yuv420p', str(path)])
                self.assertEqual(code, 0)
                frames = await m.video_frames(path.read_bytes())
                self.assertGreaterEqual(len(frames), 1)
                self.assertLessEqual(len(frames), 4)
        asyncio.run(scenario())

    def test_notice_voice_failure_does_not_retry_text(self):
        import jarvis_chat_voice as voice
        with patch.dict(os.environ, {'TELEGRAM_NOTICE_VOICE': 'true'}), patch.object(voice, 'send_spoken_reply', AsyncMock(side_effect=RuntimeError('hidden payload'))) as speak, patch.object(j, '_tg_send', AsyncMock()) as send:
            self.assertFalse(asyncio.run(m.spoken_notice(j, 'Aviso')))
            speak.assert_awaited_once()
            send.assert_not_awaited()

    def test_video_webhook_queues_only_authenticated_owner(self):
        from fastapi.testclient import TestClient
        update = {'update_id': 90001, 'message': {'chat': {'id': 123, 'type': 'private'},
                  'from': {'id': 123}, 'video': {'file_id': 'synthetic', 'duration': 1}}}
        with patch.object(j, 'TG_SECRET', 'synthetic-webhook-secret'), patch.object(j, '_tg_enqueue', return_value='new') as enqueue, patch.object(j, '_tg_process', AsyncMock()):
            client = TestClient(j.app)
            self.assertEqual(client.post('/telegram', json=update).status_code, 401)
            enqueue.assert_not_called()
            self.assertEqual(client.post('/telegram', json=update, headers={'x-telegram-bot-api-secret-token': 'synthetic-webhook-secret'}).status_code, 200)
            enqueue.assert_called_once()
            enqueue.reset_mock()
            update['message']['from']['id'] = 456
            client.post('/telegram', json=update, headers={'x-telegram-bot-api-secret-token': 'synthetic-webhook-secret'})
            enqueue.assert_not_called()


if __name__ == '__main__':
    unittest.main()
