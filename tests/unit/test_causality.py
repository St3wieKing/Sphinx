from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from sphinx_bot.data.resample import CausalResampler
from sphinx_bot.models import Bar, PivotKind
from sphinx_bot.strategy.market_structure import FixedPivotDetector


def bar(index: int, high: float, low: float, close: float | None = None) -> Bar:
    timestamp = datetime(2024, 1, 1, tzinfo=UTC) + timedelta(minutes=2 * index)
    close = (high + low) / 2 if close is None else close
    return Bar(timestamp, close, high, low, close, 1, "NQ", 120)


class CausalityTests(unittest.TestCase):
    def test_pivot_is_emitted_only_after_right_window(self):
        detector = FixedPivotDetector(left=2, right=2)
        values = [bar(0, 2, 0), bar(1, 3, 0), bar(2, 8, 1), bar(3, 4, 0), bar(4, 3, 0)]
        for item in values[:-1]:
            self.assertEqual(detector.update(item), [])
        pivots = detector.update(values[-1])
        high = next(pivot for pivot in pivots if pivot.kind is PivotKind.HIGH)
        self.assertEqual(high.occurred_at, values[2].timestamp)
        self.assertEqual(high.confirmed_at, values[4].timestamp)

    def test_resampler_does_not_emit_open_bucket(self):
        resampler = CausalResampler(300)
        first = Bar(datetime(2024, 1, 1, 0, 0, tzinfo=UTC), 1, 2, 0, 1.5, 10, "NQ", 120)
        second = Bar(datetime(2024, 1, 1, 0, 2, tzinfo=UTC), 1.5, 3, 1, 2.5, 20, "NQ", 120)
        next_bucket = Bar(datetime(2024, 1, 1, 0, 6, tzinfo=UTC), 2.5, 4, 2, 3, 5, "NQ", 120)
        self.assertIsNone(resampler.update(first))
        self.assertIsNone(resampler.update(second))
        completed = resampler.update(next_bucket)
        self.assertIsNotNone(completed)
        self.assertEqual(completed.timestamp, first.timestamp)
        self.assertEqual(completed.high, 3)
        self.assertEqual(completed.volume, 30)


if __name__ == "__main__":
    unittest.main()
