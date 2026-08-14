"""The executable, deterministic 50% retracement state machine."""

from __future__ import annotations

import hashlib
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ..config import StrategyConfig
from ..data.resample import MultiTimeframeFeed
from ..models import (
    Bar,
    Consolidation,
    Decision,
    Direction,
    Regime,
    SetupPlan,
    StrategyState,
)
from .areas_of_interest import AreaOfInterestEngine, dealing_range
from .context import SMTDivergenceDetector, SMTEvent
from .liquidity import LiquidityEngine
from .market_structure import MarketStructureEngine, detect_consolidation


@dataclass
class Impulse:
    direction: Direction
    origin: float
    extreme: float
    breakout_at: datetime
    consolidation: Consolidation
    breakout_body: float
    bars_elapsed: int = 0
    extension_count: int = 0

    @property
    def midpoint(self) -> float:
        return (self.origin + self.extreme) / 2.0

    @property
    def width(self) -> float:
        return abs(self.extreme - self.origin)


@dataclass(frozen=True)
class StrategyStep:
    plan: SetupPlan | None
    decisions: tuple[Decision, ...]
    session_ended: bool = False


class ScrivStateMachine:
    """Source-inspired baseline, not a claim of exact strategy replication.

    Engines update on every completed execution bar. Entry decisions are allowed
    only in the configured session. A retracement trigger can use only the
    impulse midpoint calculated before the triggering bar began.
    """

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.state = StrategyState.IDLE
        self.structure = MarketStructureEngine(config.structure, config.instrument)
        self.liquidity = LiquidityEngine(config.liquidity, config.instrument)
        self.execution_aoi = AreaOfInterestEngine(config.setup, config.instrument, "2m")
        intervals = config.timeframes.intermediate_seconds + config.timeframes.context_seconds
        self.multitimeframe = MultiTimeframeFeed(intervals)
        self.context_aois = {
            seconds: AreaOfInterestEngine(config.setup, config.instrument, self._tf_name(seconds))
            for seconds in intervals
        }
        self.smt = SMTDivergenceDetector(lookback=10)
        self.latest_smt: SMTEvent | None = None
        history_size = (
            max(
                config.session.warmup_bars,
                config.setup.consolidation_lookback,
                config.structure.atr_period,
            )
            + 1
        )
        self.history: deque[Bar] = deque(maxlen=history_size)
        self.impulse: Impulse | None = None
        self.current_session: date | None = None
        self.last_timestamp: datetime | None = None
        self.cooldown_remaining = 0
        self.latest_regime = Regime.UNKNOWN
        self._zone = ZoneInfo(config.session.timezone)
        self._session_start = self._parse_clock(config.session.start)
        self._session_end = self._parse_clock(config.session.end)

    @staticmethod
    def _parse_clock(value: str) -> time:
        hour, minute = (int(item) for item in value.split(":"))
        return time(hour, minute)

    @staticmethod
    def _tf_name(seconds: int) -> str:
        if seconds % 3600 == 0:
            return f"{seconds // 3600}h"
        return f"{seconds // 60}m"

    def _session_membership(self, timestamp: datetime) -> tuple[bool, date]:
        local = timestamp.astimezone(self._zone)
        clock = local.time().replace(tzinfo=None)
        if self._session_start < self._session_end:
            inside = self._session_start <= clock < self._session_end
            key = local.date()
        else:
            inside = clock >= self._session_start or clock < self._session_end
            key = local.date() if clock >= self._session_start else local.date() - timedelta(days=1)
        # For an overnight window, weekday eligibility belongs to its start date.
        inside = inside and key.weekday() in self.config.session.weekdays
        return inside, key

    def session_info(self, timestamp: datetime) -> tuple[bool, date]:
        return self._session_membership(timestamp)

    def on_bar(self, bar: Bar, secondary_bar: Bar | None = None) -> StrategyStep:
        decisions: list[Decision] = []
        if self.last_timestamp is not None and bar.timestamp <= self.last_timestamp:
            self.state = StrategyState.DISABLED
            decision = Decision(
                bar.timestamp,
                self.state,
                "invalid_data",
                False,
                ("bar timestamp is not strictly increasing",),
            )
            return StrategyStep(None, (decision,))
        self.last_timestamp = bar.timestamp

        # Capture prior ATR/history before exposing the current completed bar to
        # breakout logic. Breakout location can therefore use only t-1 context.
        prior_atr = self.structure.atr.value
        prior_history = list(self.history)
        snapshot, pivots = self.structure.update(bar)
        self.latest_regime = snapshot.regime
        active_range = dealing_range(snapshot.latest_high, snapshot.latest_low)
        self.liquidity.update(
            bar,
            active_range.lower if active_range else None,
            active_range.upper if active_range else None,
        )
        for pivot in pivots:
            self.liquidity.add_pivot(pivot, "2m")
        self.execution_aoi.update(bar)
        for seconds, aggregate in self.multitimeframe.update(bar).items():
            created = self.context_aois[seconds].update(aggregate)
            if created:
                decisions.append(
                    Decision(
                        bar.timestamp,
                        self.state,
                        "higher_timeframe_aoi_confirmed",
                        True,
                        (f"{len(created)} completed {self._tf_name(seconds)} zone(s)",),
                    )
                )
        if secondary_bar is not None:
            self.latest_smt = self.smt.update(bar, secondary_bar) or self.latest_smt
        self.history.append(bar)

        inside, session_key = self._session_membership(bar.timestamp)
        session_ended = (
            self.current_session is not None and not inside and self.state is not StrategyState.IDLE
        )
        if not inside:
            if self.state not in {StrategyState.POSITION_OPEN, StrategyState.DISABLED}:
                self._reset(StrategyState.IDLE)
            return StrategyStep(None, tuple(decisions), session_ended=session_ended)

        if self.current_session != session_key:
            self.current_session = session_key
            if self.state is not StrategyState.DISABLED:
                self._reset(StrategyState.SESSION_INITIALIZATION)
                decisions.append(
                    Decision(
                        bar.timestamp,
                        self.state,
                        "session_initialized",
                        True,
                        (
                            "risk/session counters reset externally",
                            "levels use confirmed data only",
                        ),
                    )
                )
                self.state = StrategyState.WAITING_FOR_LOCATION

        if self.state is StrategyState.DISABLED:
            return StrategyStep(None, tuple(decisions))
        if self.state is StrategyState.POSITION_OPEN:
            return StrategyStep(None, tuple(decisions))
        if len(prior_history) < self.config.session.warmup_bars or prior_atr is None:
            decisions.append(
                Decision(
                    bar.timestamp,
                    self.state,
                    "warmup",
                    False,
                    ("insufficient completed warmup bars",),
                )
            )
            return StrategyStep(None, tuple(decisions))
        if self.state is StrategyState.COOLDOWN:
            self.cooldown_remaining -= 1
            if self.cooldown_remaining <= 0:
                self.state = StrategyState.WAITING_FOR_LOCATION
                decisions.append(
                    Decision(
                        bar.timestamp,
                        self.state,
                        "cooldown_complete",
                        True,
                        ("bar cooldown elapsed",),
                    )
                )
            return StrategyStep(None, tuple(decisions))

        if self.state is StrategyState.WAITING_FOR_LOCATION:
            consolidation = detect_consolidation(
                prior_history,
                self.config.setup.consolidation_lookback,
                prior_atr,
                self.config.setup.consolidation_max_atr,
            )
            if consolidation is None:
                return StrategyStep(None, tuple(decisions))
            direction = self._breakout_direction(bar, consolidation, prior_atr)
            if direction is None:
                return StrategyStep(None, tuple(decisions))
            origin = consolidation.low if direction is Direction.LONG else consolidation.high
            extreme = bar.high if direction is Direction.LONG else bar.low
            self.impulse = Impulse(
                direction, origin, extreme, bar.timestamp, consolidation, bar.body
            )
            self.state = StrategyState.TRACKING_IMPULSE
            decisions.append(
                Decision(
                    bar.timestamp,
                    self.state,
                    "displacement_breakout",
                    True,
                    (
                        "prior-window consolidation valid",
                        "close cleared buffered range",
                        "body met ATR displacement threshold",
                    ),
                    details={
                        "direction": direction.value,
                        "origin": origin,
                        "extreme": extreme,
                        "midpoint": self.impulse.midpoint,
                    },
                )
            )
            return StrategyStep(None, tuple(decisions))

        if self.state is StrategyState.TRACKING_IMPULSE and self.impulse is not None:
            plan, tracking_decisions = self._track_impulse(bar)
            decisions.extend(tracking_decisions)
            return StrategyStep(plan, tuple(decisions))
        if self.state is StrategyState.ENTRY_READY:
            return StrategyStep(None, tuple(decisions))
        return StrategyStep(None, tuple(decisions))

    def _breakout_direction(
        self, bar: Bar, consolidation: Consolidation, atr: float
    ) -> Direction | None:
        buffer = self.config.setup.breakout_buffer_ticks * self.config.instrument.tick_size
        displaced = bar.body >= atr * self.config.setup.displacement_min_atr
        if not displaced:
            return None
        bullish = bar.close > consolidation.high + buffer
        bearish = bar.close < consolidation.low - buffer
        if bullish == bearish:
            return None
        return Direction.LONG if bullish else Direction.SHORT

    def _track_impulse(self, bar: Bar) -> tuple[SetupPlan | None, list[Decision]]:
        assert self.impulse is not None
        impulse = self.impulse
        impulse.bars_elapsed += 1
        decisions: list[Decision] = []
        setup = self.config.setup
        tick = self.config.instrument.tick_size
        tolerance = setup.retest_tolerance_ticks * tick

        if impulse.bars_elapsed > setup.max_retrace_bars:
            decisions.append(
                Decision(
                    bar.timestamp,
                    self.state,
                    "setup_expired",
                    False,
                    ("maximum retrace bars exceeded",),
                )
            )
            self._reset(StrategyState.WAITING_FOR_LOCATION)
            return None, decisions
        invalidated = (
            bar.close < impulse.origin
            if impulse.direction is Direction.LONG
            else bar.close > impulse.origin
        )
        if invalidated:
            decisions.append(
                Decision(
                    bar.timestamp,
                    self.state,
                    "setup_invalidated",
                    False,
                    ("close crossed impulse origin",),
                )
            )
            self._reset(StrategyState.WAITING_FOR_LOCATION)
            return None, decisions

        # Midpoint and extreme were both known before this bar. Check that
        # standing trigger first; update a new extreme only if no retrace fired.
        entry = impulse.midpoint
        touched = (
            bar.low <= entry + tolerance and bar.high >= entry
            if impulse.direction is Direction.LONG
            else bar.high >= entry - tolerance and bar.low <= entry
        )
        confirmed = touched
        if setup.entry_confirmation == "close_rejection":
            confirmed = touched and (
                bar.close > entry and bar.close > bar.open
                if impulse.direction is Direction.LONG
                else bar.close < entry and bar.close < bar.open
            )
        if confirmed:
            planned_entry = bar.close if setup.entry_confirmation == "close_rejection" else entry
            plan = self._build_plan(bar, impulse, planned_entry)
            if plan.failed_conditions:
                decisions.append(
                    Decision(
                        bar.timestamp,
                        self.state,
                        "entry_rejected",
                        False,
                        tuple(plan.failed_conditions),
                        plan.signal_id,
                        plan.to_dict(),
                    )
                )
                self._reset(StrategyState.COOLDOWN)
                self.cooldown_remaining = setup.cooldown_bars
                return None, decisions
            self.state = StrategyState.ENTRY_READY
            decisions.append(
                Decision(
                    bar.timestamp,
                    self.state,
                    "entry_checklist_passed",
                    True,
                    tuple(plan.passed_conditions),
                    plan.signal_id,
                    plan.to_dict(),
                )
            )
            return plan, decisions

        extended = False
        if impulse.direction is Direction.LONG and bar.high > impulse.extreme:
            impulse.extreme = bar.high
            extended = True
        elif impulse.direction is Direction.SHORT and bar.low < impulse.extreme:
            impulse.extreme = bar.low
            extended = True
        if extended:
            impulse.extension_count += 1
            decisions.append(
                Decision(
                    bar.timestamp,
                    self.state,
                    "impulse_extended",
                    True,
                    ("no prior midpoint trigger; extreme updated after bar close",),
                    details={"extreme": impulse.extreme, "midpoint": impulse.midpoint},
                )
            )
        return None, decisions

    def _build_plan(self, bar: Bar, impulse: Impulse, entry: float) -> SetupPlan:
        tick = self.config.instrument.tick_size
        setup = self.config.setup
        direction = impulse.direction
        fixed = entry - direction.sign * setup.fixed_stop_ticks * tick
        pivotal = impulse.origin - direction.sign * setup.pivotal_buffer_ticks * tick
        if setup.stop_mode == "fixed":
            stop = fixed
        elif setup.stop_mode == "pivotal":
            stop = pivotal
        else:
            pivotal_distance = abs(entry - pivotal)
            fixed_distance = setup.fixed_stop_ticks * tick
            stop = pivotal if 0 < pivotal_distance <= fixed_distance else fixed
        target_1 = impulse.extreme
        fallback = impulse.origin + direction.sign * setup.extension_multiple * impulse.width
        candidates = self.liquidity.active_targets(direction, target_1)
        target_level = candidates[0] if candidates else None
        target_2 = target_level.price if target_level is not None else fallback
        if direction is Direction.LONG:
            target_2 = max(target_2, target_1)
        else:
            target_2 = min(target_2, target_1)

        active_context = []
        for engine in self.context_aois.values():
            active_context.extend(
                engine.active_at(impulse.origin, bullish=direction is Direction.LONG)
            )
        smt_valid = self.latest_smt is not None and self.latest_smt.direction is direction
        risk = abs(entry - stop)
        rr = abs(target_2 - entry) / risk if risk else 0.0
        passed = [
            "approved session active",
            "consolidation breakout confirmed on a completed bar",
            "50% impulse retracement touched",
            "stop is beyond entry in the invalidation direction",
            "target is beyond entry in the trade direction",
        ]
        failed: list[str] = []
        if risk <= 0:
            failed.append("zero or inverted stop distance")
        if direction is Direction.LONG and not (stop < entry < target_2):
            failed.append("long price ordering invalid")
        if direction is Direction.SHORT and not (stop > entry > target_2):
            failed.append("short price ordering invalid")
        if rr < setup.minimum_rr:
            failed.append(f"expected RR {rr:.3f} below minimum {setup.minimum_rr:.3f}")
        if setup.require_context_aoi and not active_context:
            failed.append("required completed higher-timeframe AOI absent")
        elif active_context:
            passed.append("completed higher-timeframe AOI confluence present")
        if setup.require_smt and not smt_valid:
            failed.append("required synchronized SMT proxy absent")
        elif smt_valid:
            passed.append("causal SMT proxy aligns")

        weights = setup.score_weights
        displacement_score = min(
            1.0,
            impulse.breakout_body
            / max(impulse.consolidation.atr * setup.displacement_min_atr, tick),
        )
        location_score = max(
            0.0,
            1.0
            - impulse.consolidation.width
            / max(impulse.consolidation.atr * setup.consolidation_max_atr, tick),
        )
        liquidity_score = self.liquidity.score(target_level) if target_level else 0.4
        context_score = 1.0 if active_context else 0.5
        freshness_score = max(0.0, 1.0 - impulse.bars_elapsed / setup.max_retrace_bars)
        components = {
            "location": location_score,
            "displacement": displacement_score,
            "liquidity": liquidity_score,
            "context": context_score,
            "freshness": freshness_score,
        }
        denominator = sum(weights.get(name, 0.0) for name in components) or 1.0
        score = (
            100
            * sum(weights.get(name, 0.0) * value for name, value in components.items())
            / denominator
        )
        raw_id = (
            f"{bar.timestamp.isoformat()}|{direction.value}|{entry:.8f}|"
            f"{impulse.breakout_at.isoformat()}"
        )
        signal_id = hashlib.sha256(raw_id.encode()).hexdigest()[:20]
        return SetupPlan(
            signal_id=signal_id,
            created_at=bar.timestamp,
            direction=direction,
            raw_entry=entry,
            raw_stop=stop,
            raw_target_1=target_1,
            raw_target_2=target_2,
            setup_score=round(score, 2),
            passed_conditions=passed,
            failed_conditions=failed,
            evidence={
                "core_entry": "EXPLICIT_RULE: consolidation break, evolving high/low, 50% retest",
                "stop": "EXPLICIT_RULE with deterministic fixed-or-pivotal interpretation",
                "target_1": "EXPLICIT_RULE: prior/range high-low",
                "target_2": "EXPLICIT_RULE plus deterministic first-active-liquidity fallback",
                "score": "EXPERIMENTAL AUTOMATION; not stated by source",
            },
            impulse_origin=impulse.origin,
            impulse_extreme=impulse.extreme,
            liquidity_target_id=target_level.id if target_level else None,
            regime=self.latest_regime,
        )

    def notify_position_open(self) -> None:
        if self.state is not StrategyState.ENTRY_READY:
            raise RuntimeError(f"cannot open position from state {self.state.value}")
        self.state = StrategyState.POSITION_OPEN

    def notify_entry_rejected(self) -> None:
        self._reset(StrategyState.COOLDOWN)
        self.cooldown_remaining = self.config.setup.cooldown_bars

    def notify_position_closed(self) -> None:
        self._reset(StrategyState.COOLDOWN)
        self.cooldown_remaining = self.config.setup.cooldown_bars

    def disable(self) -> None:
        self.impulse = None
        self.state = StrategyState.DISABLED

    def reenable_after_session_reset(self) -> None:
        if self.state is StrategyState.DISABLED:
            self._reset(StrategyState.IDLE)

    def _reset(self, state: StrategyState) -> None:
        self.impulse = None
        self.state = state
