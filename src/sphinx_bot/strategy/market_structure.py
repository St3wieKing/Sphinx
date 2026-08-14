"""Causal swing, structure, ATR, consolidation, and regime detection."""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from itertools import pairwise
from statistics import mean

from ..config import InstrumentConfig, StructureConfig
from ..models import (
    Bar,
    Consolidation,
    Direction,
    Pivot,
    PivotKind,
    Regime,
    StructureLabel,
    StructureSnapshot,
)


def true_range(bar: Bar, previous_close: float | None) -> float:
    if previous_close is None:
        return bar.range
    return max(
        bar.high - bar.low,
        abs(bar.high - previous_close),
        abs(bar.low - previous_close),
    )


class RollingATR:
    """Simple rolling ATR whose value at t uses only completed bars through t."""

    def __init__(self, period: int) -> None:
        if period <= 0:
            raise ValueError("ATR period must be positive")
        self.period = period
        self.ranges: deque[float] = deque(maxlen=period)
        self.previous_close: float | None = None

    def update(self, bar: Bar) -> float | None:
        self.ranges.append(true_range(bar, self.previous_close))
        self.previous_close = bar.close
        return self.value

    @property
    def value(self) -> float | None:
        if len(self.ranges) < self.period:
            return None
        return mean(self.ranges)


class FixedPivotDetector:
    """Confirm a pivot only after `right` subsequent completed bars exist."""

    def __init__(self, left: int, right: int, method: str = "fixed") -> None:
        if left < 1 or right < 1:
            raise ValueError("pivot left/right windows must be positive")
        self.left = left
        self.right = right
        self.method = method
        self.window: deque[Bar] = deque(maxlen=left + right + 1)

    def update(self, bar: Bar) -> list[Pivot]:
        self.window.append(bar)
        if len(self.window) < self.window.maxlen:
            return []
        values = list(self.window)
        candidate = values[self.left]
        left = values[: self.left]
        right = values[self.left + 1 :]
        pivots: list[Pivot] = []
        # Strict on the older side and non-strict on the newer side resolves ties
        # deterministically and avoids emitting a run of equal pivots.
        if all(candidate.high > item.high for item in left) and all(
            candidate.high >= item.high for item in right
        ):
            pivots.append(
                Pivot(
                    kind=PivotKind.HIGH,
                    price=candidate.high,
                    occurred_at=candidate.timestamp,
                    confirmed_at=bar.timestamp,
                    method=self.method,
                )
            )
        if all(candidate.low < item.low for item in left) and all(
            candidate.low <= item.low for item in right
        ):
            pivots.append(
                Pivot(
                    kind=PivotKind.LOW,
                    price=candidate.low,
                    occurred_at=candidate.timestamp,
                    confirmed_at=bar.timestamp,
                    method=self.method,
                )
            )
        return pivots


class ReversalPivotDetector:
    """Online zig-zag using either an ATR or percentage reversal threshold."""

    def __init__(self, method: str, atr_multiplier: float, percentage: float) -> None:
        self.method = method
        self.atr_multiplier = atr_multiplier
        self.percentage = percentage
        self.candidate_high: Bar | None = None
        self.candidate_low: Bar | None = None
        self.seeking: PivotKind | None = None

    def update(self, bar: Bar, atr: float | None) -> list[Pivot]:
        if self.candidate_high is None:
            self.candidate_high = self.candidate_low = bar
            return []
        assert self.candidate_low is not None
        if bar.high >= self.candidate_high.high:
            self.candidate_high = bar
        if bar.low <= self.candidate_low.low:
            self.candidate_low = bar
        if self.method == "atr":
            if atr is None:
                return []
            threshold_high = threshold_low = atr * self.atr_multiplier
        else:
            threshold_high = self.candidate_high.high * self.percentage
            threshold_low = self.candidate_low.low * self.percentage
        pivots: list[Pivot] = []
        if self.seeking in (None, PivotKind.HIGH):
            if self.candidate_high.high - bar.low >= threshold_high:
                pivots.append(
                    Pivot(
                        PivotKind.HIGH,
                        self.candidate_high.high,
                        self.candidate_high.timestamp,
                        bar.timestamp,
                        self.method,
                    )
                )
                self.seeking = PivotKind.LOW
                self.candidate_low = bar
        elif self.candidate_low is not None and bar.high - self.candidate_low.low >= threshold_low:
            pivots.append(
                Pivot(
                    PivotKind.LOW,
                    self.candidate_low.low,
                    self.candidate_low.timestamp,
                    bar.timestamp,
                    self.method,
                )
            )
            self.seeking = PivotKind.HIGH
            self.candidate_high = bar
        return pivots


