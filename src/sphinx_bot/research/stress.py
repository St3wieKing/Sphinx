"""Execution-scenario backtests without parameter optimization."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace

from ..config import StrategyConfig
from ..models import Bar
from .backtest import BacktestEngine, BacktestResult


def scenario_configs(config: StrategyConfig) -> dict[str, StrategyConfig]:
    base = config.execution
    return {
        "optimistic": replace(
            config,
            execution=replace(
                base,
                spread_ticks=max(0.5, base.spread_ticks * 0.5),
                slippage_ticks=0.0,
            ),
        ),
        "base": config,
        "pessimistic": replace(
            config,
            execution=replace(
                base,
                spread_ticks=max(2.0, base.spread_ticks * 2),
                slippage_ticks=max(2.0, base.slippage_ticks * 2),
                commission_per_contract_per_side=base.commission_per_contract_per_side * 1.5,
                exchange_fee_per_contract_per_side=base.exchange_fee_per_contract_per_side * 1.25,
                entry_delay_bars=max(1, base.entry_delay_bars),
            ),
        ),
    }


def run_execution_scenarios(
    config: StrategyConfig, bars: Sequence[Bar]
) -> dict[str, BacktestResult]:
    return {
        name: BacktestEngine(candidate).run(bars)
        for name, candidate in scenario_configs(config).items()
    }
