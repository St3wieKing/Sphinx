"""Causal liquidity map with explicit lifecycle and target ranking."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime

from ..config import InstrumentConfig, LiquidityConfig
from ..models import (
    Bar,
    Direction,
    LiquidityLevel,
    LiquidityScope,
    LiquiditySide,
    Pivot,
    PivotKind,
)


@dataclass(frozen=True)
class LiquidityEvent:
    timestamp: datetime
    level_id: str
    event: str
    price: float
    direction: Direction | None


class LiquidityEngine:
    def __init__(self, config: LiquidityConfig, instrument: InstrumentConfig) -> None:
        self.config = config
        self.instrument = instrument
        self.levels: list[LiquidityLevel] = []
        self.events: list[LiquidityEvent] = []
        self._bar_index = 0
        self._created_index: dict[str, int] = {}
        self._pending_sweeps: dict[str, tuple[int, Direction]] = {}

    def _id(self, kind: str, price: float, timestamp: datetime) -> str:
        raw = f"{kind}|{price:.10f}|{timestamp.isoformat()}".encode()
        return hashlib.sha1(raw).hexdigest()[:16]

    def add_pivot(self, pivot: Pivot, timeframe: str = "2m") -> LiquidityLevel:
        side = LiquiditySide.BUY_SIDE if pivot.kind is PivotKind.HIGH else LiquiditySide.SELL_SIDE
        tolerance = self.config.equal_level_tolerance_ticks * self.instrument.tick_size
        matches = [
            level
            for level in self.levels
            if level.active and level.side is side and abs(level.price - pivot.price) <= tolerance
        ]
        kind = pivot.kind.value
        if matches:
            level = min(matches, key=lambda item: abs(item.price - pivot.price))
            old_count = level.touch_count
            level.price = (level.price * old_count + pivot.price) / (old_count + 1)
            level.touch_count += 1
            level.type = "equal_high" if side is LiquiditySide.BUY_SIDE else "equal_low"
            level.strength = min(1.0, level.strength + 0.15)
            level.source_ids = level.source_ids + (pivot.occurred_at.isoformat(),)
            return level
        level = LiquidityLevel(
            id=self._id(kind, pivot.price, pivot.occurred_at),
            price=pivot.price,
            type=kind,
            side=side,
            timeframe=timeframe,
            strength=min(1.0, 0.35 + 0.1 * pivot.strength),
            touch_count=1,
            created_at=pivot.occurred_at,
            confirmed_at=pivot.confirmed_at,
            source_ids=(pivot.occurred_at.isoformat(),),
        )
        self.levels.append(level)
        self._created_index[level.id] = self._bar_index
        self._trim()
        return level

    def add_reference_level(
        self,
        *,
        price: float,
        kind: str,
        side: LiquiditySide,
        timeframe: str,
        created_at: datetime,
        confirmed_at: datetime,
        strength: float,
    ) -> LiquidityLevel:
        level = LiquidityLevel(
            id=self._id(kind, price, created_at),
            price=price,
            type=kind,
            side=side,
            timeframe=timeframe,
            strength=max(0.0, min(1.0, strength)),
            touch_count=0,
            created_at=created_at,
            confirmed_at=confirmed_at,
        )
        self.levels.append(level)
        self._created_index[level.id] = self._bar_index
        self._trim()
        return level

    def update(
        self, bar: Bar, dealing_low: float | None = None, dealing_high: float | None = None
    ) -> tuple[LiquidityEvent, ...]:
        self._bar_index += 1
        emitted: list[LiquidityEvent] = []
        excursion = self.config.sweep_excursion_ticks * self.instrument.tick_size
        tolerance = self.config.equal_level_tolerance_ticks * self.instrument.tick_size
        for level in self.levels:
            level.distance_from_price = abs(level.price - bar.close)
            if dealing_low is not None and dealing_high is not None:
                level.scope = (
                    LiquidityScope.INTERNAL
                    if dealing_low - tolerance <= level.price <= dealing_high + tolerance
                    else LiquidityScope.EXTERNAL
                )
            if not level.active or level.confirmed_at >= bar.timestamp:
                continue
            touched = (
                bar.high >= level.price
                if level.side is LiquiditySide.BUY_SIDE
                else bar.low <= level.price
            )
            if touched and level.last_touched_at != bar.timestamp:
                level.touch_count += 1
                level.last_touched_at = bar.timestamp
                emitted.append(LiquidityEvent(bar.timestamp, level.id, "touch", level.price, None))
            if level.side is LiquiditySide.BUY_SIDE:
                crossed = bar.high >= level.price + excursion
                reclaimed = bar.close < level.price
                consumed = bar.close > level.price + excursion
                direction = Direction.SHORT
            else:
                crossed = bar.low <= level.price - excursion
                reclaimed = bar.close > level.price
                consumed = bar.close < level.price - excursion
                direction = Direction.LONG
            if crossed and not level.swept and not consumed:
                self._pending_sweeps.setdefault(level.id, (self._bar_index, direction))
            pending = self._pending_sweeps.get(level.id)
            if pending is not None:
                age = self._bar_index - pending[0]
                if reclaimed and age < self.config.sweep_reclaim_bars and not level.swept:
                    level.swept = True
                    self._pending_sweeps.pop(level.id, None)
                    emitted.append(
                        LiquidityEvent(
                            bar.timestamp, level.id, "sweep_reclaim", level.price, pending[1]
                        )
                    )
                elif age >= self.config.sweep_reclaim_bars:
                    self._pending_sweeps.pop(level.id, None)
            if consumed and not level.consumed:
                self._pending_sweeps.pop(level.id, None)
                level.consumed = True
                level.active = False
                emitted.append(
                    LiquidityEvent(bar.timestamp, level.id, "consumed", level.price, None)
                )
        self.events.extend(emitted)
        return tuple(emitted)

    def active_targets(self, direction: Direction, current_price: float) -> list[LiquidityLevel]:
        min_distance = self.config.min_target_distance_ticks * self.instrument.tick_size
        desired = LiquiditySide.BUY_SIDE if direction is Direction.LONG else LiquiditySide.SELL_SIDE
        candidates = [
            level
            for level in self.levels
            if level.active
            and not level.consumed
            and level.side is desired
            and (
                level.price >= current_price + min_distance
                if direction is Direction.LONG
                else level.price <= current_price - min_distance
            )
        ]
        # "First logical liquidity" is nearest first; quality breaks near-ties.
        return sorted(
            candidates, key=lambda item: (abs(item.price - current_price), -self.score(item))
        )

    def score(self, level: LiquidityLevel) -> float:
        weights = self.config.weights
        timeframe_score = {
            "1w": 1.0,
            "1d": 0.9,
            "4h": 0.8,
            "1h": 0.7,
            "15m": 0.55,
            "5m": 0.4,
            "2m": 0.3,
        }.get(level.timeframe, 0.25)
        touches = min(level.touch_count / 3.0, 1.0)
        age = max(0, self._bar_index - self._created_index.get(level.id, self._bar_index))
        recency = 1.0 / (1.0 + age / 50.0)
        equality = 1.0 if level.type in {"equal_high", "equal_low"} else 0.3
        distance = 1.0 / (1.0 + level.distance_from_price / (100 * self.instrument.tick_size))
        session = 1.0 if level.type.startswith(("session_", "previous_day")) else 0.5
        components = {
            "timeframe": timeframe_score,
            "touches": touches,
            "recency": recency,
            "equality": equality,
            "distance": distance,
            "session": session,
        }
        total_weight = sum(weights.get(key, 0.0) for key in components) or 1.0
        score = (
            sum(weights.get(key, 0.0) * value for key, value in components.items()) / total_weight
        )
        return round(max(0.0, min(1.0, score)), 6)

    def _trim(self) -> None:
        overflow = len(self.levels) - self.config.max_levels
        if overflow <= 0:
            return
        inactive = sorted(
            (level for level in self.levels if not level.active),
            key=lambda item: item.confirmed_at,
        )
        remove_ids = {level.id for level in inactive[:overflow]}
        if len(remove_ids) < overflow:
            remaining = sorted(self.levels, key=lambda item: item.confirmed_at)
            remove_ids.update(level.id for level in remaining[: overflow - len(remove_ids)])
        self.levels = [level for level in self.levels if level.id not in remove_ids]
