"""Offline replay validation: no app, account, real network, or model imports."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'evaluation'))
import replay_paper_plan as hourly
import replay_minute as minute


def candles(start, end, step):
    return {s: [[t, 99, 101, 100, 100, 1] for t in range(start, end, step)]
            for s in hourly.plan.PRODUCTS}


class EvaluationInputs(unittest.TestCase):
    def setUp(self):
        engine = patch.object(hourly.plan, 'core', hourly.plan.core)
        engine.start()
        self.addCleanup(engine.stop)

    def test_valid_extra_period_is_trimmed_without_future_bars(self):
        data = candles(0, 7200, 60)
        index = hourly.data_index(data, 3600, 7200, 60)
        self.assertEqual(list(index['BTC-USD']), list(range(3600, 7200, 60)))

    def test_rejects_missing_product_bar_and_duplicates(self):
        base = candles(0, 120, 60)
        for change in ('product', 'bar', 'duplicate'):
            data = copy.deepcopy(base)
            if change == 'product':
                del data['ETH-USD']
            elif change == 'bar':
                data['BTC-USD'].pop()
            else:
                data['SOL-USD'].append(data['SOL-USD'][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                hourly.data_index(data, 0, 120, 60)

    def test_bad_cache_cannot_generate_report_or_trigger_redownload(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / 'bad.json'
            data = candles(0, 120, 60)
            data['BTC-USD'].pop()
            cache.write_text(json.dumps(data))
            original = cache.read_bytes()
            with patch.object(hourly, 'download') as download, self.assertRaises(ValueError):
                hourly.load_candles(cache, 0, 120, 60)
            download.assert_not_called()
            self.assertEqual(cache.read_bytes(), original)

    def test_rejects_malformed_and_impossible_prices(self):
        rows = [[], [0, 99, 101, 100, 100, -1], [0, 102, 101, 100, 100, 1],
                [0, 99, 101, 100, 500, 1], [1, 99, 101, 100, 100, 1],
                [0, 0, 101, 100, 100, 1], [0, 99, 101, float('nan'), 100, 1],
                [0, 99, 101, True, 100, 1], [0, 99, 101, '100', 100, 1]]
        for row in rows:
            with self.subTest(row=row), self.assertRaises(ValueError):
                hourly.candle_index([row], 0, 60, 60)

    def test_warmup_gap_rejected_before_engine_runs(self):
        data = candles(0, 61 * 3600, 3600)
        data['BTC-USD'].pop(12)
        with patch.object(hourly, 'make_core') as core, self.assertRaises(ValueError):
            hourly.replay(data, 60 * 3600, 61 * 3600)
        core.assert_not_called()

    def test_current_hour_close_is_not_a_signal(self):
        data = candles(0, 61 * 3600, 3600)
        before = hourly.replay(data, 60 * 3600, 61 * 3600)
        for rows in data.values():
            rows[-1][2] = 1000
            rows[-1][4] = 999
        self.assertEqual(hourly.replay(data, 60 * 3600, 61 * 3600), before)

    def test_clean_minute_run_fetches_its_own_hourly_warmup_and_reuses_cache(self):
        start, end = 60 * 3600, 61 * 3600
        fetched = []
        def download(symbol, begin, finish, granularity=3600):
            fetched.append((symbol, begin, finish, granularity))
            return candles(begin, finish, granularity)[symbol]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'evaluation').mkdir()
            (root / 'jarvis_paper_plan.py').write_bytes((ROOT / 'jarvis_paper_plan.py').read_bytes())
            with patch.object(minute, 'ROOT', root), patch.object(minute, 'start', start), \
                 patch.object(minute, 'end', end), patch.object(hourly, 'download', side_effect=download), \
                 patch('builtins.print'):
                minute.run()
                report = json.loads((root / 'evaluation/minute_results.json').read_text())
                self.assertEqual(len(fetched), 6)
                self.assertEqual(sum(x[3] == 3600 and x[1] == 0 for x in fetched), 3)
                self.assertTrue(report['validated_inputs'])
                self.assertEqual(set(report['samples_by_symbol'].values()), {60})
                self.assertEqual(len(report['hourly_data_sha256']), 64)
                minute.run()
                self.assertEqual(len(fetched), 6)
                self.assertEqual(json.loads((root / 'evaluation/minute_results.json').read_text()), report)


if __name__ == '__main__':
    unittest.main()
