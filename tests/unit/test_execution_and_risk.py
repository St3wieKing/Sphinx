from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

from sphinx_bot.config import load_config
from sphinx_bot.execution.simulator import PaperBroker
from sphinx_bot.models import (
    Bar,
    Direction,
    ExitReason,
    KillReason,
    Regime,
    SetupPlan,
    StrategyState,
    Trade,
)
from sphinx_bot.research.backtest import BacktestEngine
from sphinx_bot.risk.manager import RiskManager

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2024, 1, 8, 5, 0, tzinfo=UTC)


def plan() -> SetupPlan:
    return SetupPlan(
        signal_id="signal",
        created_at=NOW,
        direction=Direction.LONG,
        raw_entry=100,
        raw_stop=90,
        raw_target_1=110,
        raw_target_2=120,
        setup_score=80,
        passed_conditions=["test"],
        failed_conditions=[],
        evidence={},
        impulse_origin=90,
        impulse_extreme=110,
    )


class ExecutionAndRiskTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / "config/baseline.json")

    def test_same_bar_stop_wins_over_target(self):
        broker = PaperBroker(self.config)
        broker.open(plan(), 2, NOW)
        bar = Bar(NOW + timedelta(minutes=2), 100, 121, 89, 110, 100, "NQ", 120)
        trade = broker.process_bar(bar)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.exit_reason, ExitReason.STOP)
        self.assertAlmostEqual(trade.gross_pnl, -400)
        self.assertGreater(trade.costs, 0)
        self.assertLess(trade.net_pnl, trade.gross_pnl)

    def test_partial_moves_stop_and_conservative_same_bar_be(self):
        broker = PaperBroker(self.config)
        broker.open(plan(), 2, NOW)
        bar = Bar(NOW + timedelta(minutes=2), 101, 111, 99, 105, 100, "NQ", 120)
        trade = broker.process_bar(bar)
        self.assertIsNotNone(trade)
        self.assertEqual(trade.exit_reason, ExitReason.STOP)
        self.assertAlmostEqual(trade.gross_pnl, 200)
        self.assertEqual(len(trade.fills), 3)

    def test_internal_risk_rejection_is_not_counted_as_broker_rejection(self):
        engine = BacktestEngine(self.config)
        machine = MagicMock()
        machine.state = StrategyState.ENTRY_READY
        risk = MagicMock()
        decisions = []
        bar = Bar(NOW, 100, 101, 99, 100, 100, "NQ", 120)

        engine._reject_entry(
            machine,
            risk,
            plan(),
            bar,
            ("maximum trades per session reached",),
            decisions,
        )

        risk.record_rejection.assert_not_called()
        machine.notify_entry_rejected.assert_called_once_with()
        self.assertEqual(decisions[0].event, "risk_rejected_entry")

    def test_position_size_includes_costs_and_never_uses_score(self):
        risk = RiskManager(self.config)
        low_score = plan()
        high_score = replace(low_score, setup_score=100)
        first = risk.position_size(low_score)
        second = risk.position_size(high_score)
        self.assertEqual(first, second)
        self.assertEqual(first[0], 1)
        self.assertLessEqual(first[2], first[1])

    def test_daily_loss_kill_resets_only_on_new_session(self):
        risk = RiskManager(self.config)
        risk.reset_session(NOW.date(), NOW)
        losing = Trade(
            signal_id="loss",
            direction=Direction.LONG,
            quantity=1,
            entry_time=NOW,
            exit_time=NOW + timedelta(minutes=2),
            entry_price=100,
            average_exit_price=40,
            gross_pnl=-1200,
            execution_costs=0,
            fees=0,
            costs=0,
            net_pnl=-1200,
            exit_reason=ExitReason.STOP,
            mae_points=60,
            mfe_points=0,
            duration_seconds=120,
            regime=Regime.RANGE,
        )
        risk.record_trade(losing)
        self.assertTrue(risk.disabled)
        risk.reset_session((NOW + timedelta(days=1)).date(), NOW + timedelta(days=1))
        self.assertFalse(risk.disabled)

    def test_weekly_loss_kill_persists_until_new_iso_week(self):
        risk = RiskManager(self.config)
        risk.reset_session(NOW.date(), NOW)
        risk.mark_to_market(NOW, -2600)
        self.assertIn(KillReason.WEEKLY_LOSS_LIMIT, risk.kills)
        next_day = NOW + timedelta(days=1)
        risk.reset_session(next_day.date(), next_day)
        self.assertIn(KillReason.WEEKLY_LOSS_LIMIT, risk.kills)
        next_week = NOW + timedelta(days=7)
        risk.reset_session(next_week.date(), next_week)
        self.assertNotIn(KillReason.WEEKLY_LOSS_LIMIT, risk.kills)


if __name__ == "__main__":
    unittest.main()
