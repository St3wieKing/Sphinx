"""Bounded, anti-overfit research suite for NQ and MNQ.

The suite never opens the final holdout. It produces development, validation,
walk-forward, execution, risk, sensitivity, and bootstrap evidence without
selecting a winner automatically.
"""

from __future__ import annotations

import hashlib
import random
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from statistics import mean, median, pstdev
from typing import Any
from zoneinfo import ZoneInfo

from ..config import StrategyConfig
from ..data.csv_feed import inspect_data
from ..data.split import chronological_split, expanding_walk_forward
from ..models import Bar, Trade
from .backtest import BacktestEngine, BacktestResult
from .stress import run_execution_scenarios


@dataclass(frozen=True)
class SensitivityCase:
    case_id: str
    hypothesis: str
    parameter: str
    value: int | float
    config: StrategyConfig


def _metrics_summary(result: BacktestResult) -> dict[str, object]:
    keys = (
        "trade_count",
        "gross_pnl_before_costs",
        "total_costs",
        "net_pnl_after_costs",
        "win_rate",
        "expectancy_per_trade",
        "profit_factor",
        "maximum_drawdown",
        "maximum_consecutive_losses",
        "average_mae_points",
        "average_mfe_points",
        "by_entry_hour",
        "by_direction",
        "by_regime",
    )
    return {key: result.metrics.get(key) for key in keys}


def _trade_months(trades: Sequence[Trade], timezone_name: str) -> dict[str, dict[str, float | int]]:
    zone = ZoneInfo(timezone_name)
    grouped: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        month = trade.entry_time.astimezone(zone).strftime("%Y-%m")
        grouped[month].append(trade)
    return {
        month: {
            "trades": len(values),
            "net_pnl": sum(trade.net_pnl for trade in values),
            "gross_pnl": sum(trade.gross_pnl for trade in values),
            "costs": sum(trade.costs for trade in values),
            "win_rate": sum(trade.net_pnl > 0 for trade in values) / len(values),
            "expectancy": mean(trade.net_pnl for trade in values),
        }
        for month, values in sorted(grouped.items())
    }


def _session_hours(
    trades: Sequence[Trade], timezone_name: str
) -> dict[str, dict[str, float | int]]:
    zone = ZoneInfo(timezone_name)
    grouped: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        grouped[f"{trade.entry_time.astimezone(zone).hour:02d}:00"].append(trade)
    return {
        hour: {
            "trades": len(values),
            "net_pnl": sum(trade.net_pnl for trade in values),
            "win_rate": sum(trade.net_pnl > 0 for trade in values) / len(values),
            "expectancy": mean(trade.net_pnl for trade in values),
        }
        for hour, values in sorted(grouped.items())
    }


def bootstrap_expectancy(
    trades: Sequence[Trade], simulations: int = 2_000, seed: int = 44
) -> dict[str, object]:
    """Non-parametric confidence diagnostic for average net trade outcome."""

    if not trades:
        return {
            "simulations": simulations,
            "sample_trades": 0,
            "mean": None,
            "p05": None,
            "p50": None,
            "p95": None,
            "probability_positive": None,
        }
    rng = random.Random(seed)
    outcomes = [trade.net_pnl for trade in trades]
    estimates = [mean(rng.choice(outcomes) for _ in outcomes) for _ in range(simulations)]
    estimates.sort()

    def percentile(probability: float) -> float:
        position = (len(estimates) - 1) * probability
        lower = int(position)
        upper = min(lower + 1, len(estimates) - 1)
        weight = position - lower
        return estimates[lower] * (1 - weight) + estimates[upper] * weight

    return {
        "simulations": simulations,
        "sample_trades": len(trades),
        "mean": mean(estimates),
        "p05": percentile(0.05),
        "p50": percentile(0.50),
        "p95": percentile(0.95),
        "probability_positive": sum(value > 0 for value in estimates) / len(estimates),
        "warning": "Bootstrap resamples observed trades; it does not create unseen regimes.",
    }


