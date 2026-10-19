"""Protect the owner's newer local panel from partial or mismatched updates."""
import difflib
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import install_voice_continuity as installer


class VoiceUpdate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name); self.root = self.home / 'Jarvis-agents'; self.root.mkdir()
        entries = []; hunks = []
        for name in sorted(installer.ALLOWED):
            old = b'marker = 1\n' if name.endswith('.py') else b'var marker = 1;\n'
            new = old.replace(b'1', b'2')
            path = self.root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(old)
            entries.append({'path': name, 'before': installer.sha(old), 'after': installer.sha(new)})
            hunks.extend(difflib.unified_diff(old.decode().splitlines(True), new.decode().splitlines(True), fromfile='a/'+name, tofile='b/'+name))
        self.payload = ''.join(hunks).encode()
        self.manifest = {'format': 1, 'patch_sha256': installer.sha(self.payload), 'files': entries}
        self.config = self.home / '.jarvis-desktop/config.env'; self.config.parent.mkdir()
        self.config.write_text('VOICE_STT_LANGUAGE=es\nJARVIS_REPLY_LANGUAGE=en-GB\nOTHER_PRIVATE_VALUE=unchanged\nVOICE_STT_THREADS=4\n')

    def test_install_backup_config_and_idempotence(self):
        installer.install(self.root, self.manifest, self.payload, self.home)
        for entry in self.manifest['files']:
            self.assertEqual(installer.sha((self.root/entry['path']).read_bytes()), entry['after'])
        self.assertIn('VOICE_STT_LANGUAGE=auto', self.config.read_text())
        self.assertIn('OTHER_PRIVATE_VALUE=unchanged', self.config.read_text())
        self.assertIn('VOICE_STT_THREADS=4', self.config.read_text())
        backup = next((self.home/'.jarvis-desktop/update-backups').iterdir())
        self.assertEqual((backup/'desktop/app.py').read_bytes(), b'marker = 1\n')
        self.assertIn('ya está instalada', installer.install(self.root, self.manifest, self.payload, self.home))

    def test_unknown_edits_refused_without_changes(self):
        (self.root/'desktop/ui/app.js').write_text('custom = true;\n')
        with self.assertRaises(ValueError): installer.install(self.root, self.manifest, self.payload, self.home)
        self.assertEqual((self.root/'desktop/app.py').read_bytes(), b'marker = 1\n')
        self.assertFalse((self.home/'.jarvis-desktop/update-backups').exists())

    def test_symlink_refused_and_check_is_read_only(self):
        installer.install(self.root, self.manifest, self.payload, self.home, check=True)
        self.assertEqual((self.root/'desktop/app.py').read_bytes(), b'marker = 1\n')
        target = self.root/'desktop/ui/app.js'; target.unlink(); target.symlink_to(self.config)
        with self.assertRaises(ValueError): installer.prepare(self.root, self.manifest, self.payload)
        self.assertIn('VOICE_STT_LANGUAGE=es', self.config.read_text())

    def test_partial_write_failure_rolls_back(self):
        real = installer.atomic; failed = False
        def atomic(path, data, mode=0o600):
            nonlocal failed
            if path == self.root/'desktop/documentos.py' and not failed:
                failed = True; raise OSError('simulated disk failure')
            return real(path, data, mode)
        with patch.object(installer, 'atomic', side_effect=atomic):
            with self.assertRaises(OSError): installer.install(self.root, self.manifest, self.payload, self.home)
        for entry in self.manifest['files']:
            self.assertEqual(installer.sha((self.root/entry['path']).read_bytes()), entry['before'])
        self.assertIn('VOICE_STT_LANGUAGE=es', self.config.read_text())

    def test_duplicate_language_settings_refused_before_write(self):
        self.config.write_text('VOICE_STT_LANGUAGE=es\nVOICE_STT_LANGUAGE=en\n')
        with self.assertRaises(ValueError): installer.install(self.root, self.manifest, self.payload, self.home)
        self.assertFalse((self.home/'.jarvis-desktop/update-backups').exists())

if __name__ == '__main__': unittest.main()
