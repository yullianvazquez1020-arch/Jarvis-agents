import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installer', Path(__file__).parents[1] / 'scripts/install_combinado_update.py')
i = importlib.util.module_from_spec(spec); spec.loader.exec_module(i)

class InstallerTests(unittest.TestCase):
    def test_merge_preserves_independent_local_change(self):
        base = b'first\n' + b'unchanged\n' * 10 + b'last\n'
        local = base.replace(b'first', b'custom')
        new = base.replace(b'last', b'fixed')
        merged = i.merge_local(local, base, new)
        self.assertIn(b'custom', merged); self.assertIn(b'fixed', merged)

    def test_conflict_never_silently_overwrites(self):
        with self.assertRaises(RuntimeError):
            i.merge_local(b'custom\n', b'base\n', b'fixed\n')

    def test_known_intro_hotfix_already_present_in_update(self):
        base = b'  function startMic() {\n    if (!isOwner || rec) return;\n    capture();\n  }\n'
        local = base.replace(b'  function startMic() {\n', b'  function startMic() {\n    if (window.JarvisStopIntro) window.JarvisStopIntro();\n', 1)
        incoming = b'  function startMic() {\n    if (!isOwner || rec || micPending) return;\n    if(window.JarvisStopIntro)window.JarvisStopIntro();\n    capture();\n  }\n'
        self.assertEqual(i.merge_local(local, base, incoming, name='desktop/ui/app.js'), incoming)
        with self.assertRaises(RuntimeError):
            i.merge_local(local.replace(b'function startMic()', b'function customMic()'), base, incoming, name='desktop/ui/app.js')

    def test_preparation_preserves_source_and_configuration(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'; source.mkdir()
            def git(*args): return i.git(source, *args).decode().strip()
            git('init'); git('config', 'user.email', 'test@example.invalid'); git('config', 'user.name', 'Test')
            (source / 'desktop/ui').mkdir(parents=True); (source / 'scripts').mkdir()
            app = source / 'desktop/ui/app.js'
            app.write_text('first\n' + 'unchanged\n' * 10 + 'last\n')
            for name in i.AUDIO: (source / name).write_text('original music')
            (source / 'scripts/check.py').write_text('pass\n')
            git('add', '.'); git('commit', '-m', 'base'); base = git('rev-parse', 'HEAD')
            app.write_text(app.read_text().replace('last', 'fixed'))
            for name in i.AUDIO: (source / name).write_text('intro only')
            git('add', '.'); git('commit', '-m', 'update'); target = git('rev-parse', 'HEAD')
            git('checkout', '--detach', base)
            app.write_text(app.read_text().replace('first', 'custom'))
            for name in i.AUDIO: (source / name).write_text('local audio edit')
            config = source / 'desktop/config.env'; config.write_text('EXAMPLE=value\n')
            original = app.read_bytes(); dest = Path(folder) / 'installed'
            with patch.object(i, 'BASE', base): backup = i.prepare(source, target, dest)
            self.assertEqual(git('rev-parse', 'HEAD'), base)
            self.assertEqual(app.read_bytes(), original)
            self.assertIn('custom', (dest / 'desktop/ui/app.js').read_text())
            self.assertIn('fixed', (dest / 'desktop/ui/app.js').read_text())
            self.assertEqual((dest / 'desktop/config.env').read_bytes(), config.read_bytes())
            self.assertEqual((dest / 'desktop/config.env').stat().st_mode & 0o777, 0o600)
            self.assertEqual((backup / 'desktop/ui/startup.js').read_text(), 'local audio edit')
            self.assertEqual((dest / 'desktop/ui/startup.js').read_text(), 'intro only')
