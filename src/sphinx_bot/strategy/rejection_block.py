"""Predeclared Bryan/Powell-inspired key-open rejection-block experiment.

This is deliberately separate from the frozen Scriv-inspired baseline.  It turns
only publicly observable rejection-block ideas into deterministic rules; it is
not represented as Bryan's complete discretionary method.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..config import StrategyConfig
from ..models import Bar, Decision, Direction, Regime, SetupPlan, StrategyState
from .state_machine import StrategyStep


@dataclass
class RejectionBlock:
    key: str
    key_open: float
    direction: Direction
    extreme: float
    body_edge: float
    formed_at: datetime
    eligible_after: datetime

    @property
    def midpoint(self) -> float:
        return (self.extreme + self.body_edge) / 2.0


class KeyOpenRejectionBlockMachine:
    """Causal key-open rejection-block model on completed execution bars.

    Predeclared rules:
    * New York 00:00 and 02:00 opens are the only reference levels.
    * A bearish block has an upper wick reaching the open while its entire body
      remains below it; bullish is the mirror image.
    * Keep only the most extreme block for each key open and direction.
    * Entry is the wick midpoint on a later bar, stop one tick past the wick,
      and target is fixed at 3R.  No same-bar formation/entry is permitted.
    """

    KEY_OPEN_TIMES = (time(0, 0), time(2, 0))
    REWARD_RISK = 3.0
    STOP_BUFFER_TICKS = 1.0

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.state = StrategyState.IDLE
        self.current_session: date | None = None
        self.last_timestamp: datetime | None = None
        self.latest_regime = Regime.UNKNOWN
        self._zone = ZoneInfo(config.session.timezone)
        self._session_start = self._parse_clock(config.session.start)
        self._session_end = self._parse_clock(config.session.end)
        self._key_opens: dict[str, float] = {}
        self._blocks: dict[tuple[str, Direction], RejectionBlock] = {}

    @staticmethod
    def _parse_clock(value: str) -> time:
        hour, minute = (int(item) for item in value.split(":"))
        return time(hour, minute)

    def _session_membership(self, timestamp: datetime) -> tuple[bool, date]:
        local = timestamp.astimezone(self._zone)
        clock = local.time().replace(tzinfo=None)
        if self._session_start < self._session_end:
            inside = self._session_start <= clock < self._session_end
            key = local.date()
        else:
            inside = clock >= self._session_start or clock < self._session_end
            key = local.date() if clock >= self._session_start else local.date() - timedelta(days=1)
        return inside and key.weekday() in self.config.session.weekdays, key

    def session_info(self, timestamp: datetime) -> tuple[bool, date]:
        return self._session_membership(timestamp)

    def on_bar(self, bar: Bar, secondary_bar: Bar | None = None) -> StrategyStep:
        del secondary_bar
        decisions: list[Decision] = []
        if self.last_timestamp is not None and bar.timestamp <= self.last_timestamp:
            self.state = StrategyState.DISABLED
            return StrategyStep(
                None,
                (
                    Decision(
                        bar.timestamp,
                        self.state,
                        "invalid_data",
                        False,
                        ("bar timestamp is not strictly increasing",),
                    ),
                ),
            )
        self.last_timestamp = bar.timestamp
        inside, session_key = self._session_membership(bar.timestamp)
        session_ended = self.current_session is not None and not inside
        if not inside:
            if self.state not in {StrategyState.POSITION_OPEN, StrategyState.DISABLED}:
                self.state = StrategyState.IDLE
            return StrategyStep(None, (), session_ended=session_ended)

        if self.current_session != session_key:
            self.current_session = session_key
            self._key_opens.clear()
            self._blocks.clear()
            if self.state is not StrategyState.DISABLED:
                self.state = StrategyState.WAITING_FOR_LOCATION
            decisions.append(
                Decision(
                    bar.timestamp,
                    self.state,
                    "rejection_block_session_initialized",
                    True,
                    ("New York key-open levels reset",),
                )
            )

        if self.state is StrategyState.DISABLED:
            return StrategyStep(None, tuple(decisions))

        local = bar.timestamp.astimezone(self._zone)
        local_clock = local.time().replace(tzinfo=None)
        for key_time in self.KEY_OPEN_TIMES:
            if local_clock == key_time:
                key = key_time.strftime("%H:%M")
                self._key_opens[key] = bar.open
                # The new daily instance of this level invalidates yesterday's blocks.
                for block_key in tuple(self._blocks):
                    if block_key[0] == key:
                        del self._blocks[block_key]
                decisions.append(
                    Decision(
                        bar.timestamp,
                        self.state,
                        "key_open_recorded",
                        True,
                        (f"{key} America/New_York open recorded",),
                        details={"key_open": bar.open},
                    )
                )

        # Existing blocks are evaluated before the completed current bar is
        # allowed to create/replace one. A break past the tip invalidates first;
        # this is conservative if midpoint and invalidation occur in one OHLC bar.
        if self.state not in {StrategyState.POSITION_OPEN, StrategyState.ENTRY_READY}:
            plan = self._evaluate_existing_blocks(bar, decisions)
            if plan is not None:
                return StrategyStep(plan, tuple(decisions))

        self._update_blocks(bar, decisions)
        return StrategyStep(None, tuple(decisions))

    def _evaluate_existing_blocks(
        self, bar: Bar, decisions: list[Decision]
    ) -> SetupPlan | None:
        for block_key, block in sorted(
            tuple(self._blocks.items()), key=lambda item: item[1].formed_at
        ):
            if bar.timestamp <= block.eligible_after:
                continue
            invalid = (
                bar.high > block.extreme
                if block.direction is Direction.SHORT
                else bar.low < block.extreme
            )
            if invalid:
                del self._blocks[block_key]
                decisions.append(
                    Decision(
                        bar.timestamp,
                        self.state,
                        "rejection_block_invalidated",
                        False,
                        ("wick traded beyond rejection-block tip",),
                    )
                )
                continue
            entry = block.midpoint
            touched = bar.low <= entry <= bar.high
            if not touched:
                continue
            del self._blocks[block_key]
            plan = self._build_plan(bar, block)
            self.state = StrategyState.ENTRY_READY
            decisions.append(
                Decision(
                    bar.timestamp,
                    self.state,
                    "rejection_block_entry_ready",
                    True,
                    tuple(plan.passed_conditions),
                    plan.signal_id,
                    plan.to_dict(),
                )
            )
            return plan
        return None

    def _update_blocks(self, bar: Bar, decisions: list[Decision]) -> None:
        for key, level in self._key_opens.items():
            body_top = max(bar.open, bar.close)
            body_bottom = min(bar.open, bar.close)
            candidates: list[RejectionBlock] = []
            if bar.high >= level and body_top < level and bar.high > body_top:
                candidates.append(
                    RejectionBlock(
                        key,
                        level,
                        Direction.SHORT,
                        bar.high,
                        body_top,
                        bar.timestamp,
                        bar.timestamp,
                    )
                )
            if bar.low <= level and body_bottom > level and bar.low < body_bottom:
                candidates.append(
                    RejectionBlock(
                        key,
                        level,
                        Direction.LONG,
                        bar.low,
                        body_bottom,
                        bar.timestamp,
                        bar.timestamp,
                    )
                )
            for candidate in candidates:
                block_key = (key, candidate.direction)
                current = self._blocks.get(block_key)
                more_extreme = current is None or (
                    candidate.extreme > current.extreme
                    if candidate.direction is Direction.SHORT
                    else candidate.extreme < current.extreme
                )
                if more_extreme:
                    self._blocks[block_key] = candidate
                    decisions.append(
                        Decision(
                            bar.timestamp,
                            self.state,
                            "key_open_rejection_block_formed",
                            True,
                            ("wick reached key open", "entire candle body remained beyond level"),
                            details={
                                "key_open_name": key,
                                "key_open": level,
                                "direction": candidate.direction.value,
                                "wick_extreme": candidate.extreme,
                                "wick_midpoint": candidate.midpoint,
                            },
                        )
                    )

    def _build_plan(self, bar: Bar, block: RejectionBlock) -> SetupPlan:
        tick = self.config.instrument.tick_size
        entry = block.midpoint
        stop = block.extreme - block.direction.sign * self.STOP_BUFFER_TICKS * tick
        risk = abs(entry - stop)
        target_1 = entry + block.direction.sign * risk
        target_2 = entry + block.direction.sign * risk * self.REWARD_RISK
        raw_id = (
            f"RB|{block.key}|{block.formed_at.isoformat()}|{bar.timestamp.isoformat()}|"
            f"{block.direction.value}|{entry:.8f}"
        )
        return SetupPlan(
            signal_id=hashlib.sha256(raw_id.encode()).hexdigest()[:20],
            created_at=bar.timestamp,
            direction=block.direction,
            raw_entry=entry,
            raw_stop=stop,
            raw_target_1=target_1,
            raw_target_2=target_2,
            setup_score=100.0,
            passed_conditions=[
                "approved session active",
                f"{block.key} New York key open rejection block formed on a completed bar",
                "entry occurred on a later bar at 50% of the rejection wick",
                "stop is one tick beyond the rejection wick",
                "target is fixed at 3R",
            ],
            failed_conditions=[],
            evidence={
                "key_opens": "EXPLICIT RULE (public indicator): 00:00 and 02:00 are key opens",
                "block": (
                    "EXPLICIT RULE (public indicator): wick reaches level while body "
                    "stays beyond it"
                ),
                "entry": "LIKELY INFERENCE: rejection-block consequent encroachment (50% wick)",
                "stop": "LIKELY INFERENCE: one tick beyond wick invalidation",
                "target": (
                    "UNCONFIRMED: fixed 3R research rule; public posts do not specify a "
                    "universal target"
                ),
                "attribution": "Bryan/Powell-inspired public model; not an exact replication",
            },
            impulse_origin=block.body_edge,
            impulse_extreme=block.extreme,
            liquidity_target_id=f"key-open-{block.key}",
            regime=self.latest_regime,
        )

    def notify_position_open(self) -> None:
        if self.state is not StrategyState.ENTRY_READY:
            raise RuntimeError(f"cannot open position from state {self.state.value}")
        self.state = StrategyState.POSITION_OPEN

    def notify_entry_rejected(self) -> None:
        self.state = StrategyState.WAITING_FOR_LOCATION

    def notify_position_closed(self) -> None:
        self.state = StrategyState.WAITING_FOR_LOCATION

    def disable(self) -> None:
        self._blocks.clear()
        self.state = StrategyState.DISABLED

    def reenable_after_session_reset(self) -> None:
        if self.state is StrategyState.DISABLED:
            self.state = StrategyState.WAITING_FOR_LOCATION
