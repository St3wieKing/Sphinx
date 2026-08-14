"""Detailed research-decision records for future validated paper candidates.

No record authorizes execution.  The schema exists so rejected, skipped, and
paper decisions can be analyzed with the same fields instead of logging winners
only.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .audit import AuditLogger


@dataclass(frozen=True)
class TradeDecisionRecord:
    timestamp: datetime
    instrument: str
    status: str
    market_regime: str
    higher_timeframe_bias: str | None
    liquidity_setup: str | None
    liquidity_score: float | None
    rejection_model: str | None
    rejection_details: dict[str, Any]
    setup_type: str
    entry_reasons: tuple[str, ...]
    feature_values: dict[str, float]
    target_probabilities: dict[str, float]
    probability_uncertainty: dict[str, Any]
    candidate_targets: dict[str, dict[str, float]]
    selected_target: str | None
    expected_value_r: float | None
    stop_price: float | None
    stop_logic: str | None
    expected_entry: float | None
    actual_entry: float | None = None
    slippage_ticks: float | None = None
    exit_reason: str | None = None
    actual_r: float | None = None
    maximum_favorable_excursion: float | None = None
    maximum_adverse_excursion: float | None = None
    notes: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("decision timestamp must be timezone-aware")
        if self.status not in {"REJECTED", "SKIPPED", "PAPER_APPROVED", "PAPER_CLOSED"}:
            raise ValueError("unsupported decision status")
        if not self.instrument or not self.setup_type:
            raise ValueError("instrument and setup_type are required")
        probabilities = list(self.target_probabilities.values())
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in probabilities):
            raise ValueError("target probabilities must be finite values in [0,1]")
        numeric_optional = (
            self.liquidity_score,
            self.expected_value_r,
            self.stop_price,
            self.expected_entry,
            self.actual_entry,
            self.slippage_ticks,
            self.actual_r,
            self.maximum_favorable_excursion,
            self.maximum_adverse_excursion,
        )
        if any(value is not None and not math.isfinite(value) for value in numeric_optional):
            raise ValueError("numeric decision fields must be finite")
        if self.status.startswith("PAPER") and self.selected_target is None:
            raise ValueError("paper decisions require a selected target")

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        payload = asdict(self)
        payload["timestamp"] = self.timestamp.isoformat()
        return payload


class TradeDecisionLogger:
    def __init__(self, path: str | Path) -> None:
        self.audit = AuditLogger(path)

    def write(self, decision: TradeDecisionRecord) -> dict[str, Any]:
        return self.audit.write("trade_decision", decision.to_dict())
