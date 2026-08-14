"""Reproducible trade-sequence and execution Monte Carlo stress tests."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import mean

from ..models import Trade


@dataclass(frozen=True)
class MonteCarloConfig:
    simulations: int = 2_000
    missed_trade_probability: float = 0.10
    extra_slippage_ticks_min: float = 0.0
    extra_slippage_ticks_max: float = 2.0
    cost_multiplier: float = 1.25
    ruin_drawdown_fraction: float = 0.20
    seed: int = 44


DEFAULT_MONTE_CARLO_CONFIG = MonteCarloConfig()


@dataclass(frozen=True)
class MonteCarloResult:
    simulations: int
    terminal_pnl_percentiles: dict[str, float]
    max_drawdown_percentiles: dict[str, float]
    probability_of_loss: float
    probability_of_ruin_drawdown: float
    mean_max_losing_streak: float
    worst_max_losing_streak: int
    assumptions: dict[str, float]

    def to_dict(self) -> dict[str, object]:
        return {
            "simulations": self.simulations,
            "terminal_pnl_percentiles": self.terminal_pnl_percentiles,
            "max_drawdown_percentiles": self.max_drawdown_percentiles,
            "probability_of_loss": self.probability_of_loss,
            "probability_of_ruin_drawdown": self.probability_of_ruin_drawdown,
            "mean_max_losing_streak": self.mean_max_losing_streak,
            "worst_max_losing_streak": self.worst_max_losing_streak,
            "assumptions": self.assumptions,
        }


def _percentile(values: list[float], probability: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = (len(ordered) - 1) * probability
    lower = int(index)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = index - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def run_monte_carlo(
    trades: Sequence[Trade],
    *,
    initial_equity: float,
    tick_size: float,
    point_value: float,
    config: MonteCarloConfig = DEFAULT_MONTE_CARLO_CONFIG,
) -> MonteCarloResult:
    if config.simulations <= 0:
        raise ValueError("simulations must be positive")
    if not 0 <= config.missed_trade_probability < 1:
        raise ValueError("missed_trade_probability must be in [0,1)")
    if not trades:
        raise ValueError("Monte Carlo requires observed backtest trades")
    rng = random.Random(config.seed)
    terminals: list[float] = []
    drawdowns: list[float] = []
    streaks: list[int] = []
    ruined = 0
    losses = 0
    for _ in range(config.simulations):
        sequence = list(trades)
        rng.shuffle(sequence)
        equity = initial_equity
        peak = equity
        max_drawdown = 0.0
        streak = 0
        max_streak = 0
        for trade in sequence:
            if rng.random() < config.missed_trade_probability:
                continue
            extra_ticks = rng.uniform(
                config.extra_slippage_ticks_min,
                config.extra_slippage_ticks_max,
            )
            round_trip_execution_penalty = (
                2 * extra_ticks * tick_size * point_value * trade.quantity
            )
            extra_historical_cost = trade.costs * (config.cost_multiplier - 1)
            outcome = trade.net_pnl - round_trip_execution_penalty - extra_historical_cost
            equity += outcome
            peak = max(peak, equity)
            drawdown = (peak - equity) / peak if peak else 1.0
            max_drawdown = max(max_drawdown, drawdown)
            streak = streak + 1 if outcome < 0 else 0
            max_streak = max(max_streak, streak)
        terminal = equity - initial_equity
        terminals.append(terminal)
        drawdowns.append(max_drawdown)
        streaks.append(max_streak)
        losses += terminal < 0
        ruined += max_drawdown >= config.ruin_drawdown_fraction or equity <= 0
    labels = (("p05", 0.05), ("p25", 0.25), ("p50", 0.50), ("p75", 0.75), ("p95", 0.95))
    return MonteCarloResult(
        simulations=config.simulations,
        terminal_pnl_percentiles={key: _percentile(terminals, value) for key, value in labels},
        max_drawdown_percentiles={key: _percentile(drawdowns, value) for key, value in labels},
        probability_of_loss=losses / config.simulations,
        probability_of_ruin_drawdown=ruined / config.simulations,
        mean_max_losing_streak=mean(streaks),
        worst_max_losing_streak=max(streaks),
        assumptions={
            "missed_trade_probability": config.missed_trade_probability,
            "extra_slippage_ticks_min": config.extra_slippage_ticks_min,
            "extra_slippage_ticks_max": config.extra_slippage_ticks_max,
            "cost_multiplier": config.cost_multiplier,
            "ruin_drawdown_fraction": config.ruin_drawdown_fraction,
            "seed": float(config.seed),
        },
    )
