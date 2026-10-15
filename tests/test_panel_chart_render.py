from pathlib import Path
import subprocess
import unittest

class ChartRenderTests(unittest.TestCase):
    def test_density_resize_and_canvas_reuse(self):
        subprocess.run(['node', str(Path(__file__).parents[1] / 'scripts/check_panel_charts.cjs')], check=True)
