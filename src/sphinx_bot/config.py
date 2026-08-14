"""Strict, dependency-free runtime configuration loading."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any, TypeVar, get_type_hints
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class InstrumentConfig:
    symbol: str = "NQ"
    tick_size: float = 0.25
    point_value: float = 20.0
    quantity_increment: int = 1
    max_contracts: int = 2


@dataclass(frozen=True)
class SessionConfig:
    timezone: str = "America/New_York"
    start: str = "00:00"
    end: str = "04:00"
    weekdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    force_flat_at_end: bool = True
    warmup_bars: int = 30


@dataclass(frozen=True)
class TimeframeConfig:
    execution_seconds: int = 120
    intermediate_seconds: tuple[int, ...] = (300, 900)
    context_seconds: tuple[int, ...] = (3600, 14400)


@dataclass(frozen=True)
class StructureConfig:
    method: str = "fixed"
    pivot_left_bars: int = 3
    pivot_right_bars: int = 3
    atr_period: int = 14
    atr_reversal_multiplier: float = 1.5
    percentage_reversal: float = 0.002
    equal_tolerance_ticks: float = 4.0
    regime_lookback: int = 20
    trend_efficiency_threshold: float = 0.45
    expansion_atr_ratio: float = 1.5


@dataclass(frozen=True)
class SetupConfig:
    consolidation_lookback: int = 12
    consolidation_max_atr: float = 2.0
    displacement_min_atr: float = 0.8
    breakout_buffer_ticks: float = 1.0
    max_retrace_bars: int = 12
    retest_tolerance_ticks: float = 1.0
    entry_confirmation: str = "touch"
    stop_mode: str = "fixed_or_pivotal"
    fixed_stop_ticks: float = 40.0
    pivotal_buffer_ticks: float = 1.0
    extension_multiple: float = 1.66
    first_target_fraction: float = 0.5
    minimum_rr: float = 1.0
    cooldown_bars: int = 3
    require_context_aoi: bool = False
    require_smt: bool = False
    fvg_min_ticks: float = 2.0
    max_aoi_age_bars: int = 120
    score_weights: dict[str, float] = field(
        default_factory=lambda: {
            "location": 0.25,
            "displacement": 0.25,
            "liquidity": 0.20,
            "context": 0.15,
            "freshness": 0.15,
        }
    )
    aoi_score_weights: dict[str, float] = field(
        default_factory=lambda: {
            "displacement": 0.30,
            "freshness": 0.30,
            "mitigation": 0.20,
            "interactions": 0.20,
        }
    )


@dataclass(frozen=True)
class LiquidityConfig:
    max_levels: int = 200
    equal_level_tolerance_ticks: float = 4.0
    sweep_excursion_ticks: float = 1.0
    sweep_reclaim_bars: int = 1
    min_target_distance_ticks: float = 4.0
    weights: dict[str, float] = field(
        default_factory=lambda: {
            "timeframe": 0.30,
            "touches": 0.20,
            "recency": 0.15,
            "equality": 0.15,
            "distance": 0.10,
            "session": 0.10,
        }
    )


@dataclass(frozen=True)
class RiskConfig:
    initial_equity: float = 100_000.0
    risk_per_trade_pct: float = 0.0025
    daily_loss_limit_pct: float = 0.01
    max_drawdown_pct: float = 0.05
    max_trades_per_session: int = 3
    max_consecutive_losses: int = 2
    loss_cooldown_minutes: int = 60
    max_notional_exposure: float = 500_000.0
    reject_after_count: int = 3
    flatten_on_critical_kill: bool = True


@dataclass(frozen=True)
class ExecutionConfig:
    spread_ticks: float = 1.0
    slippage_ticks: float = 1.0
    commission_per_contract_per_side: float = 2.50
    exchange_fee_per_contract_per_side: float = 0.35
    entry_delay_bars: int = 0
    same_bar_policy: str = "stop_first_no_favorable_exit"
    fill_mode: str = "trigger_market"
    max_spread_ticks: float = 4.0
    max_data_gap_seconds: int = 360


@dataclass(frozen=True)
class ResearchConfig:
    development_fraction: float = 0.60
    validation_fraction: float = 0.20
    holdout_fraction: float = 0.20
    minimum_bars_per_partition: int = 100
    strategy_frozen: bool = False
    random_seed: int = 44


@dataclass(frozen=True)
class LoggingConfig:
    output_directory: str = "artifacts"
    decisions_filename: str = "decisions.jsonl"
    trades_filename: str = "trades.jsonl"
    reports_directory: str = "reports"


@dataclass(frozen=True)
class StrategyConfig:
    version: str
    name: str
    paper_only: bool
    instrument: InstrumentConfig
    session: SessionConfig
    timeframes: TimeframeConfig
    structure: StructureConfig
    setup: SetupConfig
    liquidity: LiquidityConfig
    risk: RiskConfig
    execution: ExecutionConfig
    research: ResearchConfig
    logging: LoggingConfig

    def validate(self) -> None:
        errors: list[str] = []
        if not self.paper_only:
            errors.append("paper_only must remain true; no live-money adapter is implemented")
        if self.instrument.tick_size <= 0 or self.instrument.point_value <= 0:
            errors.append("tick_size and point_value must be positive")
        if self.timeframes.execution_seconds <= 0:
            errors.append("execution timeframe must be positive")
        if self.session.warmup_bars < self.setup.consolidation_lookback:
            errors.append("session warmup must cover consolidation lookback")
        try:
            ZoneInfo(self.session.timezone)
        except ZoneInfoNotFoundError:
            errors.append(f"unknown session timezone: {self.session.timezone}")
        for clock in (self.session.start, self.session.end):
            try:
                hour, minute = (int(value) for value in clock.split(":"))
                if not (0 <= hour <= 23 and 0 <= minute <= 59):
                    raise ValueError
            except ValueError:
                errors.append(f"invalid HH:MM time: {clock}")
        if not self.session.weekdays or any(day not in range(7) for day in self.session.weekdays):
            errors.append("session weekdays must contain values from 0 through 6")
        if self.structure.method not in {"fixed", "fractal", "atr", "percentage"}:
            errors.append("structure.method must be fixed, fractal, atr, or percentage")
        if (
            min(
                self.structure.pivot_left_bars,
                self.structure.pivot_right_bars,
                self.structure.atr_period,
                self.setup.consolidation_lookback,
                self.setup.max_retrace_bars,
            )
            <= 0
        ):
            errors.append("structure and setup lookbacks must be positive")
        if self.setup.entry_confirmation not in {"touch", "close_rejection"}:
            errors.append("entry_confirmation must be touch or close_rejection")
        if self.setup.stop_mode not in {"fixed", "pivotal", "fixed_or_pivotal"}:
            errors.append("unsupported stop mode")
        if not 0 < self.risk.risk_per_trade_pct <= 0.01:
            errors.append("risk_per_trade_pct must be in (0, 0.01]")
        if not 0 < self.risk.daily_loss_limit_pct <= self.risk.max_drawdown_pct:
            errors.append("daily loss must be positive and no greater than max drawdown")
        if self.setup.fixed_stop_ticks <= 0 or self.setup.extension_multiple <= 1:
            errors.append("stop ticks must be positive and extension_multiple must exceed one")
        if not 0 <= self.setup.first_target_fraction <= 1:
            errors.append("first_target_fraction must be in [0, 1]")
        fractions = (
            self.research.development_fraction,
            self.research.validation_fraction,
            self.research.holdout_fraction,
        )
        if any(value <= 0 for value in fractions) or abs(sum(fractions) - 1.0) > 1e-9:
            errors.append("research partition fractions must be positive and sum to one")
        for label, weights in (
            ("setup.score_weights", self.setup.score_weights),
            ("setup.aoi_score_weights", self.setup.aoi_score_weights),
            ("liquidity.weights", self.liquidity.weights),
        ):
            if (
                not weights
                or any(value < 0 for value in weights.values())
                or sum(weights.values()) <= 0
            ):
                errors.append(f"{label} must have nonnegative values and positive total weight")
        if self.execution.same_bar_policy != "stop_first_no_favorable_exit":
            errors.append("only conservative same-bar execution is supported")
        if self.execution.max_spread_ticks < self.execution.spread_ticks:
            errors.append("max spread cannot be below modeled spread")
        if self.risk.initial_equity <= 0 or self.risk.max_notional_exposure <= 0:
            errors.append("initial equity and maximum exposure must be positive")
        if errors:
            raise ValueError("invalid configuration:\n- " + "\n- ".join(errors))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


T = TypeVar("T")


def _construct(cls: type[T], values: dict[str, Any]) -> T:
    """Recursively build dataclasses while rejecting typo-prone unknown keys."""

    valid = {item.name for item in fields(cls)}
    unknown = set(values) - valid
    if unknown:
        raise ValueError(f"unknown keys for {cls.__name__}: {sorted(unknown)}")
    hints = get_type_hints(cls)
    kwargs: dict[str, Any] = {}
    for item in fields(cls):
        if item.name not in values:
            continue
        value = values[item.name]
        target = hints.get(item.name)
        if isinstance(target, type) and is_dataclass(target):
            if not isinstance(value, dict):
                raise TypeError(f"{item.name} must be an object")
            value = _construct(target, value)
        elif getattr(target, "__origin__", None) is tuple and isinstance(value, list):
            value = tuple(value)
        kwargs[item.name] = value
    return cls(**kwargs)


def load_config(path: str | Path) -> StrategyConfig:
    source = Path(path)
    with source.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    if not isinstance(raw, dict):
        raise TypeError("configuration root must be an object")
    config = _construct(StrategyConfig, raw)
    config.validate()
    return config
