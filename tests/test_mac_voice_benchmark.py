import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('voice_bench', Path(__file__).parents[1]/'scripts/mac_voice_benchmark.py')
b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)

def candidate(seconds=1, accuracy=1):
    return {'candidate': {'model':'base.bin', 'threads':2, 'fast':True},
            'samples':[{'seconds':seconds, 'accuracy':accuracy} for _ in range(2)]}

class VoiceBenchmark(unittest.TestCase):
    def test_word_accuracy_penalizes_omissions_and_insertions(self):
        self.assertEqual(b.accuracy('La información.', 'la informacion'), 1)
        self.assertLess(b.accuracy('la puerta esta cerrada', 'la puerta'), .9)
        self.assertLess(b.accuracy('la puerta', 'la puerta la puerta'), .9)

    def test_selection_requires_latency_accuracy_and_improvement(self):
        baseline = candidate(8)['samples']
        good = candidate(1.5)
        self.assertIs(b.choose([candidate(3), candidate(1, .8), good], baseline), good)
        self.assertIsNone(b.choose([candidate(3), candidate(1, .8)], baseline))
        self.assertIsNone(b.choose([candidate(1.9)], candidate(2)['samples']))
        self.assertIsNone(b.choose([good], [{'error':'timeout'}]))

    def test_settings_preserve_unrelated_configuration(self):
        original = '# private config\nEXAMPLE_SECRET=unchanged\nVOICE_STT_THREADS=4\nVOICE_STT_THREADS=8\n'
        new = b.replace_settings(original, {'VOICE_STT_THREADS':2})
        self.assertIn('EXAMPLE_SECRET=unchanged', new)
        self.assertEqual(new.count('VOICE_STT_THREADS='), 1)

    def test_restart_exception_restores_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'config.env'; original = 'EXAMPLE_SECRET=unchanged\n'; p.write_text(original)
            with patch.object(b, 'restart_and_check', side_effect=[RuntimeError('failed'), True]):
                result = b.apply_choice(p, original, candidate()['candidate'], Path(tmp))
            self.assertFalse(result['applied']); self.assertTrue(result['rollback_healthy'])
            self.assertEqual(p.read_text(), original)
            backups = list(Path(tmp).glob('config.before-*'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)

    def test_concurrent_edit_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'config.env'; p.write_text('new')
            with self.assertRaises(RuntimeError):
                b.apply_choice(p, 'old', candidate()['candidate'], Path(tmp))
            self.assertEqual(p.read_text(), 'new')

    def test_linux_never_runs_mac_actions(self):
        with patch.object(b.sys, 'platform', 'linux'), patch.object(b.subprocess, 'run') as run:
            with self.assertRaises(RuntimeError):
                b.main(['--apply'])
            run.assert_not_called()

    def test_recognition_reports_only_numeric_timings(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def fake_run(cmd, **kwargs):
                self.assertEqual(cmd[-4:], ['-bs', '1', '-bo', '1'])
                Path(cmd[cmd.index('-of') + 1] + '.txt').write_text(b.PHRASES[0])
                return SimpleNamespace(returncode=0, stderr=b'private output\nwhisper_print_timings: encode time = 1200.5 ms\n')
            with patch.object(b.subprocess, 'run', side_effect=fake_run):
                result = b.run_sample('whisper', candidate()['candidate'], root/'sample.wav', b.PHRASES[0], root, 'es')
            self.assertEqual(result['accuracy'], 1)
            self.assertEqual(result['engine_ms'], {'encode': 1200.5})
            self.assertNotIn('private', str(result))
