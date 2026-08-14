"""Conservative OHLC paper broker for NQ futures research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ..config import StrategyConfig
from ..models import Bar, Direction, ExitReason, Fill, Position, SetupPlan, Trade


@dataclass(frozen=True)
class BrokerEvent:
    timestamp: datetime
    event: str
    signal_id: str
    details: dict[str, float | int | str]


class PaperBroker:
    """Single-position paper broker.

    Intrabar policy:
    * an existing stop wins whenever stop and target both occur in one OHLC bar;
    * on the entry bar, only an adverse stop can execute (no favorable exit);
    * price gaps through a stop fill at the worse opening chart price;
    * spread and slippage are charged adversely on every fill.
    """

    def __init__(self, config: StrategyConfig) -> None:
        self.config = config
        self.position: Position | None = None
        self.trades: list[Trade] = []
        self.events: list[BrokerEvent] = []

    @property
    def has_position(self) -> bool:
        return self.position is not None

    def open(
        self,
        plan: SetupPlan,
        quantity: int,
        timestamp: datetime,
        *,
        chart_entry: float | None = None,
    ) -> Position:
        if self.position is not None:
            raise RuntimeError("broker already has an open position")
        if quantity <= 0 or quantity % self.config.instrument.quantity_increment:
            raise ValueError("invalid order quantity")
        if quantity > self.config.instrument.max_contracts:
            raise ValueError("quantity exceeds broker limit")
        chart_entry = plan.raw_entry if chart_entry is None else chart_entry
        fill_price = self._adverse_price(chart_entry, plan.direction, entering=True)
        fee = self._fee(quantity)
        fill = Fill(
            timestamp=timestamp,
            price=fill_price,
            chart_price=chart_entry,
            quantity=quantity,
            direction=plan.direction,
            commission=fee,
            slippage_ticks=self.config.execution.slippage_ticks,
            reason="entry",
        )
        fraction = self.config.setup.first_target_fraction
        partial_quantity = int(quantity * fraction)
        partial_quantity -= partial_quantity % self.config.instrument.quantity_increment
        if partial_quantity >= quantity:
            partial_quantity = quantity - self.config.instrument.quantity_increment
        partial_quantity = max(0, partial_quantity)
        self.position = Position(
            signal_id=plan.signal_id,
            direction=plan.direction,
            quantity=quantity,
            remaining_quantity=quantity,
            entry_time=timestamp,
            entry_price=fill_price,
            chart_entry=chart_entry,
            stop_price=plan.raw_stop,
            target_1=plan.raw_target_1,
            target_2=plan.raw_target_2,
            partial_quantity=partial_quantity,
            entry_commission=fee,
            regime=plan.regime,
            fills=[fill],
        )
        self.events.append(
            BrokerEvent(
                timestamp,
                "position_opened",
                plan.signal_id,
                {"quantity": quantity, "fill": fill_price},
            )
        )
        return self.position

    def process_bar(self, bar: Bar, *, entry_bar: bool = False) -> Trade | None:
        position = self.position
        if position is None:
            return None
        self._update_excursions(position, bar)
        if self._stop_touched(position, bar):
            chart_price = self._stop_chart_fill(position, bar)
            self._exit_quantity(
                position, position.remaining_quantity, chart_price, bar.timestamp, "stop"
            )
            return self._finalize(position, bar.timestamp, ExitReason.STOP)
        if entry_bar:
            return None

        target_1_touched = self._target_touched(position.direction, position.target_1, bar)
        if not position.partial_taken and position.partial_quantity > 0 and target_1_touched:
            self._exit_quantity(
                position,
                position.partial_quantity,
                position.target_1,
                bar.timestamp,
                "target_1",
            )
            position.partial_taken = True
            position.stop_price = position.chart_entry
            self.events.append(
                BrokerEvent(
                    bar.timestamp,
                    "partial_and_break_even",
                    position.signal_id,
                    {"remaining": position.remaining_quantity, "new_stop": position.stop_price},
                )
            )
            # Conservative ordering after a partial: if the same bar also spans
            # the new break-even stop, assume the remainder was stopped.
            if self._stop_touched(position, bar):
                self._exit_quantity(
                    position,
                    position.remaining_quantity,
                    position.stop_price,
                    bar.timestamp,
                    "break_even_stop",
                )
                return self._finalize(position, bar.timestamp, ExitReason.STOP)
        if self._target_touched(position.direction, position.target_2, bar):
            self._exit_quantity(
                position,
                position.remaining_quantity,
                position.target_2,
                bar.timestamp,
                "target_2",
            )
            return self._finalize(position, bar.timestamp, ExitReason.TARGET)
        return None

    def force_close(self, bar: Bar, reason: ExitReason) -> Trade | None:
        position = self.position
        if position is None:
            return None
        self._update_excursions(position, bar)
        self._exit_quantity(
            position,
            position.remaining_quantity,
            bar.close,
            bar.timestamp,
            reason.value,
        )
        return self._finalize(position, bar.timestamp, reason)

    def unrealized_pnl(self, mark_price: float) -> float:
        position = self.position
        if position is None:
            return 0.0
        sign = position.direction.sign
        adverse_exit = self._adverse_price(mark_price, position.direction, entering=False)
        pnl = (
            (adverse_exit - position.entry_price)
            * sign
            * self.config.instrument.point_value
            * position.remaining_quantity
        )
        return pnl - self._fee(position.remaining_quantity)

    def _adverse_price(self, chart_price: float, direction: Direction, *, entering: bool) -> float:
        ticks = self.config.execution.spread_ticks / 2 + self.config.execution.slippage_ticks
        points = ticks * self.config.instrument.tick_size
        # Long entry buys higher; long exit sells lower. Short is opposite.
        sign = direction.sign if entering else -direction.sign
        return chart_price + sign * points

    def _fee(self, quantity: int) -> float:
        execution = self.config.execution
        return quantity * (
            execution.commission_per_contract_per_side
            + execution.exchange_fee_per_contract_per_side
        )

    @staticmethod
    def _target_touched(direction: Direction, target: float, bar: Bar) -> bool:
        return bar.high >= target if direction is Direction.LONG else bar.low <= target

    @staticmethod
    def _stop_touched(position: Position, bar: Bar) -> bool:
        return (
            bar.low <= position.stop_price
            if position.direction is Direction.LONG
            else bar.high >= position.stop_price
        )

    @staticmethod
    def _stop_chart_fill(position: Position, bar: Bar) -> float:
        if position.direction is Direction.LONG:
            return min(position.stop_price, bar.open)
        return max(position.stop_price, bar.open)

    def _update_excursions(self, position: Position, bar: Bar) -> None:
        if position.direction is Direction.LONG:
            adverse = max(0.0, position.entry_price - bar.low)
            favorable = max(0.0, bar.high - position.entry_price)
        else:
            adverse = max(0.0, bar.high - position.entry_price)
            favorable = max(0.0, position.entry_price - bar.low)
        position.mae_points = max(position.mae_points, adverse)
        position.mfe_points = max(position.mfe_points, favorable)

    def _exit_quantity(
        self,
        position: Position,
        quantity: int,
        chart_price: float,
        timestamp: datetime,
        reason: str,
    ) -> None:
        if quantity <= 0 or quantity > position.remaining_quantity:
            raise ValueError("invalid exit quantity")
        price = self._adverse_price(chart_price, position.direction, entering=False)
        fee = self._fee(quantity)
        sign = position.direction.sign
        position.realized_gross += (
            (chart_price - position.chart_entry)
            * sign
            * self.config.instrument.point_value
            * quantity
        )
        position.exit_commission += fee
        position.remaining_quantity -= quantity
        position.fills.append(
            Fill(
                timestamp=timestamp,
                price=price,
                chart_price=chart_price,
                quantity=quantity,
                direction=position.direction,
                commission=fee,
                slippage_ticks=self.config.execution.slippage_ticks,
                reason=reason,
            )
        )
        self.events.append(
            BrokerEvent(
                timestamp, reason, position.signal_id, {"quantity": quantity, "fill": price}
            )
        )

    def _finalize(self, position: Position, timestamp: datetime, reason: ExitReason) -> Trade:
        if position.remaining_quantity != 0:
            raise RuntimeError("cannot finalize a position with remaining quantity")
        exits = [fill for fill in position.fills if fill.reason != "entry"]
        exit_value = sum(fill.price * fill.quantity for fill in exits)
        average_exit = exit_value / position.quantity
        sign = position.direction.sign
        execution_pnl = sum(
            (fill.price - position.entry_price)
            * sign
            * self.config.instrument.point_value
            * fill.quantity
            for fill in exits
        )
        fees = position.entry_commission + position.exit_commission
        execution_costs = max(0.0, position.realized_gross - execution_pnl)
        costs = execution_costs + fees
        trade = Trade(
            signal_id=position.signal_id,
            direction=position.direction,
            quantity=position.quantity,
            entry_time=position.entry_time,
            exit_time=timestamp,
            entry_price=position.entry_price,
            average_exit_price=average_exit,
            gross_pnl=position.realized_gross,
            execution_costs=execution_costs,
            fees=fees,
            costs=costs,
            net_pnl=position.realized_gross - costs,
            exit_reason=reason,
            mae_points=position.mae_points,
            mfe_points=position.mfe_points,
            duration_seconds=(timestamp - position.entry_time).total_seconds(),
            regime=position.regime,
            fills=tuple(position.fills),
        )
        self.trades.append(trade)
        self.position = None
        self.events.append(
            BrokerEvent(timestamp, "position_closed", trade.signal_id, {"net_pnl": trade.net_pnl})
        )
        return trade
