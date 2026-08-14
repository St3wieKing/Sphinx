from __future__ import annotations

import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sphinx_bot.config import load_config
from sphinx_bot.models import Bar, Direction, Pivot, PivotKind, ZoneKind
from sphinx_bot.strategy.areas_of_interest import AreaOfInterestEngine
from sphinx_bot.strategy.context import SMTDivergenceDetector
from sphinx_bot.strategy.liquidity import LiquidityEngine

ROOT = Path(__file__).resolve().parents[2]
BASE = datetime(2024, 1, 8, 5, 0, tzinfo=UTC)


def make_bar(index: int, open_: float, high: float, low: float, close: float) -> Bar:
    return Bar(BASE + timedelta(minutes=2 * index), open_, high, low, close, 100, "NQ", 120)


class StrategyEngineTests(unittest.TestCase):
    def setUp(self):
        self.config = load_config(ROOT / "config/baseline.json")

    def test_fvg_is_created_on_third_bar_close_and_inverts_later(self):
        setup = replace(self.config.setup, fvg_min_ticks=1)
        engine = AreaOfInterestEngine(setup, self.config.instrument)
        self.assertEqual(engine.update(make_bar(0, 100, 101, 99, 100)), ())
        self.assertEqual(engine.update(make_bar(1, 101, 102, 100, 101)), ())
        created = engine.update(make_bar(2, 103, 104, 102, 103.5))
        self.assertEqual(len(created), 1)
        self.assertEqual(created[0].kind, ZoneKind.BULLISH_FVG)
        self.assertEqual((created[0].lower, created[0].upper), (101, 102))
        inverted = engine.update(make_bar(3, 102, 102.5, 100, 100.5))
        self.assertTrue(any(zone.kind is ZoneKind.BEARISH_IFVG for zone in inverted))

    def test_liquidity_level_cannot_sweep_on_confirmation_bar(self):
        engine = LiquidityEngine(self.config.liquidity, self.config.instrument)
        pivot = Pivot(PivotKind.HIGH, 105, BASE, BASE + timedelta(minutes=4), "fixed")
        level = engine.add_pivot(pivot)
        confirmation_bar = make_bar(2, 104, 107, 103, 104)
        self.assertEqual(engine.update(confirmation_bar), ())
        sweep_bar = make_bar(3, 104, 106, 103, 104)
        events = engine.update(sweep_bar)
        self.assertTrue(level.swept)
        self.assertIn("sweep_reclaim", {event.event for event in events})

    def test_equal_pivots_merge(self):
        engine = LiquidityEngine(self.config.liquidity, self.config.instrument)
        one = Pivot(PivotKind.HIGH, 105, BASE, BASE + timedelta(minutes=4), "fixed")
        two = Pivot(
            PivotKind.HIGH,
            105.5,
            BASE + timedelta(minutes=10),
            BASE + timedelta(minutes=14),
            "fixed",
        )
        first = engine.add_pivot(one)
        second = engine.add_pivot(two)
        self.assertIs(first, second)
        self.assertEqual(first.type, "equal_high")
        self.assertEqual(len(engine.levels), 1)

    def test_smt_proxy_is_synchronized_and_causal(self):
        detector = SMTDivergenceDetector(lookback=2)
        primary = [
            make_bar(0, 11, 12, 10, 11),
            make_bar(1, 10, 11, 9, 10),
            make_bar(2, 9, 10, 8, 9),
        ]
        secondary = [
            make_bar(0, 11, 12, 10, 11),
            make_bar(1, 10, 11, 9, 10),
            make_bar(2, 10, 11, 9, 10),
        ]
        self.assertIsNone(detector.update(primary[0], secondary[0]))
        self.assertIsNone(detector.update(primary[1], secondary[1]))
        event = detector.update(primary[2], secondary[2])
        self.assertIsNotNone(event)
        self.assertEqual(event.direction, Direction.LONG)


if __name__ == "__main__":
    unittest.main()