def sensitivity_cases(config: StrategyConfig) -> tuple[SensitivityCase, ...]:
    """One-factor-at-a-time neighbors; no combinatorial curve fitting."""

    setup = config.setup
    structure = config.structure
    return (
        SensitivityCase(
            "SENS-CONS-08",
            "Shorter consolidation memory may react faster without losing location quality.",
            "setup.consolidation_lookback",
            8,
            replace(config, setup=replace(setup, consolidation_lookback=8)),
        ),
        SensitivityCase(
            "SENS-CONS-16",
            "Longer consolidation memory may reduce noisy breakouts.",
            "setup.consolidation_lookback",
            16,
            replace(config, setup=replace(setup, consolidation_lookback=16)),
        ),
        SensitivityCase(
            "SENS-DISP-060",
            "A lower displacement threshold may increase frequency at a quality cost.",
            "setup.displacement_min_atr",
            0.6,
            replace(config, setup=replace(setup, displacement_min_atr=0.6)),
        ),
        SensitivityCase(
            "SENS-DISP-100",
            "A higher displacement threshold may filter weak breaks.",
            "setup.displacement_min_atr",
            1.0,
            replace(config, setup=replace(setup, displacement_min_atr=1.0)),
        ),
        SensitivityCase(
            "SENS-STOP-32",
            "A 32-tick cap may improve nominal R but increase invalidations.",
            "setup.fixed_stop_ticks",
            32,
            replace(config, setup=replace(setup, fixed_stop_ticks=32)),
        ),
        SensitivityCase(
            "SENS-STOP-48",
            "A 48-tick cap may survive noise but lower quantity/R.",
            "setup.fixed_stop_ticks",
            48,
            replace(config, setup=replace(setup, fixed_stop_ticks=48)),
        ),
        SensitivityCase(
            "SENS-PIVOT-2",
            "A shorter delayed pivot may map liquidity more responsively.",
            "structure.pivot_left_right_bars",
            2,
            replace(
                config,
                structure=replace(structure, pivot_left_bars=2, pivot_right_bars=2),
            ),
        ),
        SensitivityCase(
            "SENS-PIVOT-4",
            "A longer delayed pivot may map cleaner liquidity.",
            "structure.pivot_left_right_bars",
            4,
            replace(
                config,
                structure=replace(structure, pivot_left_bars=4, pivot_right_bars=4),
            ),
        ),
    )


def _dataset_fingerprint(bars: Sequence[Bar]) -> str:
    digest = hashlib.sha256()
    for bar in bars:
        digest.update(
            f"{bar.timestamp.isoformat()}|{bar.open}|{bar.high}|{bar.low}|{bar.close}|{bar.volume}\n".encode()
        )
    return digest.hexdigest()


