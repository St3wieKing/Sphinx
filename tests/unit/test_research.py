from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sphinx_bot.data.split import chronological_split
from sphinx_bot.models import Bar, Direction, ExitReason, Regime, Trade
from sphinx_bot.monitoring.audit import AuditLogger, verify_chain
from sphinx_bot.research.experiments import ExperimentLedger
from sphinx_bot.research.metrics import performance_metrics
from sphinx_bot.research.monte_carlo import MonteCarloConfig, run_monte_carlo

NOW = datetime(2024, 1, 1, tzinfo=UTC)


def trade(index: int, pnl: float) -> Trade:
    return Trade(
        signal_id=str(index),
        direction=Direction.LONG if index % 2 == 0 else Direction.SHORT,
        quantity=1,
        entry_time=NOW + timedelta(days=index),
        exit_time=NOW + timedelta(days=index, minutes=10),
        entry_price=100,
        average_exit_price=100 + pnl / 20,
        gross_pnl=pnl + 10,
        execution_costs=5,
        fees=5,
        costs=10,
        net_pnl=pnl,
        exit_reason=ExitReason.TARGET if pnl > 0 else ExitReason.STOP,
        mae_points=1,
        mfe_points=2,
        duration_seconds=600,
        regime=Regime.RANGE,
    )


class ResearchTests(unittest.TestCase):
    def test_holdout_is_locked_twice(self):
        bars = [Bar(NOW + timedelta(minutes=2 * i), 1, 2, 0, 1, 1, "NQ", 120) for i in range(10)]
        split = chronological_split(bars, 0.6, 0.2, 0.2)
        with self.assertRaises(PermissionError):
            split.get("holdout", strategy_frozen=False, allow_holdout=True)
        with self.assertRaises(PermissionError):
            split.get("holdout", strategy_frozen=True, allow_holdout=False)
        self.assertEqual(len(split.get("holdout", strategy_frozen=True, allow_holdout=True)), 2)

    def test_metrics_expectancy_and_cost_separation(self):
        trades = [trade(0, 100), trade(1, -50)]
        curve = [
            (NOW, 100_000),
            (NOW + timedelta(days=1), 100_100),
            (NOW + timedelta(days=2), 100_050),
        ]
        metrics = performance_metrics(trades, 100_000, curve)
        self.assertEqual(metrics["expectancy_per_trade"], 25)
        self.assertEqual(metrics["expectancy_formula"], 25)
        self.assertEqual(metrics["total_costs"], 20)
        self.assertEqual(metrics["profit_factor"], 2)

    def test_monte_carlo_is_reproducible(self):
        trades = [trade(index, 100 if index % 2 == 0 else -50) for index in range(10)]
        config = MonteCarloConfig(simulations=100, seed=7)
        one = run_monte_carlo(
            trades, initial_equity=100_000, tick_size=0.25, point_value=20, config=config
        )
        two = run_monte_carlo(
            trades, initial_equity=100_000, tick_size=0.25, point_value=20, config=config
        )
        self.assertEqual(one, two)

    def test_audit_chain_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.jsonl"
            audit = AuditLogger(path)
            audit.write("one", {"value": 1})
            audit.write("two", {"value": 2})
            self.assertEqual(verify_chain(path), (True, 2, None))
            content = path.read_text().replace('"value": 1', '"value": 9')
            path.write_text(content)
            valid, _, _ = verify_chain(path)
            self.assertFalse(valid)

    def test_ledger_refuses_unfrozen_holdout(self):
        with tempfile.TemporaryDirectory() as directory:
            ledger = ExperimentLedger(Path(directory) / "ledger.jsonl")
            with self.assertRaises(PermissionError):
                ledger.append(
                    experiment_id="x",
                    hypothesis="a test",
                    parameters_changed={},
                    reason="research",
                    config_fingerprint="abc",
                    holdout_result={"pnl": 1},
                    strategy_frozen_before_holdout=False,
                )


if __name__ == "__main__":
    unittest.main()
