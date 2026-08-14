from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from sphinx_bot.config import load_config
from sphinx_bot.execution.paper_trader import PaperTrader
from sphinx_bot.monitoring.audit import AuditLogger, verify_chain
from sphinx_bot.research.backtest import BacktestEngine
from sphinx_bot.research.stress import run_execution_scenarios
from sphinx_bot.research.synthetic import generate_synthetic_bars

ROOT = Path(__file__).resolve().parents[2]


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / "config/baseline.json")
        self.bars = generate_synthetic_bars(days=4)

    def test_backtest_and_audit_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            result = BacktestEngine(self.config, AuditLogger(path)).run(self.bars)
            self.assertEqual(len(result.equity_curve), len(self.bars))
            self.assertIn("net_pnl_after_costs", result.metrics)
            valid, count, error = verify_chain(path)
            self.assertTrue(valid, error)
            self.assertGreater(count, 2)

    def test_execution_scenarios_keep_strategy_but_change_fingerprint(self):
        results = run_execution_scenarios(self.config, self.bars)
        self.assertEqual(set(results), {"optimistic", "base", "pessimistic"})
        self.assertEqual(len({result.config_fingerprint for result in results.values()}), 3)

    def test_paper_replay_writes_persistent_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            trader = PaperTrader(self.config, directory)
            result = trader.replay(self.bars)
            self.assertTrue((trader.run_directory / "audit.jsonl").exists())
            self.assertTrue((trader.run_directory / "summary.json").exists())
            self.assertTrue((trader.run_directory / "config.snapshot.json").exists())
            self.assertIn("trade_count", result.metrics)


if __name__ == "__main__":
    unittest.main()