class DeepResearchSuite:
    def __init__(self, config: StrategyConfig, bootstrap_simulations: int = 2_000) -> None:
        self.config = config
        self.bootstrap_simulations = bootstrap_simulations

    def run(self, bars: Sequence[Bar]) -> dict[str, object]:
        minimum = self.config.research.minimum_bars_per_partition
        split = chronological_split(
            bars,
            self.config.research.development_fraction,
            self.config.research.validation_fraction,
            self.config.research.holdout_fraction,
            minimum,
        )
        quality = inspect_data(
            bars,
            expected_interval_seconds=self.config.timeframes.execution_seconds,
            max_gap_seconds=self.config.execution.max_data_gap_seconds,
        )
        development = BacktestEngine(self.config).run(split.development)
        validation = BacktestEngine(self.config).run(split.validation)

        execution = run_execution_scenarios(self.config, split.validation)
        execution_summary = {name: _metrics_summary(result) for name, result in execution.items()}

        risk_runs: dict[str, dict[str, object]] = {}
        for risk_pct in (0.001, 0.0025, 0.005):
            candidate = replace(
                self.config,
                risk=replace(self.config.risk, risk_per_trade_pct=risk_pct),
            )
            result = BacktestEngine(candidate).run(split.validation)
            risk_runs[f"{risk_pct:.4f}"] = _metrics_summary(result)

        sensitivities: list[dict[str, object]] = []
        for case in sensitivity_cases(self.config):
            case.config.validate()
            result = BacktestEngine(case.config).run(split.development)
            sensitivities.append(
                {
                    "case_id": case.case_id,
                    "hypothesis": case.hypothesis,
                    "parameter": case.parameter,
                    "value": case.value,
                    "config_fingerprint": case.config.fingerprint,
                    "metrics": _metrics_summary(result),
                }
            )

        first_eighty = tuple(split.development) + tuple(split.validation)
        initial = max(minimum, int(len(first_eighty) * 0.40))
        validation_size = max(minimum, int(len(first_eighty) * 0.10))
        folds = expanding_walk_forward(first_eighty, initial, validation_size)
        walk_forward: list[dict[str, object]] = []
        for fold in folds:
            # No fitting is performed; this measures the frozen baseline on
            # successive unseen windows after an expanding observation history.
            result = BacktestEngine(self.config).run(fold.validation)
            walk_forward.append(
                {
                    "fold": fold.fold,
                    "development_bars_observed": len(fold.development),
                    "validation_bars": len(fold.validation),
                    "start": fold.validation[0].timestamp.isoformat(),
                    "end": fold.validation[-1].timestamp.isoformat(),
                    "metrics": _metrics_summary(result),
                }
            )

        sensitivity_expectancies = [
            item["metrics"]["expectancy_per_trade"]
            for item in sensitivities
            if item["metrics"]["expectancy_per_trade"] is not None
        ]
        sensitivity_stability = {
            "cases_with_trades": len(sensitivity_expectancies),
            "median_expectancy": median(sensitivity_expectancies)
            if sensitivity_expectancies
            else None,
            "expectancy_dispersion": pstdev(sensitivity_expectancies)
            if len(sensitivity_expectancies) > 1
            else None,
            "positive_case_fraction": (
                sum(value > 0 for value in sensitivity_expectancies) / len(sensitivity_expectancies)
                if sensitivity_expectancies
                else None
            ),
        }

        warnings: list[str] = []
        if len(validation.trades) < 100:
            warnings.append("Validation contains fewer than 100 trades; inference is weak.")
        if quality.large_gaps:
            warnings.append(
                f"Dataset has {quality.large_gaps} gaps above the configured threshold; verify session closures."
            )
        if validation.metrics["expectancy_per_trade"] is None:
            warnings.append("Validation produced no trades.")
        warnings.append("Final 20% holdout was not opened by this suite.")

        return {
            "suite_version": "1.0",
            "generated_at": datetime.now().astimezone().isoformat(),
            "instrument": self.config.instrument.symbol,
            "status": "RESEARCH_ONLY_NO_PROFITABILITY_CLAIM",
            "config_fingerprint": self.config.fingerprint,
            "data": {
                **asdict(quality),
                "first_timestamp": quality.first_timestamp.isoformat()
                if quality.first_timestamp
                else None,
                "last_timestamp": quality.last_timestamp.isoformat()
                if quality.last_timestamp
                else None,
                "dataset_fingerprint": _dataset_fingerprint(bars),
                "development_bars": len(split.development),
                "validation_bars": len(split.validation),
                "holdout_bars_locked": len(split.holdout),
            },
            "development": {
                "metrics": _metrics_summary(development),
                "by_month": _trade_months(development.trades, self.config.session.timezone),
                "by_session_hour": _session_hours(development.trades, self.config.session.timezone),
            },
            "validation": {
                "metrics": _metrics_summary(validation),
                "by_month": _trade_months(validation.trades, self.config.session.timezone),
                "by_session_hour": _session_hours(validation.trades, self.config.session.timezone),
                "expectancy_bootstrap": bootstrap_expectancy(
                    validation.trades,
                    self.bootstrap_simulations,
                    self.config.research.random_seed,
                ),
            },
            "execution_scenarios_on_validation": execution_summary,
            "risk_scenarios_on_validation": risk_runs,
            "one_factor_sensitivity_on_development": sensitivities,
            "sensitivity_stability": sensitivity_stability,
            "walk_forward_baseline": walk_forward,
            "holdout": {
                "opened": False,
                "bars_locked": len(split.holdout),
                "reason": "Strategy is not frozen; suite intentionally stops before holdout.",
            },
            "warnings": warnings,
        }


def paired_instrument_summary(reports: dict[str, dict[str, Any]]) -> dict[str, object]:
    """Compare NQ/MNQ validation outcomes without claiming independence."""

    summaries: dict[str, object] = {}
    for symbol, report in reports.items():
        summaries[symbol] = report["validation"]["metrics"]
    return {
        "instruments": summaries,
        "independence_warning": (
            "NQ and MNQ track the same Nasdaq-100 exposure. Treat them as execution/sizing variants, "
            "not independent strategy confirmations."
        ),
    }
