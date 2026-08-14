from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sphinx_bot.config import load_config
from sphinx_bot.data.csv_feed import read_bars
from sphinx_bot.data.importers import normalize_external_data
from sphinx_bot.research.deep import DeepResearchSuite
from sphinx_bot.research.synthetic import generate_synthetic_bars
from sphinx_bot.web.server import PINE_PATH, DashboardService

ROOT = Path(__file__).resolve().parents[2]


class DeepWebImportTests(unittest.TestCase):
    def test_external_one_minute_csv_normalizes_only_complete_buckets(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "external.csv"
            output = Path(directory) / "normalized.csv"
            source.write_text(
                "timestamp ET,open,high,low,close,volume\n"
                "2024-01-08 00:00:00,100,101,99,100.5,10\n"
                "2024-01-08 00:01:00,100.5,102,100,101.5,20\n"
                "2024-01-08 00:02:00,101.5,103,101,102.5,30\n",
                encoding="utf-8",
            )
            manifest = normalize_external_data(
                source,
                output,
                symbol="NQ",
                source_timezone="America/New_York",
                source_interval_seconds=60,
            )
            bars = read_bars(output)
            self.assertEqual(len(bars), 1)
            self.assertEqual(
                (bars[0].open, bars[0].high, bars[0].low, bars[0].close), (100, 102, 99, 101.5)
            )
            self.assertEqual(manifest["dropped_incomplete_source_rows"], 1)

    def test_deep_suite_keeps_holdout_locked(self):
        config = load_config(ROOT / "config/baseline.json")
        report = DeepResearchSuite(config, bootstrap_simulations=20).run(
            generate_synthetic_bars(days=4)
        )
        self.assertFalse(report["holdout"]["opened"])
        self.assertEqual(len(report["one_factor_sensitivity_on_development"]), 8)
        self.assertIn("execution_scenarios_on_validation", report)

    def test_dashboard_is_explicitly_demo_and_paper_only(self):
        service = DashboardService()
        overview = service.overview()
        self.assertEqual(overview["mode"], "PAPER / RESEARCH ONLY")
        self.assertEqual(overview["holdout_status"], "LOCKED")
        self.assertEqual(service.instrument("NQ")["data_mode"], "SYNTHETIC_ENGINEERING_DEMO")
        self.assertTrue(PINE_PATH.exists())

    def test_tradingview_webhook_is_receive_only_and_validated(self):
        with tempfile.TemporaryDirectory() as directory:
            log = Path(directory) / "webhooks.jsonl"
            with patch.dict("os.environ", {"SPHINX_WEBHOOK_TOKEN": "test-secret"}):
                service = DashboardService(webhook_log=log)
            event = service.accept_tradingview_alert(
                {
                    "side": "LONG",
                    "ticker": "MNQ1!",
                    "entry": 20000,
                    "stop": 19990,
                    "tp1": 20010,
                    "tp2": 20020,
                }
            )
            self.assertEqual(event["status"], "RECEIVED_NOT_ROUTED")
            self.assertEqual(event["symbol"], "MNQ")
            self.assertEqual(service.webhook_status()["received_this_run"], 1)
            self.assertTrue(log.exists())
            with self.assertRaisesRegex(ValueError, "ordering"):
                service.accept_tradingview_alert(
                    {
                        "side": "LONG",
                        "ticker": "NQ1!",
                        "entry": 20000,
                        "stop": 20010,
                        "tp1": 19990,
                        "tp2": 19980,
                    }
                )

    def test_packaged_pine_copy_matches_deliverable(self):
        deliverable = (ROOT / "tradingview/sphinx_signal_indicator.pine").read_text()
        packaged = (ROOT / "src/sphinx_bot/web/static/sphinx_signal_indicator.pine").read_text()
        self.assertEqual(deliverable, packaged)
        self.assertIn("//@version=6", deliverable)
        self.assertIn("alertcondition(longSignal", deliverable)
        self.assertIn("lookahead = barmerge.lookahead_on", deliverable)


if __name__ == "__main__":
    unittest.main()
