"""Hard risk constraints, deterministic position sizing, and latched kill switches."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from ..config import StrategyConfig
from ..models import Bar, Direction, KillReason, SetupPlan, Trade


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    quantity: int
    reasons: tuple[str, ...]
    risk_budget: float
    estimated_loss: float


@dataclass(frozen=True)
class KillSwitchEvent:
    timestamp: datetime
    reason: KillReason
    details: str
    requires_manual_review: bool


class RiskManager:
    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.equity = config.risk.initial_equity
        self.peak_equity = self.equity
        self.session_start_equity = self.equity
        self.week_start_equity = self.equity
        self.session_key: date | None = None
        self.week_key: tuple[int, int] | None = None
        self.trades_this_session = 0
        self.consecutive_losses = 0
        self.cooldown_until: datetime | None = None
        self.kills: dict[KillReason, KillSwitchEvent] = {}
        self.rejection_count = 0
        self.previous_session_bar: Bar | None = None

    @property
    def disabled(self) -> bool:
        return bool(self.kills)

    def reset_session(self, key: date, timestamp: datetime) -> None:
        if key == self.session_key:
            return
        self.session_key = key
        self.session_start_equity = self.equity
        iso = key.isocalendar()
        current_week = (iso.year, iso.week)
        if current_week != self.week_key:
            self.week_key = current_week
            self.week_start_equity = self.equity
            self.kills.pop(KillReason.WEEKLY_LOSS_LIMIT, None)
        self.trades_this_session = 0
        self.consecutive_losses = 0
        self.cooldown_until = None
        self.previous_session_bar = None
        # The daily limit unlocks only on a new configured session. Critical
        # operational and account drawdown kills remain latched for review.
        self.kills.pop(KillReason.DAILY_LOSS_LIMIT, None)

    def observe_market_data(self, bar: Bar, *, session_active: bool) -> None:
        if not session_active:
            self.previous_session_bar = None
            return
        previous = self.previous_session_bar
        if previous is not None:
            gap = (bar.timestamp - previous.timestamp).total_seconds()
            expected = self.config.timeframes.execution_seconds
            if gap > max(expected, self.config.execution.max_data_gap_seconds):
                self.activate(
                    KillReason.STALE_DATA,
                    bar.timestamp,
                    f"{gap:.0f}s gap within active session",
                    manual=True,
                )
        self.previous_session_bar = bar

    def check_open(
        self,
        plan: SetupPlan,
        timestamp: datetime,
        *,
        spread_ticks: float,
        existing_position: bool,
    ) -> RiskDecision:
        reasons: list[str] = []
        prices = (plan.raw_entry, plan.raw_stop, plan.raw_target_1, plan.raw_target_2)
        if not all(math.isfinite(value) for value in prices):
            self.activate(
                KillReason.RISK_CALCULATION_FAILURE,
                timestamp,
                "signal contains a non-finite price",
                manual=True,
            )
            reasons.append("non-finite signal price")
        if not math.isfinite(self.equity) or self.equity <= 0:
            self.activate(
                KillReason.UNEXPECTED_ACCOUNT_STATE,
                timestamp,
                f"invalid closed equity {self.equity}",
                manual=True,
            )
            reasons.append("invalid account equity")
        ordering_valid = (
            plan.raw_stop < plan.raw_entry < plan.raw_target_2
            if plan.direction is Direction.LONG
            else plan.raw_stop > plan.raw_entry > plan.raw_target_2
        )
        if not ordering_valid:
            reasons.append("entry/stop/target ordering is invalid at execution time")
        if self.disabled:
            reasons.append("kill switch active: " + ", ".join(item.value for item in self.kills))
        if existing_position:
            reasons.append("maximum one concurrent position")
        if self.cooldown_until is not None and timestamp < self.cooldown_until:
            reasons.append(f"loss cooldown active until {self.cooldown_until.isoformat()}")
        if self.trades_this_session >= self.config.risk.max_trades_per_session:
            reasons.append("maximum trades per session reached")
        if spread_ticks > self.config.execution.max_spread_ticks:
            self.activate(
                KillReason.ABNORMAL_SPREAD,
                timestamp,
                f"spread {spread_ticks} > limit {self.config.execution.max_spread_ticks}",
                manual=True,
            )
            reasons.append("abnormal spread")
        quantity, budget, estimated = self.position_size(plan)
        if quantity > 0:
            per_contract_estimate = estimated / quantity
            exposure_cap = math.floor(
                self.config.risk.max_notional_exposure
                / (plan.raw_entry * self.config.instrument.point_value)
            )
            increment = self.config.instrument.quantity_increment
            exposure_cap = (exposure_cap // increment) * increment
            quantity = min(quantity, exposure_cap)
            estimated = quantity * per_contract_estimate
        if quantity <= 0:
            reasons.append("risk budget or exposure cap cannot support minimum contract quantity")
        return RiskDecision(
            not reasons, quantity if not reasons else 0, tuple(reasons), budget, estimated
        )

    def position_size(self, plan: SetupPlan) -> tuple[int, float, float]:
        risk_budget = self.equity * self.config.risk.risk_per_trade_pct
        chart_stop_points = abs(plan.raw_entry - plan.raw_stop)
        if not math.isfinite(chart_stop_points) or chart_stop_points <= 0:
            return 0, risk_budget, 0.0
        execution = self.config.execution
        instrument = self.config.instrument
        adverse_entry_points = (
            execution.spread_ticks / 2 + execution.slippage_ticks
        ) * instrument.tick_size
        adverse_exit_points = adverse_entry_points
        fees = 2 * (
            execution.commission_per_contract_per_side
            + execution.exchange_fee_per_contract_per_side
        )
        per_contract_loss = (
            chart_stop_points + adverse_entry_points + adverse_exit_points
        ) * instrument.point_value + fees
        if per_contract_loss <= 0 or not math.isfinite(per_contract_loss):
            return 0, risk_budget, 0.0
        raw = math.floor(risk_budget / per_contract_loss)
        increment = instrument.quantity_increment
        quantity = (raw // increment) * increment
        quantity = min(quantity, instrument.max_contracts)
        return quantity, risk_budget, quantity * per_contract_loss

    def record_open(self) -> None:
        self.trades_this_session += 1
        self.rejection_count = 0

    def record_rejection(self, timestamp: datetime, details: str) -> None:
        self.rejection_count += 1
        if self.rejection_count >= self.config.risk.reject_after_count:
            self.activate(KillReason.REPEATED_REJECTION, timestamp, details, manual=True)

    def record_trade(self, trade: Trade) -> None:
        self.equity += trade.net_pnl
        self.peak_equity = max(self.peak_equity, self.equity)
        if trade.net_pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= self.config.risk.max_consecutive_losses:
                self.cooldown_until = trade.exit_time + timedelta(
                    minutes=self.config.risk.loss_cooldown_minutes
                )
        else:
            self.consecutive_losses = 0
        self._check_equity_limits(trade.exit_time, self.equity)

    def mark_to_market(self, timestamp: datetime, unrealized_pnl: float) -> None:
        marked = self.equity + unrealized_pnl
        self.peak_equity = max(self.peak_equity, marked)
        self._check_equity_limits(timestamp, marked)

    def _check_equity_limits(self, timestamp: datetime, marked_equity: float) -> None:
        daily_floor = self.session_start_equity * (1 - self.config.risk.daily_loss_limit_pct)
        if marked_equity <= daily_floor:
            self.activate(
                KillReason.DAILY_LOSS_LIMIT,
                timestamp,
                f"marked equity {marked_equity:.2f} <= daily floor {daily_floor:.2f}",
                manual=False,
            )
        weekly_floor = self.week_start_equity * (1 - self.config.risk.weekly_loss_limit_pct)
        if marked_equity <= weekly_floor:
            self.activate(
                KillReason.WEEKLY_LOSS_LIMIT,
                timestamp,
                f"marked equity {marked_equity:.2f} <= weekly floor {weekly_floor:.2f}",
                manual=False,
            )
        drawdown = (
            (self.peak_equity - marked_equity) / self.peak_equity if self.peak_equity else 1.0
        )
        if drawdown >= self.config.risk.max_drawdown_pct:
            self.activate(
                KillReason.MAX_DRAWDOWN,
                timestamp,
                f"drawdown {drawdown:.2%} >= {self.config.risk.max_drawdown_pct:.2%}",
                manual=True,
            )

    def check_position_consistency(
        self,
        *,
        timestamp: datetime,
        strategy_expects_position: bool,
        broker_has_position: bool,
    ) -> bool:
        if strategy_expects_position == broker_has_position:
            return True
        self.activate(
            KillReason.POSITION_MISMATCH,
            timestamp,
            (
                f"strategy expects position={strategy_expects_position}, "
                f"broker reports position={broker_has_position}"
            ),
            manual=True,
        )
        return False

    def activate(
        self,
        reason: KillReason,
        timestamp: datetime,
        details: str,
        *,
        manual: bool,
    ) -> KillSwitchEvent:
        event = KillSwitchEvent(timestamp, reason, details, manual)
        self.kills.setdefault(reason, event)
        return self.kills[reason]

    def manual_review_reset(self, reason: KillReason) -> None:
        event = self.kills.get(reason)
        if event is None:
            return
        if reason is KillReason.MAX_DRAWDOWN:
            raise PermissionError(
                "max drawdown reset requires a new risk configuration/research review"
            )
        del self.kills[reason]
