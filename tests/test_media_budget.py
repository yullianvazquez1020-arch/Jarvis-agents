import asyncio
import sys
import unittest
from unittest.mock import patch
import jarvis_media_budget as budget


class MediaBudget(unittest.TestCase):
    def test_only_clean_inactive_cache_is_discounted(self):
        with patch.object(budget.Path, 'read_text', return_value='inactive_file 100\nfile_dirty 10\nfile_writeback 5\nactive_file 900\nanon 400\n'):
            self.assertEqual(budget.inactive_cache('/stat', 500), 85)

    def test_inconsistent_or_missing_counters_never_invent_headroom(self):
        for stat in ('inactive_file -1', 'inactive_file 501', 'inactive_file nope', 'anon 300', 'inactive_file 100\nfile_dirty -1'):
            with patch.object(budget.Path, 'read_text', return_value=stat):
                self.assertEqual(budget.inactive_cache('/stat', 500), 0)

    def test_v1_uses_hierarchical_cache_counter(self):
        with patch.object(budget.Path, 'read_text', return_value='total_inactive_file 120\ninactive_file 900\ntotal_writeback 20'):
            self.assertEqual(budget.inactive_cache('/stat', 500, True), 100)

    def test_effective_usage_preserves_limit_and_real_pressure(self):
        def read(path):
            name = path.name
            return {'memory.max':'512','memory.current':'480','memory.stat':'inactive_file 100\nfile_dirty 10'}[name]
        with patch.object(budget.Path, 'read_text', new=read):
            self.assertEqual(budget.memory_state(), (390, 512))

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
