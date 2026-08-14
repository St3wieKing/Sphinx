"""Performance metrics with explicit empty/undefined handling."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime
from itertools import pairwise
from statistics import mean, pstdev

from ..models import Trade


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _drawdowns(equity: Sequence[tuple[datetime, float]]) -> tuple[float, float]:
    if not equity:
        return 0.0, 0.0
    peak = equity[0][1]
    max_dd = 0.0
    drawdowns: list[float] = []
    for _, value in equity:
        peak = max(peak, value)
        dd = (peak - value) / peak if peak else 0.0
        drawdowns.append(dd)
        max_dd = max(max_dd, dd)
    return max_dd, mean(drawdowns)


def _daily_returns(equity: Sequence[tuple[datetime, float]]) -> list[float]:
    closes: dict[str, float] = {}
    for timestamp, value in equity:
        closes[timestamp.date().isoformat()] = value
    values = list(closes.values())
    return [current / previous - 1 for previous, current in pairwise(values) if previous]


def _group_summary(trades: Iterable[Trade]) -> dict[str, float | int | None]:
    values = list(trades)
    wins = [trade for trade in values if trade.net_pnl > 0]
    losses = [trade for trade in values if trade.net_pnl < 0]
    net = sum(trade.net_pnl for trade in values)
    gross_wins = sum(trade.net_pnl for trade in wins)
    gross_losses = abs(sum(trade.net_pnl for trade in losses))
    return {
        "trades": len(values),
        "net_pnl": net,
        "win_rate": len(wins) / len(values) if values else None,
        "expectancy": net / len(values) if values else None,
        "profit_factor": _safe_ratio(gross_wins, gross_losses),
    }


def performance_metrics(
    trades: Sequence[Trade],
    initial_equity: float,
    equity_curve: Sequence[tuple[datetime, float]],
) -> dict[str, object]:
    wins = [trade for trade in trades if trade.net_pnl > 0]
    losses = [trade for trade in trades if trade.net_pnl < 0]
    breakeven = [trade for trade in trades if trade.net_pnl == 0]
    net = sum(trade.net_pnl for trade in trades)
    gross_before_costs = sum(trade.gross_pnl for trade in trades)
    total_costs = sum(trade.costs for trade in trades)
    execution_costs = sum(trade.execution_costs for trade in trades)
    fees = sum(trade.fees for trade in trades)
    ending_equity = initial_equity + net
    total_return = net / initial_equity if initial_equity else None
    max_dd, average_dd = _drawdowns(equity_curve)

    days = 0.0
    if equity_curve:
        days = (equity_curve[-1][0] - equity_curve[0][0]).total_seconds() / 86400
    annualized = None
    # Annualizing a few intraday observations is misleading and numerically
    # unstable; report it only for samples spanning at least 30 calendar days.
    if days >= 30 and initial_equity > 0 and ending_equity > 0:
        annualized = (ending_equity / initial_equity) ** (365.0 / days) - 1
    daily = _daily_returns(equity_curve)
    sharpe = None
    if len(daily) >= 2 and pstdev(daily) > 0:
        sharpe = mean(daily) / pstdev(daily) * math.sqrt(252)
    downside = [min(0.0, value) for value in daily]
    sortino = None
    if len(downside) >= 2 and pstdev(downside) > 0:
        sortino = mean(daily) / pstdev(downside) * math.sqrt(252)

    consecutive = 0
    maximum_consecutive = 0
    for trade in trades:
        consecutive = consecutive + 1 if trade.net_pnl < 0 else 0
        maximum_consecutive = max(maximum_consecutive, consecutive)
    unique_days = {trade.entry_time.date() for trade in trades}
    win_rate = len(wins) / len(trades) if trades else None
    loss_rate = len(losses) / len(trades) if trades else None
    average_win = mean(trade.net_pnl for trade in wins) if wins else None
    average_loss = abs(mean(trade.net_pnl for trade in losses)) if losses else None
    expectancy_formula = None
    if win_rate is not None and loss_rate is not None:
        expectancy_formula = win_rate * (average_win or 0.0) - loss_rate * (average_loss or 0.0)

    grouped_hour: dict[str, list[Trade]] = defaultdict(list)
    grouped_direction: dict[str, list[Trade]] = defaultdict(list)
    grouped_regime: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        grouped_hour[f"{trade.entry_time.hour:02d}:00"].append(trade)
        grouped_direction[trade.direction.value].append(trade)
        grouped_regime[trade.regime.value].append(trade)

    gross_wins = sum(trade.net_pnl for trade in wins)
    gross_losses = abs(sum(trade.net_pnl for trade in losses))
    return {
        "initial_equity": initial_equity,
        "ending_equity": ending_equity,
        "total_return": total_return,
        "annualized_return": annualized,
        "gross_pnl_before_costs": gross_before_costs,
        "net_pnl_after_costs": net,
        "total_costs": total_costs,
        "execution_costs": execution_costs,
        "fees": fees,
        "trade_count": len(trades),
        "win_count": len(wins),
        "loss_count": len(losses),
        "breakeven_count": len(breakeven),
        "win_rate": win_rate,
        "loss_rate": loss_rate,
        "average_win": average_win,
        "average_loss": average_loss,
        "expectancy_per_trade": net / len(trades) if trades else None,
        "expectancy_formula": expectancy_formula,
        "profit_factor": _safe_ratio(gross_wins, gross_losses),
        "maximum_drawdown": max_dd,
        "average_drawdown": average_dd,
        "sharpe_daily": sharpe,
        "sortino_daily": sortino,
        "recovery_factor": _safe_ratio(total_return or 0.0, max_dd),
        "maximum_consecutive_losses": maximum_consecutive,
        "average_trade_duration_seconds": mean(trade.duration_seconds for trade in trades)
        if trades
        else None,
        "trades_per_active_day": len(trades) / len(unique_days) if unique_days else None,
        "average_mae_points": mean(trade.mae_points for trade in trades) if trades else None,
        "average_mfe_points": mean(trade.mfe_points for trade in trades) if trades else None,
        "by_entry_hour": {
            key: _group_summary(value) for key, value in sorted(grouped_hour.items())
        },
        "by_direction": {
            key: _group_summary(value) for key, value in sorted(grouped_direction.items())
        },
        "by_regime": {key: _group_summary(value) for key, value in sorted(grouped_regime.items())},
    }
