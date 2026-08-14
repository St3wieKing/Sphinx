"""Optional causal context confluences, including NQ/ES SMT divergence."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime

from ..models import Bar, Direction


@dataclass(frozen=True)
class SMTEvent:
    timestamp: datetime
    direction: Direction
    primary_level: float
    secondary_level: float
    lookback: int


class SMTDivergenceDetector:
    """Mechanical experimental proxy for visually identified SMT.

    Bullish: primary makes a lower rolling low while secondary does not.
    Bearish: primary makes a higher rolling high while secondary does not.
    Paired bars must share exactly the same completed-bar timestamp.
    """

    def __init__(self, lookback: int = 10) -> None:
        if lookback < 2:
            raise ValueError("SMT lookback must be at least two")
        self.lookback = lookback
        self.primary: deque[Bar] = deque(maxlen=lookback + 1)
        self.secondary: deque[Bar] = deque(maxlen=lookback + 1)

    def update(self, primary: Bar, secondary: Bar) -> SMTEvent | None:
        if primary.timestamp != secondary.timestamp:
            raise ValueError("SMT bars must be synchronized")
        event: SMTEvent | None = None
        if len(self.primary) >= self.lookback:
            primary_prior_low = min(bar.low for bar in self.primary)
            secondary_prior_low = min(bar.low for bar in self.secondary)
            primary_prior_high = max(bar.high for bar in self.primary)
            secondary_prior_high = max(bar.high for bar in self.secondary)
            bullish = primary.low < primary_prior_low and secondary.low >= secondary_prior_low
            bearish = primary.high > primary_prior_high and secondary.high <= secondary_prior_high
            # If both trigger on an outside bar, ambiguity means no SMT signal.
            if bullish != bearish:
                event = SMTEvent(
                    timestamp=primary.timestamp,
                    direction=Direction.LONG if bullish else Direction.SHORT,
                    primary_level=primary.low if bullish else primary.high,
                    secondary_level=secondary.low if bullish else secondary.high,
                    lookback=self.lookback,
                )
        self.primary.append(primary)
        self.secondary.append(secondary)
        return event
