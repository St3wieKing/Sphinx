"""Event-driven backtest using the exact paper strategy/broker components."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime

from ..config import StrategyConfig
from ..execution.simulator import PaperBroker
from ..models import Bar, Decision, ExitReason, KillReason, SetupPlan, StrategyState, Trade
from ..monitoring.audit import AuditLogger
from ..risk.manager import RiskManager
from ..strategy.state_machine import ScrivStateMachine
from .metrics import performance_metrics


@dataclass(frozen=True)
class BacktestResult:
    config_fingerprint: str
    trades: tuple[Trade, ...]
    equity_curve: tuple[tuple[datetime, float], ...]
    decisions: tuple[Decision, ...]
    metrics: dict[str, object]
    kill_switches: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "config_fingerprint": self.config_fingerprint,
            "trades": [trade.to_dict() for trade in self.trades],
            "equity_curve": [
                {"timestamp": timestamp.isoformat(), "equity": equity}
                for timestamp, equity in self.equity_curve
            ],
            "decisions": [decision.to_dict() for decision in self.decisions],
            "metrics": self.metrics,
            "kill_switches": list(self.kill_switches),
        }


@dataclass
class _Pending:
    plan: SetupPlan
    due_index: int


class BacktestEngine:
    def __init__(self, config: StrategyConfig, audit: AuditLogger | None = None) -> None:
        config.validate()
        self.config = config
        self.audit = audit or AuditLogger()

    def run(
        self,
        bars: Sequence[Bar],
        *,
        secondary_bars: Mapping[datetime, Bar] | None = None,
    ) -> BacktestResult:
        if not bars:
            raise ValueError("backtest requires at least one bar")
        machine = ScrivStateMachine(self.config)
        broker = PaperBroker(self.config)
        risk = RiskManager(self.config)
        decisions: list[Decision] = []
        equity_curve: list[tuple[datetime, float]] = []
        pending: _Pending | None = None
        logged_kills: set[tuple[str, str]] = set()
        previous_bar: Bar | None = None
        previous_inside = False
        self.audit.write(
            "run_started",
            {
                "config_fingerprint": self.config.fingerprint,
                "bars": len(bars),
                "first": bars[0].timestamp,
                "last": bars[-1].timestamp,
                "paper_only": self.config.paper_only,
            },
        )

        for index, bar in enumerate(bars):
            inside, session_key = machine.session_info(bar.timestamp)
            if inside and session_key != risk.session_key:
                risk.reset_session(session_key, bar.timestamp)
                if not risk.disabled:
                    machine.reenable_after_session_reset()
                self.audit.write(
                    "risk_session_reset", {"session": session_key, "equity": risk.equity}
                )

            # Force flat at the final completed in-session close. We never use
            # the first out-of-session bar as if it were available earlier.
            if (
                previous_bar is not None
                and previous_inside
                and not inside
                and broker.has_position
                and self.config.session.force_flat_at_end
            ):
                trade = broker.force_close(previous_bar, ExitReason.SESSION_END)
                if trade:
                    self._record_trade(trade, risk, machine)
                    self.audit.write("trade", trade)

            risk.observe_market_data(bar, session_active=inside)
            if broker.has_position and inside:
                try:
                    trade = broker.process_bar(bar)
                except (RuntimeError, ValueError) as exc:
                    risk.activate(
                        KillReason.EXECUTION_ERROR,
                        bar.timestamp,
                        f"paper broker bar processing failed: {exc}",
                        manual=True,
                    )
                    machine.disable()
                    trade = None
                if trade:
                    self._record_trade(trade, risk, machine)
                    self.audit.write("trade", trade)

            # Delayed confirmation orders fill at the next eligible bar open.
            if pending is not None and index >= pending.due_index and not broker.has_position:
                if not inside:
                    decision = Decision(
                        bar.timestamp,
                        machine.state,
                        "delayed_entry_cancelled",
                        False,
                        ("next bar is outside approved session",),
                        pending.plan.signal_id,
                    )
                    decisions.append(decision)
                    self.audit.write("decision", decision)
                    machine.notify_entry_rejected()
                    pending = None
                else:
                    executable = replace(pending.plan, raw_entry=bar.open)
                    risk_decision = risk.check_open(
                        executable,
                        bar.timestamp,
                        spread_ticks=self.config.execution.spread_ticks,
                        existing_position=broker.has_position,
                    )
                    if risk_decision.allowed:
                        try:
                            broker.open(
                                executable,
                                risk_decision.quantity,
                                bar.timestamp,
                                chart_entry=bar.open,
                            )
                            risk.record_open()
                            machine.notify_position_open()
                            self.audit.write(
                                "risk_approval",
                                {"signal_id": executable.signal_id, **risk_decision.__dict__},
                            )
                            trade = broker.process_bar(bar, entry_bar=True)
                        except (RuntimeError, ValueError) as exc:
                            risk.activate(
                                KillReason.EXECUTION_ERROR,
                                bar.timestamp,
                                f"paper entry execution failed: {exc}",
                                manual=True,
                            )
                            machine.disable()
                            trade = None
                        if trade:
                            self._record_trade(trade, risk, machine)
                            self.audit.write("trade", trade)
                    else:
                        self._reject_entry(
                            machine, risk, executable, bar, risk_decision.reasons, decisions
                        )
                    pending = None

            secondary = secondary_bars.get(bar.timestamp) if secondary_bars else None
            step = machine.on_bar(bar, secondary)
            for decision in step.decisions:
                decisions.append(decision)
                self.audit.write("decision", decision)

            if step.plan is not None:
                delay = self.config.execution.entry_delay_bars
                if self.config.setup.entry_confirmation == "close_rejection":
                    delay = max(1, delay)
                if delay > 0:
                    pending = _Pending(step.plan, index + delay)
                    self.audit.write(
                        "order_pending",
                        {"signal_id": step.plan.signal_id, "due_index": index + delay},
                    )
                else:
                    risk_decision = risk.check_open(
                        step.plan,
                        bar.timestamp,
                        spread_ticks=self.config.execution.spread_ticks,
                        existing_position=broker.has_position,
                    )
                    if risk_decision.allowed:
                        try:
                            broker.open(step.plan, risk_decision.quantity, bar.timestamp)
                            risk.record_open()
                            machine.notify_position_open()
                            self.audit.write(
                                "risk_approval",
                                {"signal_id": step.plan.signal_id, **risk_decision.__dict__},
                            )
                            trade = broker.process_bar(bar, entry_bar=True)
                        except (RuntimeError, ValueError) as exc:
                            risk.activate(
                                KillReason.EXECUTION_ERROR,
                                bar.timestamp,
                                f"paper entry execution failed: {exc}",
                                manual=True,
                            )
                            machine.disable()
                            trade = None
                        if trade:
                            self._record_trade(trade, risk, machine)
                            self.audit.write("trade", trade)
                    else:
                        self._reject_entry(
                            machine, risk, step.plan, bar, risk_decision.reasons, decisions
                        )

            risk.check_position_consistency(
                timestamp=bar.timestamp,
                strategy_expects_position=machine.state is StrategyState.POSITION_OPEN,
                broker_has_position=broker.has_position,
            )
            risk.mark_to_market(bar.timestamp, broker.unrealized_pnl(bar.close))
            for reason, event in risk.kills.items():
                key = (reason.value, event.timestamp.isoformat())
                if key not in logged_kills:
                    logged_kills.add(key)
                    self.audit.write("kill_switch", event)
            if risk.disabled:
                pending = None
                machine.disable()
                if broker.has_position and self.config.risk.flatten_on_critical_kill:
                    trade = broker.force_close(bar, ExitReason.KILL_SWITCH)
                    if trade:
                        risk.record_trade(trade)
                        self.audit.write("trade", trade)
            equity_curve.append((bar.timestamp, risk.equity + broker.unrealized_pnl(bar.close)))
            previous_bar = bar
            previous_inside = inside

        if broker.has_position:
            trade = broker.force_close(bars[-1], ExitReason.END_OF_DATA)
            if trade:
                self._record_trade(trade, risk, machine)
                self.audit.write("trade", trade)
                equity_curve.append((bars[-1].timestamp, risk.equity))
        metrics = performance_metrics(broker.trades, self.config.risk.initial_equity, equity_curve)
        kill_switches = tuple(
            {
                "reason": reason.value,
                "timestamp": event.timestamp.isoformat(),
                "details": event.details,
                "requires_manual_review": str(event.requires_manual_review).lower(),
            }
            for reason, event in risk.kills.items()
        )
        self.audit.write("run_completed", {"metrics": metrics, "kills": kill_switches})
        return BacktestResult(
            config_fingerprint=self.config.fingerprint,
            trades=tuple(broker.trades),
            equity_curve=tuple(equity_curve),
            decisions=tuple(decisions),
            metrics=metrics,
            kill_switches=kill_switches,
        )

    def _reject_entry(
        self,
        machine: ScrivStateMachine,
        risk: RiskManager,
        plan: SetupPlan,
        bar: Bar,
        reasons: tuple[str, ...],
        decisions: list[Decision],
    ) -> None:
        decision = Decision(
            bar.timestamp,
            machine.state,
            "risk_rejected_entry",
            False,
            reasons,
            plan.signal_id,
        )
        decisions.append(decision)
        self.audit.write("decision", decision)
        risk.record_rejection(bar.timestamp, "; ".join(reasons))
        machine.notify_entry_rejected()

    @staticmethod
    def _record_trade(
        trade: Trade,
        risk: RiskManager,
        machine: ScrivStateMachine,
    ) -> None:
        risk.record_trade(trade)
        if machine.state is not StrategyState.DISABLED:
            machine.notify_position_closed()