class MarketStructureEngine:
    def __init__(self, config: StructureConfig, instrument: InstrumentConfig) -> None:
        self.config = config
        self.instrument = instrument
        self.atr = RollingATR(config.atr_period)
        if config.method in {"fixed", "fractal"}:
            left = 2 if config.method == "fractal" else config.pivot_left_bars
            right = 2 if config.method == "fractal" else config.pivot_right_bars
            self.detector: FixedPivotDetector | ReversalPivotDetector = FixedPivotDetector(
                left, right, config.method
            )
        else:
            self.detector = ReversalPivotDetector(
                config.method,
                config.atr_reversal_multiplier,
                config.percentage_reversal,
            )
        self.highs: list[Pivot] = []
        self.lows: list[Pivot] = []
        self.bars: deque[Bar] = deque(maxlen=max(config.regime_lookback, config.atr_period * 3))
        self._last_bos_high_at = None
        self._last_bos_low_at = None
        self.trend: Direction | None = None

    def update(self, bar: Bar) -> tuple[StructureSnapshot, tuple[Pivot, ...]]:
        atr = self.atr.update(bar)
        self.bars.append(bar)
        if isinstance(self.detector, FixedPivotDetector):
            candidates = self.detector.update(bar)
        else:
            candidates = self.detector.update(bar, atr)
        labelled: list[Pivot] = []
        tolerance = self.config.equal_tolerance_ticks * self.instrument.tick_size
        for pivot in candidates:
            history = self.highs if pivot.kind is PivotKind.HIGH else self.lows
            label = None
            if history:
                difference = pivot.price - history[-1].price
                if pivot.kind is PivotKind.HIGH:
                    label = (
                        StructureLabel.EQUAL_HIGH
                        if abs(difference) <= tolerance
                        else StructureLabel.HIGHER_HIGH
                        if difference > 0
                        else StructureLabel.LOWER_HIGH
                    )
                else:
                    label = (
                        StructureLabel.EQUAL_LOW
                        if abs(difference) <= tolerance
                        else StructureLabel.HIGHER_LOW
                        if difference > 0
                        else StructureLabel.LOWER_LOW
                    )
            pivot = replace(pivot, label=label)
            history.append(pivot)
            labelled.append(pivot)

        bos: Direction | None = None
        shift: Direction | None = None
        if (
            self.highs
            and bar.close > self.highs[-1].price
            and self._last_bos_high_at != self.highs[-1].occurred_at
        ):
            bos = Direction.LONG
            shift = Direction.LONG if self.trend is Direction.SHORT else None
            self.trend = Direction.LONG
            self._last_bos_high_at = self.highs[-1].occurred_at
        if (
            self.lows
            and bar.close < self.lows[-1].price
            and self._last_bos_low_at != self.lows[-1].occurred_at
        ):
            bos = Direction.SHORT
            shift = Direction.SHORT if self.trend is Direction.LONG else None
            self.trend = Direction.SHORT
            self._last_bos_low_at = self.lows[-1].occurred_at
        snapshot = StructureSnapshot(
            timestamp=bar.timestamp,
            trend=self.trend,
            regime=self._regime(atr),
            latest_high=self.highs[-1] if self.highs else None,
            latest_low=self.lows[-1] if self.lows else None,
            break_of_structure=bos,
            market_structure_shift=shift,
        )
        return snapshot, tuple(labelled)

    def _regime(self, atr: float | None) -> Regime:
        lookback = self.config.regime_lookback
        if len(self.bars) < lookback:
            return Regime.UNKNOWN
        bars = list(self.bars)[-lookback:]
        displacement = abs(bars[-1].close - bars[0].close)
        path = sum(abs(current.close - previous.close) for previous, current in pairwise(bars))
        efficiency = displacement / path if path else 0.0
        recent_ranges = [item.range for item in bars[-max(3, lookback // 4) :]]
        older_ranges = [item.range for item in bars[: max(3, lookback // 2)]]
        if (
            older_ranges
            and mean(recent_ranges) > mean(older_ranges) * self.config.expansion_atr_ratio
        ):
            return Regime.EXPANSION
        if efficiency >= self.config.trend_efficiency_threshold:
            return Regime.TREND_UP if bars[-1].close > bars[0].close else Regime.TREND_DOWN
        return Regime.RANGE


def detect_consolidation(
    completed_bars: list[Bar], lookback: int, atr: float, max_atr_multiple: float
) -> Consolidation | None:
    """Inspect bars strictly before the candidate breakout bar."""

    if atr <= 0 or len(completed_bars) < lookback:
        return None
    window = completed_bars[-lookback:]
    low = min(bar.low for bar in window)
    high = max(bar.high for bar in window)
    if high - low > atr * max_atr_multiple:
        return None
    return Consolidation(window[0].timestamp, window[-1].timestamp, low, high, atr, lookback)
