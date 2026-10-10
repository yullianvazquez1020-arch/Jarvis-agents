import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("mac_setup", Path(__file__).parents[1] / "scripts/mac_setup.py")
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class SetupTests(unittest.TestCase):
    def test_prefers_pr_then_known_female_latin_voice(self):
        listing = "Juan es_MX # Hola\nPaulina es_MX # Hola\nMonica es_ES # Hola\n"
        self.assertEqual(setup.voice_choice(listing), ("Paulina", "es_MX"))
        self.assertEqual(setup.voice_choice(listing + "Voz PR es_PR # Hola\n"), ("Voz PR", "es_PR"))
        self.assertEqual(setup.voice_choice("Alex en_US # Hello"), ("", ""))

    def test_wrong_platform_never_installs_or_moves(self):
        with patch.object(setup.sys, "platform", "linux"), patch.object(setup.subprocess, "run") as run:
            self.assertEqual(setup.main(["--install", "--launch"]), 2)
            run.assert_not_called()

    def test_paths_with_spaces_are_separate_arguments(self):
        python = setup.python_path("/Users/A B")
        command = setup.launch_command(python)
        self.assertEqual(command[0], "/Users/A B/.jarvis-control-venv/bin/python")
        self.assertEqual(command[-1], "--hand-mouse")
        self.assertNotIn("shell", command)
