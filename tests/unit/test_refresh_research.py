from __future__ import annotations

import unittest

from sphinx_bot.research.refresh import (
    _calibration_metrics,
    _fit_linear_logistic,
    _fit_platt,
    _wilson_lower,
)


class RefreshResearchTests(unittest.TestCase):
    def test_logistic_probabilities_are_finite_and_bounded(self):
        rows = [(float(index % 2), float(index) / 20) for index in range(20)]
        labels = [index % 2 for index in range(20)]
        model = _fit_linear_logistic(rows[:15], labels[:15])
        _fit_platt(model, rows[15:], labels[15:])
        probabilities = [model.predict(row) for row in rows]
        self.assertTrue(all(0 < probability < 1 for probability in probabilities))

    def test_calibration_reports_brier_and_base_rate_comparator(self):
        report = _calibration_metrics([0.2, 0.3, 0.7, 0.8], [0, 0, 1, 1])
        self.assertEqual(report["count"], 4)
        self.assertLess(report["brier"], report["base_rate_brier"])

    def test_wilson_lower_bound_is_conservative(self):
        self.assertLess(_wilson_lower(8, 10), 0.8)
        self.assertEqual(_wilson_lower(0, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
