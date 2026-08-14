"""Core immutable data contracts used by research and paper execution.

Prices in market-data bars are unadjusted chart/mid prices.  Execution costs are
applied by the broker simulator, never baked into strategy signals.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"

    @property
    def sign(self) -> int:
        return 1 if self is Direction.LONG else -1

    @property
    def opposite(self) -> Direction:
        return Direction.SHORT if self is Direction.LONG else Direction.LONG


class StrategyState(str, Enum):
    IDLE = "IDLE"
    SESSION_INITIALIZATION = "SESSION_INITIALIZATION"
    WAITING_FOR_LOCATION = "WAITING_FOR_LOCATION"
    TRACKING_IMPULSE = "TRACKING_IMPULSE"
    ENTRY_READY = "ENTRY_READY"
    POSITION_OPEN = "POSITION_OPEN"
    COOLDOWN = "COOLDOWN"
    DISABLED = "DISABLED"


class PivotKind(str, Enum):
    HIGH = "swing_high"
    LOW = "swing_low"


class StructureLabel(str, Enum):
    HIGHER_HIGH = "higher_high"
    LOWER_HIGH = "lower_high"
    HIGHER_LOW = "higher_low"
    LOWER_LOW = "lower_low"
    EQUAL_HIGH = "equal_high"
    EQUAL_LOW = "equal_low"


class Regime(str, Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    EXPANSION = "expansion"
    UNKNOWN = "unknown"


class LiquiditySide(str, Enum):
    BUY_SIDE = "buy_side"
    SELL_SIDE = "sell_side"


class LiquidityScope(str, Enum):
    INTERNAL = "internal"
    EXTERNAL = "external"


class ZoneKind(str, Enum):
    BULLISH_FVG = "bullish_fvg"
    BEARISH_FVG = "bearish_fvg"
    BULLISH_IFVG = "bullish_ifvg"
    BEARISH_IFVG = "bearish_ifvg"
    DEALING_RANGE = "dealing_range"


class ExitReason(str, Enum):
    STOP = "stop"
    TARGET = "target"
    SESSION_END = "session_end"
    KILL_SWITCH = "kill_switch"
    END_OF_DATA = "end_of_data"
    MANUAL = "manual"


class KillReason(str, Enum):
    STALE_DATA = "stale_data"
    ABNORMAL_SPREAD = "abnormal_spread"
    EXECUTION_ERROR = "execution_error"
    POSITION_MISMATCH = "position_mismatch"
    RISK_CALCULATION_FAILURE = "risk_calculation_failure"
    DAILY_LOSS_LIMIT = "daily_loss_limit"
    WEEKLY_LOSS_LIMIT = "weekly_loss_limit"
    MAX_DRAWDOWN = "max_drawdown"
    REPEATED_REJECTION = "repeated_order_rejection"
    INVALID_DATA = "invalid_data"
    UNEXPECTED_ACCOUNT_STATE = "unexpected_account_state"


@dataclass(frozen=True, slots=True)
class Bar:
    """A completed OHLCV bar with an aware UTC timestamp at bar open."""

    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    symbol: str = "NQ"
    interval_seconds: int = 120

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("bar timestamp must be timezone-aware")
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(isinstance(value, (int, float)) for value in values):
            raise TypeError("OHLCV fields must be numeric")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("bar high is below another OHLC value")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("bar low is above another OHLC value")
        if self.volume < 0:
            raise ValueError("volume cannot be negative")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def range(self) -> float:
        return self.high - self.low

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["timestamp"] = self.timestamp.isoformat()
        return result


@dataclass(frozen=True, slots=True)
class Pivot:
    kind: PivotKind
    price: float
    occurred_at: datetime
    confirmed_at: datetime
    method: str
    strength: float = 1.0
    label: StructureLabel | None = None


@dataclass(slots=True)
class LiquidityLevel:
    id: str
    price: float
    type: str
    side: LiquiditySide
    timeframe: str
    strength: float
    touch_count: int
    created_at: datetime
    confirmed_at: datetime
    distance_from_price: float = 0.0
    swept: bool = False
    consumed: bool = False
    active: bool = True
    scope: LiquidityScope = LiquidityScope.EXTERNAL
    last_touched_at: datetime | None = None
    source_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("side", "scope"):
            result[key] = result[key].value
        for key in ("created_at", "confirmed_at", "last_touched_at"):
            if result[key] is not None:
                result[key] = result[key].isoformat()
        return result


@dataclass(slots=True)
class AreaOfInterest:
    id: str
    kind: ZoneKind
    lower: float
    upper: float
    midpoint: float
    timeframe: str
    created_at: datetime
    confirmed_at: datetime
    age_bars: int = 0
    interactions: int = 0
    fill_fraction: float = 0.0
    partially_filled: bool = False
    fully_mitigated: bool = False
    invalidated: bool = False
    confluence_score: float = 0.0


@dataclass(frozen=True, slots=True)
class StructureSnapshot:
    timestamp: datetime
    trend: Direction | None
    regime: Regime
    latest_high: Pivot | None
    latest_low: Pivot | None
    break_of_structure: Direction | None = None
    market_structure_shift: Direction | None = None


@dataclass(frozen=True, slots=True)
class Consolidation:
    started_at: datetime
    ended_at: datetime
    low: float
    high: float
    atr: float
    bar_count: int

    @property
    def width(self) -> float:
        return self.high - self.low


@dataclass(slots=True)
class SetupPlan:
    signal_id: str
    created_at: datetime
    direction: Direction
    raw_entry: float
    raw_stop: float
    raw_target_1: float
    raw_target_2: float
    setup_score: float
    passed_conditions: list[str]
    failed_conditions: list[str]
    evidence: dict[str, str]
    impulse_origin: float
    impulse_extreme: float
    valid_until: datetime | None = None
    liquidity_target_id: str | None = None
    regime: Regime = Regime.UNKNOWN
    source_state: StrategyState = StrategyState.ENTRY_READY

    @property
    def expected_rr(self) -> float:
        risk = abs(self.raw_entry - self.raw_stop)
        return abs(self.raw_target_2 - self.raw_entry) / risk if risk else 0.0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("direction", "regime", "source_state"):
            result[key] = result[key].value
        for key in ("created_at", "valid_until"):
            if result[key] is not None:
                result[key] = result[key].isoformat()
        result["expected_rr"] = self.expected_rr
        return result


@dataclass(frozen=True, slots=True)
class Fill:
    timestamp: datetime
    price: float
    chart_price: float
    quantity: int
    direction: Direction
    commission: float
    slippage_ticks: float
    reason: str


@dataclass(slots=True)
class Position:
    signal_id: str
    direction: Direction
    quantity: int
    remaining_quantity: int
    entry_time: datetime
    entry_price: float
    chart_entry: float
    stop_price: float
    target_1: float
    target_2: float
    partial_quantity: int
    entry_commission: float
    regime: Regime = Regime.UNKNOWN
    partial_taken: bool = False
    realized_gross: float = 0.0
    exit_commission: float = 0.0
    mae_points: float = 0.0
    mfe_points: float = 0.0
    fills: list[Fill] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class Trade:
    signal_id: str
    direction: Direction
    quantity: int
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    average_exit_price: float
    gross_pnl: float
    execution_costs: float
    fees: float
    costs: float
    net_pnl: float
    exit_reason: ExitReason
    mae_points: float
    mfe_points: float
    duration_seconds: float
    regime: Regime
    fills: tuple[Fill, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        for key in ("direction", "exit_reason", "regime"):
            result[key] = result[key].value
        result["entry_time"] = self.entry_time.isoformat()
        result["exit_time"] = self.exit_time.isoformat()
        result["fills"] = [
            {
                **asdict(fill),
                "timestamp": fill.timestamp.isoformat(),
                "direction": fill.direction.value,
            }
            for fill in self.fills
        ]
        return result


@dataclass(frozen=True, slots=True)
class Decision:
    timestamp: datetime
    state: StrategyState
    event: str
    accepted: bool
    reasons: tuple[str, ...]
    signal_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "state": self.state.value,
            "event": self.event,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "signal_id": self.signal_id,
            "details": self.details,
        }
