import importlib.util
from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import mac_service as service


class ServiceTests(unittest.TestCase):
    def test_plist_round_trip_preserves_paths_and_does_not_start_executor(self):
        definition = service.service_definition("/Users/Owner With Spaces")
        loaded = plistlib.loads(plistlib.dumps(definition))
        self.assertEqual(loaded["ProgramArguments"][0], "/Users/Owner With Spaces/.jarvis-control-venv/bin/python")
        self.assertEqual(loaded["ProgramArguments"][-1], "--launch")
        self.assertNotIn("--automatic", loaded["ProgramArguments"])
        self.assertTrue(loaded["KeepAlive"])

    def test_other_platform_never_calls_launchctl(self):
        with patch.object(service.sys, "platform", "linux"), patch.object(service, "invoke") as invoke:
            self.assertEqual(service.main(["start"]), 2)
            invoke.assert_not_called()

    def test_active_manual_panel_is_not_killed_or_replaced(self):
        from subprocess import CompletedProcess
        with patch.object(service.sys, "platform", "darwin"), patch.object(service, "invoke", return_value=CompletedProcess([], 1)) as invoke, patch.object(service.socket, "create_connection"), patch.object(service.mac_setup, "main") as setup:
            self.assertEqual(service.main(["start"]), 2)
            setup.assert_not_called()
            self.assertEqual(invoke.call_count, 1)

    def test_stop_disables_login_start(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            plist = home / "Library/LaunchAgents" / (service.LABEL + ".plist")
            plist.parent.mkdir(parents=True)
            plist.write_bytes(b"test")
            with patch.object(service.sys, "platform", "darwin"), patch.object(service.Path, "home", return_value=home), patch.object(service, "invoke", return_value=CompletedProcess([], 0)):
                self.assertEqual(service.main(["stop"]), 0)
            self.assertFalse(plist.exists())
            self.assertTrue(plist.with_suffix(".plist.disabled").exists())
