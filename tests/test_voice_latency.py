from pathlib import Path
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / 'desktop'))
from audio import engines, latencia
from audio.wav import make_wav

class VoiceLatencyTests(unittest.TestCase):
    def test_phrase_buffer(self):
        subprocess.run(['node', str(ROOT / 'scripts/check_phrase_buffer.cjs')], check=True)

    def test_decoder_fast_and_legacy(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp) / 'model.bin'; model.write_bytes(b'm')
            for fast in (False, True):
                e = engines.WhisperCpp(sys.executable, str(model), fast=fast)
                def run(cmd, **kwargs):
                    Path(cmd[cmd.index('-of') + 1] + '.txt').write_text('hello')
                with patch.object(engines, '_run', side_effect=run) as invoke:
                    out = e.transcribe(make_wav([1000, -1000] * 8000))
                self.assertEqual(out['text'], 'hello')
                args = invoke.call_args.args[0]
                self.assertEqual('-bs' in args, fast)
                if fast:
                    self.assertEqual(args[args.index('-bs') + 1], '1')
                    self.assertEqual(args[args.index('-bo') + 1], '1')

    def test_voice_only_is_not_complete_turn(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(latencia, 'log_path', return_value=Path(tmp)/'lat.log'):
            self.assertFalse(latencia.write('greet', {'tts_first_audio_ms':200})['complete_voice_turn'])
            self.assertTrue(latencia.write('spoken', dict(vad_ms=350, stt_ms=500, llm_first_token_ms=1000, tts_first_audio_ms=200))['complete_voice_turn'])
