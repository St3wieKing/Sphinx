from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from sphinx_bot.config import load_config
from sphinx_bot.models import Bar, Direction
from sphinx_bot.strategy.rejection_block import KeyOpenRejectionBlockMachine


class KeyOpenRejectionBlockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = load_config("config/bryan_rejection_block_exp.json")
        self.machine = KeyOpenRejectionBlockMachine(self.config)
        self.start = datetime(2025, 1, 2, 5, 0, tzinfo=UTC)  # 00:00 New York

    def bar(self, minutes: int, open_: float, high: float, low: float, close: float) -> Bar:
        return Bar(
            self.start + timedelta(minutes=minutes),
            open_,
            high,
            low,
            close,
            100,
            "NQ",
            120,
        )

    def test_bearish_key_open_block_enters_only_on_later_midpoint_retest(self) -> None:
        first = self.machine.on_bar(self.bar(0, 100, 100.25, 99.5, 99.75))
        self.assertIsNone(first.plan)

        formation = self.machine.on_bar(self.bar(2, 99.5, 100.5, 99.0, 99.25))
        self.assertIsNone(formation.plan)
        self.assertTrue(
            any(d.event == "key_open_rejection_block_formed" for d in formation.decisions)
        )

        trigger = self.machine.on_bar(self.bar(4, 99.5, 100.0, 99.25, 99.75))
        self.assertIsNotNone(trigger.plan)
        assert trigger.plan is not None
        self.assertEqual(trigger.plan.direction, Direction.SHORT)
        self.assertEqual(trigger.plan.raw_entry, 100.0)
        self.assertEqual(trigger.plan.raw_stop, 100.75)
        self.assertEqual(trigger.plan.raw_target_2, 97.75)

    def test_tip_break_invalidates_before_ambiguous_midpoint_fill(self) -> None:
        self.machine.on_bar(self.bar(0, 100, 100.25, 99.5, 99.75))
        self.machine.on_bar(self.bar(2, 99.5, 100.5, 99.0, 99.25))
        step = self.machine.on_bar(self.bar(4, 99.5, 100.75, 99.25, 100.25))
        self.assertIsNone(step.plan)
        self.assertTrue(any(d.event == "rejection_block_invalidated" for d in step.decisions))


if __name__ == "__main__":
    unittest.main()
