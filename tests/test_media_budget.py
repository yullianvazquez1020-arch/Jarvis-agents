import asyncio
import sys
import unittest
from unittest.mock import patch
import jarvis_media_budget as budget


class MediaBudget(unittest.TestCase):
    def test_refuses_start_when_container_has_little_headroom(self):
        with patch.object(budget, 'memory_state', return_value=(450 * budget.MIB, 512 * budget.MIB)):
            with self.assertRaises(ValueError):
                budget.check_start()

    def test_unavailable_or_unlimited_cgroup_does_not_invent_a_limit(self):
        with patch.object(budget.Path, 'read_text', side_effect=OSError):
            self.assertIsNone(budget.memory_state())
        with patch.object(budget.Path, 'read_text', return_value='max'):
            self.assertIsNone(budget.memory_state())

    def test_pressure_kills_and_reaps_actual_child(self):
        async def run():
            proc = await asyncio.create_subprocess_exec(sys.executable, '-c', 'import time; time.sleep(10)',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            with patch.object(budget, 'memory_state', return_value=(460 * budget.MIB, 512 * budget.MIB)):
                with self.assertRaises(ValueError):
                    await budget.communicate(proc, None, 3)
            self.assertIsNotNone(proc.returncode)
        asyncio.run(run())

    def test_timeout_reaps_child_and_preserves_timeout(self):
        async def run():
            proc = await asyncio.create_subprocess_exec(sys.executable, '-c', 'import time; time.sleep(10)',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            with patch.object(budget, 'memory_state', return_value=None):
                with self.assertRaises(asyncio.TimeoutError):
                    await budget.communicate(proc, None, 0.05)
            self.assertIsNotNone(proc.returncode)
        asyncio.run(run())

    def test_success_returns_output_without_killing_worker(self):
        async def run():
            proc = await asyncio.create_subprocess_exec(sys.executable, '-c', 'print("ready")',
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            with patch.object(budget, 'memory_state', return_value=(100 * budget.MIB, 512 * budget.MIB)):
                output, _ = await budget.communicate(proc, None, 3)
            self.assertEqual(output.strip(), b'ready')
            self.assertEqual(proc.returncode, 0)
        asyncio.run(run())
