"""Causal multi-timeframe aggregation.

An aggregate is emitted only when the first execution bar of the *next* bucket
arrives.  Therefore a strategy can never observe an unfinished higher-timeframe
bar. `flush()` is intentionally absent: end-of-file is not evidence that a live
bar had completed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ..models import Bar


@dataclass
class _Bucket:
    start: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    symbol: str


class CausalResampler:
    def __init__(self, target_seconds: int) -> None:
        if target_seconds <= 0:
            raise ValueError("target_seconds must be positive")
        self.target_seconds = target_seconds
        self._bucket: _Bucket | None = None

    def _bucket_start(self, timestamp: datetime) -> datetime:
        epoch = int(timestamp.timestamp())
        floored = epoch - (epoch % self.target_seconds)
        return datetime.fromtimestamp(floored, tz=UTC)

    def update(self, bar: Bar) -> Bar | None:
        start = self._bucket_start(bar.timestamp)
        completed: Bar | None = None
        if self._bucket is None:
            self._bucket = _Bucket(
                start, bar.open, bar.high, bar.low, bar.close, bar.volume, bar.symbol
            )
            return None
        if start < self._bucket.start:
            raise ValueError("resampler received out-of-order data")
        if start > self._bucket.start:
            current = self._bucket
            completed = Bar(
                timestamp=current.start,
                open=current.open,
                high=current.high,
                low=current.low,
                close=current.close,
                volume=current.volume,
                symbol=current.symbol,
                interval_seconds=self.target_seconds,
            )
            self._bucket = _Bucket(
                start, bar.open, bar.high, bar.low, bar.close, bar.volume, bar.symbol
            )
        else:
            self._bucket.high = max(self._bucket.high, bar.high)
            self._bucket.low = min(self._bucket.low, bar.low)
            self._bucket.close = bar.close
            self._bucket.volume += bar.volume
        return completed


class MultiTimeframeFeed:
    def __init__(self, intervals: tuple[int, ...]) -> None:
        self.resamplers = {seconds: CausalResampler(seconds) for seconds in intervals}

    def update(self, bar: Bar) -> dict[int, Bar]:
        completed: dict[int, Bar] = {}
        for seconds, resampler in self.resamplers.items():
            aggregate = resampler.update(bar)
            if aggregate is not None:
                completed[seconds] = aggregate
        return completed
