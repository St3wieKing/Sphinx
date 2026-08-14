from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sphinx_bot.config import load_config
from sphinx_bot.models import Bar, Direction, StrategyState
from sphinx_bot.strategy.state_machine import ScrivStateMachine

ROOT = Path(__file__).resolve().parents[2]
BASE = datetime(2024, 1, 8, 5, 0, tzinfo=UTC)  # midnight New York


def make(index: int, open_: float, high: float, low: float, close: float) -> Bar:
    return Bar(BASE + timedelta(minutes=2 * index), open_, high, low, close, 100, "NQ", 120)


def test_config():
    config = load_config(ROOT / "config/baseline.json")
    return replace(
        config,
        session=replace(config.session, warmup_bars=5),
        structure=replace(config.structure, atr_period=3, pivot_left_bars=2, pivot_right_bars=2),
        setup=replace(
            config.setup,
            consolidation_lookback=5,
            consolidation_max_atr=2.0,
            displacement_min_atr=0.8,
            max_retrace_bars=5,
        ),
    )


class StateMachineTests(unittest.TestCase):
    def _warm_and_break(self, machine: ScrivStateMachine):
        for index in range(8):
            machine.on_bar(make(index, 100, 101, 99, 100))
        step = machine.on_bar(make(8, 100, 104.5, 99.5, 104))
        self.assertEqual(machine.state, StrategyState.TRACKING_IMPULSE)
        self.assertTrue(any(item.event == "displacement_breakout" for item in step.decisions))

    def test_evolving_midpoint_produces_plan(self):
        machine = ScrivStateMachine(test_config())
        self._warm_and_break(machine)
        extension = machine.on_bar(make(9, 104, 106, 102.5, 105))
        self.assertIsNone(extension.plan)
        self.assertAlmostEqual(machine.impulse.midpoint, 102.5)
        retrace = machine.on_bar(make(10, 105, 105, 102, 104))
        self.assertIsNotNone(retrace.plan)
        plan = retrace.plan
        self.assertEqual(plan.direction, Direction.LONG)
        self.assertAlmostEqual(plan.raw_entry, 102.5)
        self.assertLess(plan.raw_stop, plan.raw_entry)
        self.assertGreater(plan.raw_target_2, plan.raw_entry)
        self.assertEqual(machine.state, StrategyState.ENTRY_READY)

    def test_same_bar_new_extreme_does_not_rewrite_known_entry(self):
        machine = ScrivStateMachine(test_config())
        self._warm_and_break(machine)
        # The known midpoint before this bar is (99 + 104.5)/2 = 101.75.
        # This bar also makes 108, but that new high may not retroactively move
        # the standing trigger to 103.5.
        step = machine.on_bar(make(9, 104, 108, 101, 107))
        self.assertIsNotNone(step.plan)
        self.assertAlmostEqual(step.plan.raw_entry, 101.75)
        self.assertAlmostEqual(step.plan.impulse_extreme, 104.5)


if __name__ == "__main__":
    unittest.main()
