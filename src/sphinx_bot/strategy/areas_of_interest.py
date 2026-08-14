"""Deterministic FVG/IFVG and dealing-range areas.

FVGs are contextual in the baseline because the primary source explicitly calls
them discretionary confluence rather than the core 50% entry rule.
"""

from __future__ import annotations

import hashlib
from collections import deque

from ..config import InstrumentConfig, SetupConfig
from ..models import AreaOfInterest, Bar, Pivot, ZoneKind


class AreaOfInterestEngine:
    def __init__(
        self, config: SetupConfig, instrument: InstrumentConfig, timeframe: str = "2m"
    ) -> None:
        self.config = config
        self.instrument = instrument
        self.timeframe = timeframe
        self.bars: deque[Bar] = deque(maxlen=3)
        self.zones: list[AreaOfInterest] = []
        self._inverted: set[str] = set()

    @staticmethod
    def _id(kind: ZoneKind, bar: Bar, lower: float, upper: float) -> str:
        return hashlib.sha1(
            f"{kind.value}|{bar.timestamp.isoformat()}|{lower:.10f}|{upper:.10f}".encode()
        ).hexdigest()[:16]

    def update(self, bar: Bar) -> tuple[AreaOfInterest, ...]:
        created: list[AreaOfInterest] = []
        minimum = self.config.fvg_min_ticks * self.instrument.tick_size
        for zone in list(self.zones):
            zone.age_bars += 1
            if zone.invalidated or zone.created_at >= bar.timestamp:
                continue
            if zone.kind in {ZoneKind.BULLISH_FVG, ZoneKind.BULLISH_IFVG}:
                if bar.low <= zone.upper:
                    zone.interactions += 1
                    zone.partially_filled = True
                    penetration = max(0.0, zone.upper - max(bar.low, zone.lower))
                    zone.fill_fraction = min(1.0, penetration / (zone.upper - zone.lower))
                if bar.low <= zone.lower:
                    zone.fully_mitigated = True
                if bar.close < zone.lower:
                    zone.invalidated = True
                    inverse_kind = (
                        ZoneKind.BEARISH_IFVG if zone.kind is ZoneKind.BULLISH_FVG else None
                    )
                else:
                    inverse_kind = None
            elif zone.kind in {ZoneKind.BEARISH_FVG, ZoneKind.BEARISH_IFVG}:
                if bar.high >= zone.lower:
                    zone.interactions += 1
                    zone.partially_filled = True
                    penetration = max(0.0, min(bar.high, zone.upper) - zone.lower)
                    zone.fill_fraction = min(1.0, penetration / (zone.upper - zone.lower))
                if bar.high >= zone.upper:
                    zone.fully_mitigated = True
                if bar.close > zone.upper:
                    zone.invalidated = True
                    inverse_kind = (
                        ZoneKind.BULLISH_IFVG if zone.kind is ZoneKind.BEARISH_FVG else None
                    )
                else:
                    inverse_kind = None
            else:
                inverse_kind = None
            zone.confluence_score = self._quality(
                zone.lower,
                zone.upper,
                zone.age_bars,
                zone.fill_fraction,
                zone.interactions,
            )
            if inverse_kind is not None and zone.id not in self._inverted:
                inverse = AreaOfInterest(
                    id=self._id(inverse_kind, bar, zone.lower, zone.upper),
                    kind=inverse_kind,
                    lower=zone.lower,
                    upper=zone.upper,
                    midpoint=(zone.lower + zone.upper) / 2,
                    timeframe=zone.timeframe,
                    created_at=bar.timestamp,
                    confirmed_at=bar.timestamp,
                    confluence_score=self._quality(zone.lower, zone.upper, 0, 0.0, 0),
                )
                self._inverted.add(zone.id)
                self.zones.append(inverse)
                created.append(inverse)

        self.bars.append(bar)
        if len(self.bars) == 3:
            first, _, third = self.bars
            if third.low - first.high >= minimum:
                created.append(self._new_zone(ZoneKind.BULLISH_FVG, first.high, third.low, third))
            if first.low - third.high >= minimum:
                created.append(self._new_zone(ZoneKind.BEARISH_FVG, third.high, first.low, third))
        self.zones.extend(zone for zone in created if zone not in self.zones)
        self.zones = [zone for zone in self.zones if zone.age_bars <= self.config.max_aoi_age_bars]
        return tuple(created)

    def _quality(
        self,
        lower: float,
        upper: float,
        age_bars: int,
        fill_fraction: float,
        interactions: int,
    ) -> float:
        width_ticks = (upper - lower) / self.instrument.tick_size
        components = {
            "displacement": min(1.0, width_ticks / max(self.config.fvg_min_ticks * 4, 1)),
            "freshness": max(0.0, 1.0 - age_bars / self.config.max_aoi_age_bars),
            "mitigation": max(0.0, 1.0 - fill_fraction),
            "interactions": 1.0 / (1.0 + interactions),
        }
        weights = self.config.aoi_score_weights
        denominator = sum(weights.get(name, 0.0) for name in components) or 1.0
        return round(
            sum(weights.get(name, 0.0) * value for name, value in components.items()) / denominator,
            6,
        )

    def _new_zone(self, kind: ZoneKind, lower: float, upper: float, bar: Bar) -> AreaOfInterest:
        return AreaOfInterest(
            id=self._id(kind, bar, lower, upper),
            kind=kind,
            lower=lower,
            upper=upper,
            midpoint=(lower + upper) / 2,
            timeframe=self.timeframe,
            created_at=bar.timestamp,
            confirmed_at=bar.timestamp,
            confluence_score=self._quality(lower, upper, 0, 0.0, 0),
        )

    def active_at(self, price: float, bullish: bool | None = None) -> list[AreaOfInterest]:
        allowed = (
            {ZoneKind.BULLISH_FVG, ZoneKind.BULLISH_IFVG}
            if bullish is True
            else {ZoneKind.BEARISH_FVG, ZoneKind.BEARISH_IFVG}
            if bullish is False
            else set(ZoneKind)
        )
        return [
            zone
            for zone in self.zones
            if zone.kind in allowed and not zone.invalidated and zone.lower <= price <= zone.upper
        ]


def dealing_range(latest_high: Pivot | None, latest_low: Pivot | None) -> AreaOfInterest | None:
    if latest_high is None or latest_low is None:
        return None
    lower = latest_low.price
    upper = latest_high.price
    if lower >= upper:
        return None
    confirmed = max(latest_low.confirmed_at, latest_high.confirmed_at)
    occurred = max(latest_low.occurred_at, latest_high.occurred_at)
    return AreaOfInterest(
        id=hashlib.sha1(f"range|{lower}|{upper}|{confirmed.isoformat()}".encode()).hexdigest()[:16],
        kind=ZoneKind.DEALING_RANGE,
        lower=lower,
        upper=upper,
        midpoint=(lower + upper) / 2,
        timeframe="structure",
        created_at=occurred,
        confirmed_at=confirmed,
        confluence_score=0.5,
    )
