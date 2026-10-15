"""Fixed-page navigation never grants interaction or financial permissions."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'desktop'))
import account_navigation as nav
import intents

class Navigation(unittest.TestCase):
    def test_applications(self):
        for app in nav.APPS:
            self.assertEqual(intents.parse("abre " + app), ("application", app))
        self.assertEqual(intents.parse("abre Cap Cut"), ("application", "capcut"))
        self.assertNotEqual(intents.parse("abre Finder y borra todo")[0], "application")

    def test_application_launch(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {"JARVIS_CONTROL_DIR": directory}), patch.object(nav.sys, "platform", "darwin"), patch.object(nav.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.assertTrue(nav.open_application("capcut")["ok"])
            self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "-a", "CapCut"])
            run.reset_mock()
            Path(directory, "STOP").touch()
            self.assertFalse(nav.open_application("finder")["ok"])
            run.assert_not_called()

    def test_all_sites(self):
        for site in nav.SITES:
            with self.subTest(site=site):
                self.assertEqual(intents.parse('Abre ' + site), ('account', site))
    def test_aliases_and_language(self):
        for text, site in [('Jarvis, abre Chat GPT', 'chatgpt'), ('entra a mi correo', 'gmail'),
                           ('please open my Coinbase', 'coinbase'), ('abre YouTube Studio por favor', 'youtube studio')]:
            self.assertEqual(intents.parse(text), ('account', site))
    def test_no_compound_actions(self):
        for text in ['abre Coinbase y compra bitcoin', 'abre gmail y envia el correo',
                     'abre chatgpt y paga la suscripcion', 'abre instagram y borra todo',
                     'abre https://coinbase.com/transfer', 'abre coinbase.com.evil.test',
                     'no abras Coinbase', 'como puedo abrir Coinbase']:
            self.assertNotEqual(intents.parse(text)[0], 'account', text)
    def test_old_commands(self):
        self.assertEqual(intents.parse('abre Notas'), ('mouse', {'action':'open_app','app':'Notes'}))
        self.assertEqual(intents.parse('compra bitcoin')[0], 'refuse')
        self.assertEqual(intents.parse('/confirmar 123456')[0], 'refuse')
    def test_open_only_and_stop(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'JARVIS_CONTROL_DIR':directory}), \
             patch.object(nav.sys, 'platform', 'darwin'), patch.object(nav.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            result = nav.open_account('coinbase')
            self.assertTrue(result['ok'])
            self.assertIn('No he comprobado', result['message'])
            self.assertEqual(run.call_args.args[0], ['/usr/bin/open','-a','Safari','https://www.coinbase.com/'])
            run.reset_mock()
            Path(directory, 'STOP').touch()
            self.assertFalse(nav.open_account('gmail')['ok'])
            run.assert_not_called()
    def test_failed_and_unknown(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'JARVIS_CONTROL_DIR':directory}), \
             patch.object(nav.sys, 'platform', 'darwin'), patch.object(nav.subprocess, 'run', return_value=Mock(returncode=1)) as run:
            self.assertFalse(nav.open_account('gmail')['ok'])
            run.reset_mock()
            self.assertFalse(nav.open_account('https://evil.test')['ok'])
            run.assert_not_called()

if __name__ == '__main__':
    unittest.main()
