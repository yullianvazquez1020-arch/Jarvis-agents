import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
import test_growth as base
import jarvis_local_tts as tts

class LocalVoiceTests(unittest.TestCase):
    def test_default_voice_never_calls_paid_api(self):
        env=dict(os.environ);env.pop('VIDEO_TTS_PROVIDER',None)
        env.update(OPENAI_API_KEY='configured-but-not-used',TTS_AGENT_URL='https://paid.example')
        with patch.dict(os.environ,env,clear=True),patch.object(tts,'local_narration',new=AsyncMock(return_value=['local.wav'])) as local,patch.object(base.g.core.httpx,'AsyncClient') as http:
            self.assertEqual(asyncio.run(base.g.video_narration(base.plan(),'/tmp')),['local.wav'])
            local.assert_awaited_once();http.assert_not_called()
    def test_local_failure_has_no_paid_fallback(self):
        with patch.dict(os.environ,{'VIDEO_TTS_PROVIDER':'piper','OPENAI_API_KEY':'not-used'}),patch.object(tts,'local_narration',new=AsyncMock(side_effect=ValueError('local failed'))),patch.object(base.g.core.httpx,'AsyncClient') as http:
            with self.assertRaises(ValueError):asyncio.run(base.g.video_narration(base.plan(),'/tmp'))
            http.assert_not_called()
    def test_invalid_narration_rejected_before_loading_model(self):
        for texts in ([],['x']*9,['x'*401],[None]):
            with self.assertRaises(ValueError):tts.synthesize(texts,'/tmp',Path('/nonexistent'))
    def test_cached_model_is_offline(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            for name in tts.HASHES:(root/name).write_bytes(b'fixture')
            with patch.object(tts,'digest',side_effect=lambda p:tts.HASHES[p.name]),patch('httpx.stream') as request:
                self.assertEqual(tts.ensure_model(root),root/tts.MODEL);request.assert_not_called()
    def test_english_not_silently_read_in_spanish(self):
        with self.assertRaises(ValueError):asyncio.run(tts.local_narration({'language':'en','scenes':[]},'/tmp'))
