from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sphinx_bot.config import load_config
from sphinx_bot.data.csv_feed import read_bars
from sphinx_bot.models import Bar

ROOT = Path(__file__).resolve().parents[2]


class ConfigAndDataTests(unittest.TestCase):
    def test_baseline_config_is_valid_and_stable(self):
        config = load_config(ROOT / "config/baseline.json")
        self.assertTrue(config.paper_only)
        self.assertEqual(config.instrument.tick_size, 0.25)
        self.assertEqual(len(config.fingerprint), 64)

    def test_unknown_config_key_is_rejected(self):
        raw = json.loads((ROOT / "config/baseline.json").read_text())
        raw["risk"]["typo_limit"] = 1
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError, "unknown keys"):
                load_config(path)

    def test_incompatible_higher_timeframe_is_rejected(self):
        raw = json.loads((ROOT / "config/baseline.json").read_text())
        raw["timeframes"]["intermediate_seconds"] = [300]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad-timeframe.json"
            path.write_text(json.dumps(raw))
            with self.assertRaisesRegex(ValueError, "exact multiples"):
                load_config(path)

    def test_bar_requires_aware_timestamp_and_valid_ohlc(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            Bar(datetime(2024, 1, 1), 1, 2, 0, 1)  # noqa: DTZ001 — intentional
        with self.assertRaisesRegex(ValueError, "high"):
            Bar(datetime(2024, 1, 1, tzinfo=UTC), 1, 0, 0, 1)

    def test_csv_rejects_duplicate_timestamp(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bars.csv"
            path.write_text(
                "timestamp,open,high,low,close\n"
                "2024-01-01T00:00:00Z,1,2,0,1\n"
                "2024-01-01T00:00:00Z,1,2,0,1\n"
            )
            with self.assertRaisesRegex(ValueError, "duplicate/out of order"):
                read_bars(path)


if __name__ == "__main__":
    unittest.main()
