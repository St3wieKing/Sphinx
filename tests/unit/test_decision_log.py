from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from sphinx_bot.monitoring.audit import verify_chain
from sphinx_bot.monitoring.decision_log import TradeDecisionLogger, TradeDecisionRecord


class DecisionLogTests(unittest.TestCase):
    def record(self, **changes):
        values = {
            "timestamp": datetime(2025, 1, 1, tzinfo=UTC),
            "instrument": "NQ",
            "status": "REJECTED",
            "market_regime": "range",
            "higher_timeframe_bias": None,
            "liquidity_setup": "pivot_sweep",
            "liquidity_score": 0.4,
            "rejection_model": "A_BASIC_REJECTION",
            "rejection_details": {"wick_atr": 0.5},
            "setup_type": "refresh_event",
            "entry_reasons": ("sweep reclaimed",),
            "feature_values": {"wick_atr": 0.5},
            "target_probabilities": {"1R": 0.45},
            "probability_uncertainty": {"wilson_lower_90": 0.40},
            "candidate_targets": {"1R": {"expected_value_r": -0.1}},
            "selected_target": None,
            "expected_value_r": -0.1,
            "stop_price": 20000.0,
            "stop_logic": "one tick beyond sweep",
            "expected_entry": 20001.0,
        }
        values.update(changes)
        return TradeDecisionRecord(**values)

    def test_rejected_decision_is_hash_chained(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "decisions.jsonl"
            logger = TradeDecisionLogger(path)
            logger.write(self.record())
            self.assertEqual(verify_chain(path), (True, 1, None))

    def test_invalid_probability_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "probabilities"):
            self.record(target_probabilities={"1R": 1.2}).validate()


if __name__ == "__main__":
    unittest.main()
