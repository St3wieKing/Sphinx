"""Ground-up liquidity/rejection event lab with causal probability calibration.

This module is research-only.  It deliberately does not route orders or replace
an active strategy.  "Liquidity" means an OHLCV price-action proxy; historical
bars cannot reveal the live limit order book or actual stop inventory.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import date, datetime, time
from statistics import mean, pstdev
from typing import Any
from zoneinfo import ZoneInfo

from ..config import StrategyConfig
from ..models import Bar, Direction, PivotKind
from ..strategy.market_structure import FixedPivotDetector, RollingATR

TARGETS = (1.0, 1.5, 2.0, 3.0, 4.0)
MODEL_NAMES = (
    "A_BASIC_REJECTION",
    "B_CONFIRMED_CLOSE",
    "C_STRUCTURE_SHIFT",
    "D_HTF_LEVEL",
    "E_DISPLACEMENT",
)
FEATURE_NAMES = (
    "direction_long",
    "model_basic",
    "model_confirmed",
    "model_structure",
    "model_htf",
    "model_displacement",
    "wick_fraction",
    "wick_atr",
    "body_fraction",
    "sweep_atr",
    "reclaim_atr",
    "level_age_scaled",
    "cluster_scaled",
    "volume_z",
    "trend_efficiency",
    "atr_ratio",
    "confirmation_strength",
    "hour_sin",
    "hour_cos",
    "session_new_york",
)


@dataclass
class ProxyLevel:
    price: float
    side: str  # high or low
    kind: str
    created_index: int
    available_index: int
    cluster_count: int = 1
    active: bool = True


@dataclass
class BaseSweep:
    index: int
    direction: Direction
    level: ProxyLevel
    extreme: float
    features: dict[str, float]
    session: str


@dataclass
class CandidateEvent:
    base_index: int
    signal_index: int
    model: str
    direction: Direction
    entry: float
    stop: float
    session: str
    features: tuple[float, ...]
    outcomes: dict[str, int]
    net_r: dict[str, float]
    exit_indices: dict[str, int]
    cost_r: float


@dataclass
class LogisticModel:
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    calibration_intercept: float
    calibration_slope: float

    def raw_logit(self, values: tuple[float, ...]) -> float:
        standardized = [
            (value - center) / scale
            for value, center, scale in zip(values, self.means, self.scales, strict=True)
        ]
        return self.weights[0] + sum(
            weight * value for weight, value in zip(self.weights[1:], standardized, strict=True)
        )

    def predict(self, values: tuple[float, ...]) -> float:
        raw = self.raw_logit(values)
        return _sigmoid(self.calibration_intercept + self.calibration_slope * raw)


def _sigmoid(value: float) -> float:
    if value >= 0:
        inverse = math.exp(-min(value, 50.0))
        return 1.0 / (1.0 + inverse)
    exponential = math.exp(max(value, -50.0))
    return exponential / (1.0 + exponential)


def _fit_linear_logistic(
    rows: list[tuple[float, ...]], labels: list[int], *, l2: float = 0.1
) -> LogisticModel:
    if not rows or len(set(labels)) < 2:
        probability = (sum(labels) + 1.0) / (len(labels) + 2.0)
        intercept = math.log(probability / (1 - probability))
        width = len(rows[0]) if rows else len(FEATURE_NAMES)
        return LogisticModel((0.0,) * width, (1.0,) * width, (intercept,) + (0.0,) * width, 0, 1)
    columns = list(zip(*rows, strict=True))
    centers = tuple(mean(column) for column in columns)
    scales = tuple(pstdev(column) or 1.0 for column in columns)
    standardized = [
        tuple((value - center) / scale for value, center, scale in zip(row, centers, scales))
        for row in rows
    ]
    base = (sum(labels) + 0.5) / (len(labels) + 1.0)
    weights = [math.log(base / (1 - base))] + [0.0] * len(centers)
    learning_rate = 0.08
    for iteration in range(700):
        gradient = [0.0] * len(weights)
        for row, label in zip(standardized, labels, strict=True):
            estimate = _sigmoid(weights[0] + sum(w * x for w, x in zip(weights[1:], row)))
            error = estimate - label
            gradient[0] += error
            for position, value in enumerate(row, start=1):
                gradient[position] += error * value
        count = len(rows)
        gradient[0] /= count
        for position in range(1, len(weights)):
            gradient[position] = gradient[position] / count + l2 * weights[position] / count
        step = learning_rate / (1.0 + iteration / 500.0)
        for position in range(len(weights)):
            weights[position] -= step * gradient[position]
    return LogisticModel(centers, scales, tuple(weights), 0.0, 1.0)


def _fit_platt(model: LogisticModel, rows: list[tuple[float, ...]], labels: list[int]) -> None:
    if not rows or len(set(labels)) < 2:
        return
    raw = [model.raw_logit(row) for row in rows]
    intercept, slope = 0.0, 1.0
    for iteration in range(500):
        grad_i = 0.0
        grad_s = 0.0
        for value, label in zip(raw, labels, strict=True):
            error = _sigmoid(intercept + slope * value) - label
            grad_i += error
            grad_s += error * value
        count = len(raw)
        step = 0.05 / (1.0 + iteration / 300.0)
        intercept -= step * grad_i / count
        slope -= step * grad_s / count
    model.calibration_intercept = intercept
    model.calibration_slope = slope


def _clock_inside(clock: time, start: time, end: time) -> bool:
    return start <= clock < end


def _session_name(timestamp: datetime, zone: ZoneInfo) -> str | None:
    clock = timestamp.astimezone(zone).time().replace(tzinfo=None)
    if _clock_inside(clock, time(0), time(4)):
        return "overnight"
    if _clock_inside(clock, time(8), time(12)):
        return "new_york"
    return None


def _trend_efficiency(bars: list[Bar], index: int, lookback: int = 20) -> float:
    if index < lookback:
        return 0.0
    window = bars[index - lookback : index]
    path = sum(abs(window[pos].close - window[pos - 1].close) for pos in range(1, len(window)))
    return (window[-1].close - window[0].close) / path if path else 0.0


def _volume_z(bars: list[Bar], index: int, lookback: int = 30) -> float:
    if index < lookback:
        return 0.0
    values = [bar.volume for bar in bars[index - lookback : index]]
    deviation = pstdev(values)
    if not deviation:
        return 0.0
    return max(-5.0, min(5.0, (bars[index].volume - mean(values)) / deviation))


def _level_strength(kind: str) -> int:
    return {
        "previous_week_high": 6,
        "previous_week_low": 6,
        "previous_day_high": 5,
        "previous_day_low": 5,
        "overnight_high": 4,
        "overnight_low": 4,
        "open_0930": 3,
        "open_0830": 3,
        "open_0000": 2,
        "equal_high": 2,
        "equal_low": 2,
        "pivot_high": 1,
        "pivot_low": 1,
    }.get(kind, 1)


def _build_reference_levels(bars: list[Bar], zone: ZoneInfo) -> dict[int, list[ProxyLevel]]:
    additions: dict[int, list[ProxyLevel]] = defaultdict(list)
    day_stats: dict[date, tuple[float, float]] = {}
    week_stats: dict[tuple[int, int], tuple[float, float]] = {}
    day_first_index: dict[date, int] = {}
    week_first_index: dict[tuple[int, int], int] = {}
    overnight: dict[date, tuple[float, float]] = {}
    for index, bar in enumerate(bars):
        local = bar.timestamp.astimezone(zone)
        day = local.date()
        week = (local.isocalendar().year, local.isocalendar().week)
        day_first_index.setdefault(day, index)
        week_first_index.setdefault(week, index)
        high, low = day_stats.get(day, (bar.high, bar.low))
        day_stats[day] = (max(high, bar.high), min(low, bar.low))
        high, low = week_stats.get(week, (bar.high, bar.low))
        week_stats[week] = (max(high, bar.high), min(low, bar.low))
        clock = local.time().replace(tzinfo=None)
        if time(0) <= clock < time(8):
            high, low = overnight.get(day, (bar.high, bar.low))
            overnight[day] = (max(high, bar.high), min(low, bar.low))
        if clock in {time(0), time(8, 30), time(9, 30)}:
            label = f"open_{clock.strftime('%H%M')}"
            additions[index].append(ProxyLevel(bar.open, "high", label, index, index))
            additions[index].append(ProxyLevel(bar.open, "low", label, index, index))
    days = sorted(day_first_index)
    for previous, current in zip(days, days[1:], strict=False):
        index = day_first_index[current]
        high, low = day_stats[previous]
        additions[index].extend(
            [
                ProxyLevel(high, "high", "previous_day_high", index, index),
                ProxyLevel(low, "low", "previous_day_low", index, index),
            ]
        )
        if current in overnight:
            overnight_high, overnight_low = overnight[current]
            # Available only once the 08:00 bar opens.
            available = next(
                (
                    pos
                    for pos in range(index, min(index + 1000, len(bars)))
                    if bars[pos].timestamp.astimezone(zone).date() == current
                    and bars[pos].timestamp.astimezone(zone).time().replace(tzinfo=None) >= time(8)
                ),
                index,
            )
            additions[available].extend(
                [
                    ProxyLevel(overnight_high, "high", "overnight_high", index, available),
                    ProxyLevel(overnight_low, "low", "overnight_low", index, available),
                ]
            )
    weeks = sorted(week_first_index)
    for previous, current in zip(weeks, weeks[1:], strict=False):
        index = week_first_index[current]
        high, low = week_stats[previous]
        additions[index].extend(
            [
                ProxyLevel(high, "high", "previous_week_high", index, index),
                ProxyLevel(low, "low", "previous_week_low", index, index),
            ]
        )
    return additions


def extract_events(bars: list[Bar], config: StrategyConfig) -> list[CandidateEvent]:
    """Extract causal model A-E events and counterfactual target outcomes."""

    zone = ZoneInfo(config.session.timezone)
    detector = FixedPivotDetector(3, 3)
    atr_engine = RollingATR(14)
    atr_values: list[float | None] = []
    pivot_additions: dict[int, list[ProxyLevel]] = defaultdict(list)
    for index, bar in enumerate(bars):
        atr_values.append(atr_engine.update(bar))
        for pivot in detector.update(bar):
            side = "high" if pivot.kind is PivotKind.HIGH else "low"
            kind = "pivot_high" if side == "high" else "pivot_low"
            pivot_additions[index].append(
                ProxyLevel(pivot.price, side, kind, index - 3, index)
            )
    additions = _build_reference_levels(bars, zone)
    for index, values in pivot_additions.items():
        additions[index].extend(values)

    active: list[ProxyLevel] = []
    sweeps: list[BaseSweep] = []
    tolerance = config.instrument.tick_size * 4
    excursion = config.instrument.tick_size
    recent_atr: deque[float] = deque(maxlen=50)
    for index, bar in enumerate(bars):
        atr = atr_values[index]
        if atr is not None:
            recent_atr.append(atr)
        for level in additions.get(index, ()):
            match = next(
                (
                    item
                    for item in reversed(active)
                    if item.active
                    and item.side == level.side
                    and abs(item.price - level.price) <= tolerance
                ),
                None,
            )
            if match and level.kind.startswith("pivot"):
                match.price = (match.price * match.cluster_count + level.price) / (
                    match.cluster_count + 1
                )
                match.cluster_count += 1
                match.kind = "equal_high" if level.side == "high" else "equal_low"
            else:
                active.append(level)
        if len(active) > 300:
            active = [item for item in active if item.active][-300:]
        session = _session_name(bar.timestamp, zone)
        if session is None or atr is None or atr <= 0:
            continue
        candidates: list[BaseSweep] = []
        for level in active:
            if not level.active or level.available_index >= index:
                continue
            if level.side == "high":
                crossed = bar.high >= level.price + excursion
                reclaimed = bar.close < level.price
                direction = Direction.SHORT
                extreme = bar.high
                wick = bar.high - max(bar.open, bar.close)
                reclaim = level.price - bar.close
                sweep_size = bar.high - level.price
                consumed = bar.close > level.price + excursion
            else:
                crossed = bar.low <= level.price - excursion
                reclaimed = bar.close > level.price
                direction = Direction.LONG
                extreme = bar.low
                wick = min(bar.open, bar.close) - bar.low
                reclaim = bar.close - level.price
                sweep_size = level.price - bar.low
                consumed = bar.close < level.price - excursion
            if consumed:
                level.active = False
                continue
            if not crossed or not reclaimed or wick <= 0:
                continue
            bar_range = max(bar.range, config.instrument.tick_size)
            body = bar.body
            atr_history = list(recent_atr)
            older_atr = mean(atr_history[:25]) if len(atr_history) >= 25 else atr
            recent = mean(atr_history[-10:]) if atr_history else atr
            local = bar.timestamp.astimezone(zone)
            features = {
                "wick_fraction": wick / bar_range,
                "wick_atr": wick / atr,
                "body_fraction": body / bar_range,
                "sweep_atr": sweep_size / atr,
                "reclaim_atr": reclaim / atr,
                "level_age_scaled": min(5.0, (index - level.available_index) / 100.0),
                "cluster_scaled": min(level.cluster_count, 5) / 5.0,
                "volume_z": _volume_z(bars, index),
                "trend_efficiency": _trend_efficiency(bars, index),
                "atr_ratio": recent / older_atr if older_atr else 1.0,
                "confirmation_strength": 0.0,
                "hour_sin": math.sin(2 * math.pi * local.hour / 24),
                "hour_cos": math.cos(2 * math.pi * local.hour / 24),
                "session_new_york": 1.0 if session == "new_york" else 0.0,
            }
            candidates.append(BaseSweep(index, direction, level, extreme, features, session))
        # One event per direction/bar. Prefer independently defined HTF levels,
        # then clustered and older levels. This avoids duplicating one price move.
        for direction in (Direction.LONG, Direction.SHORT):
            directional = [item for item in candidates if item.direction is direction]
            if not directional:
                continue
            selected = max(
                directional,
                key=lambda item: (
                    _level_strength(item.level.kind),
                    item.level.cluster_count,
                    item.index - item.level.available_index,
                ),
            )
            selected.level.active = False
            sweeps.append(selected)

    events: list[CandidateEvent] = []
    for sweep in sweeps:
        variants: list[tuple[str, int, float]] = [(MODEL_NAMES[0], sweep.index, 0.0)]
        start = sweep.index + 1
        end = min(len(bars), sweep.index + 6)
        prior = bars[max(0, sweep.index - 5) : sweep.index]
        structure_level = (
            max(item.high for item in prior)
            if sweep.direction is Direction.LONG and prior
            else min(item.low for item in prior)
            if prior
            else bars[sweep.index].close
        )
        confirmed_index: int | None = None
        structure_index: int | None = None
        displacement_index: int | None = None
        displacement_strength = 0.0
        for index in range(start, end):
            bar = bars[index]
            directional_close = (
                bar.close > bar.open
                if sweep.direction is Direction.LONG
                else bar.close < bar.open
            )
            if confirmed_index is None and directional_close:
                confirmed_index = index
            structure_broken = (
                bar.close > structure_level
                if sweep.direction is Direction.LONG
                else bar.close < structure_level
            )
            if structure_index is None and structure_broken:
                structure_index = index
            atr = atr_values[index] or 0.0
            strength = bar.body / atr if atr else 0.0
            if displacement_index is None and directional_close and strength >= 0.8:
                displacement_index = index
                displacement_strength = strength
        if confirmed_index is not None:
            variants.append((MODEL_NAMES[1], confirmed_index, 0.0))
        if structure_index is not None:
            variants.append((MODEL_NAMES[2], structure_index, 1.0))
        if _level_strength(sweep.level.kind) >= 3:
            variants.append((MODEL_NAMES[3], sweep.index, 0.0))
        if displacement_index is not None:
            variants.append((MODEL_NAMES[4], displacement_index, displacement_strength))
        for model_name, signal_index, strength in variants:
            if _session_name(bars[signal_index].timestamp, zone) != sweep.session:
                continue
            feature_map = dict(sweep.features)
            feature_map["confirmation_strength"] = strength
            values = _feature_tuple(feature_map, sweep.direction, model_name)
            event = _evaluate_event(
                bars, config, sweep, signal_index, model_name, values
            )
            if event is not None:
                events.append(event)
    return sorted(events, key=lambda item: (item.signal_index, item.base_index, item.model))


def _feature_tuple(
    values: dict[str, float], direction: Direction, model_name: str
) -> tuple[float, ...]:
    model_flags = {
        "direction_long": 1.0 if direction is Direction.LONG else 0.0,
        "model_basic": 1.0 if model_name == MODEL_NAMES[0] else 0.0,
        "model_confirmed": 1.0 if model_name == MODEL_NAMES[1] else 0.0,
        "model_structure": 1.0 if model_name == MODEL_NAMES[2] else 0.0,
        "model_htf": 1.0 if model_name == MODEL_NAMES[3] else 0.0,
        "model_displacement": 1.0 if model_name == MODEL_NAMES[4] else 0.0,
    }
    return tuple(model_flags.get(name, values.get(name, 0.0)) for name in FEATURE_NAMES)


def _evaluate_event(
    bars: list[Bar],
    config: StrategyConfig,
    sweep: BaseSweep,
    signal_index: int,
    model_name: str,
    features: tuple[float, ...],
) -> CandidateEvent | None:
    entry = bars[signal_index].close
    buffer = config.instrument.tick_size
    stop = sweep.extreme - sweep.direction.sign * buffer
    risk_points = abs(entry - stop)
    if risk_points < config.instrument.tick_size or (
        sweep.direction is Direction.LONG and stop >= entry
    ) or (sweep.direction is Direction.SHORT and stop <= entry):
        return None
    execution = config.execution
    round_trip_points = 2 * (
        execution.spread_ticks / 2 + execution.slippage_ticks
    ) * config.instrument.tick_size
    round_trip_fees = 2 * (
        execution.commission_per_contract_per_side
        + execution.exchange_fee_per_contract_per_side
    )
    cost_r = (
        round_trip_points * config.instrument.point_value + round_trip_fees
    ) / (risk_points * config.instrument.point_value)
    outcomes: dict[str, int] = {}
    net_r: dict[str, float] = {}
    exits: dict[str, int] = {}
    zone = ZoneInfo(config.session.timezone)
    for target_r in TARGETS:
        key = f"{target_r:g}R"
        target = entry + sweep.direction.sign * risk_points * target_r
        outcome = 0
        realized = -1.0 - cost_r
        exit_index = min(len(bars) - 1, signal_index + 30)
        for index in range(signal_index + 1, min(len(bars), signal_index + 31)):
            bar = bars[index]
            if _session_name(bar.timestamp, zone) != sweep.session:
                exit_index = index - 1
                mark = bars[exit_index].close
                realized = (mark - entry) * sweep.direction.sign / risk_points - cost_r
                break
            stop_hit = bar.low <= stop if sweep.direction is Direction.LONG else bar.high >= stop
            target_hit = (
                bar.high >= target if sweep.direction is Direction.LONG else bar.low <= target
            )
            if stop_hit:
                exit_index = index
                realized = -1.0 - cost_r
                break
            if target_hit:
                exit_index = index
                outcome = 1
                realized = target_r - cost_r
                break
        else:
            mark = bars[exit_index].close
            realized = (mark - entry) * sweep.direction.sign / risk_points - cost_r
        outcomes[key] = outcome
        net_r[key] = realized
        exits[key] = exit_index
    return CandidateEvent(
        sweep.index,
        signal_index,
        model_name,
        sweep.direction,
        entry,
        stop,
        sweep.session,
        features,
        outcomes,
        net_r,
        exits,
        cost_r,
    )


def _wilson_lower(successes: int, count: int, z: float = 1.645) -> float:
    if count <= 0:
        return 0.0
    probability = successes / count
    denominator = 1 + z * z / count
    center = probability + z * z / (2 * count)
    margin = z * math.sqrt(probability * (1 - probability) / count + z * z / (4 * count**2))
    return max(0.0, (center - margin) / denominator)


def _calibration_bins(
    probabilities: list[float], labels: list[int], bins: int = 5
) -> list[dict[str, float | int]]:
    paired = sorted(zip(probabilities, labels, strict=True))
    result: list[dict[str, float | int]] = []
    if not paired:
        return result
    for bin_index in range(bins):
        start = len(paired) * bin_index // bins
        end = len(paired) * (bin_index + 1) // bins
        subset = paired[start:end]
        if not subset:
            continue
        forecasts = [item[0] for item in subset]
        outcomes = [item[1] for item in subset]
        result.append(
            {
                "min_probability": min(forecasts),
                "max_probability": max(forecasts),
                "mean_probability": mean(forecasts),
                "observed_rate": mean(outcomes),
                "count": len(subset),
                "successes": sum(outcomes),
                "wilson_lower_90": _wilson_lower(sum(outcomes), len(outcomes)),
            }
        )
    return result


def _calibration_metrics(probabilities: list[float], labels: list[int]) -> dict[str, Any]:
    if not labels:
        return {"count": 0, "brier": None, "ece": None, "base_rate": None, "bins": []}
    bins = _calibration_bins(probabilities, labels)
    brier = mean((probability - label) ** 2 for probability, label in zip(probabilities, labels))
    ece = sum(
        int(item["count"])
        / len(labels)
        * abs(float(item["mean_probability"]) - float(item["observed_rate"]))
        for item in bins
    )
    base = mean(labels)
    base_brier = mean((base - label) ** 2 for label in labels)
    return {
        "count": len(labels),
        "base_rate": base,
        "brier": brier,
        "base_rate_brier": base_brier,
        "brier_skill": 1 - brier / base_brier if base_brier else None,
        "ece_equal_count_5_bins": ece,
        "bins": bins,
    }


def _summary(events: list[CandidateEvent], target: str) -> dict[str, Any]:
    if not events:
        return {"events": 0}
    returns = [event.net_r[target] for event in events]
    wins = [event for event in events if event.outcomes[target]]
    losses = [value for value in returns if value <= 0]
    positives = [value for value in returns if value > 0]
    gross_win = sum(positives)
    gross_loss = abs(sum(losses))
    return {
        "events": len(events),
        "target_hit_rate": len(wins) / len(events),
        "average_net_r": mean(returns),
        "average_win_r": mean(positives) if positives else None,
        "average_loss_r": mean(losses) if losses else None,
        "profit_factor_r": gross_win / gross_loss if gross_loss else None,
        "positive_fraction": sum(value > 0 for value in returns) / len(returns),
        "average_cost_r": mean(event.cost_r for event in events),
    }


def _policy_evaluation(
    events: list[CandidateEvent],
    models: dict[str, LogisticModel],
    calibration: dict[str, list[dict[str, float | int]]],
    cost_multiplier: float = 1.0,
) -> dict[str, Any]:
    candidates: list[tuple[int, float, CandidateEvent, str, float, float]] = []
    for event in events:
        best: tuple[float, str, float, float] | None = None
        for target_r in TARGETS:
            target = f"{target_r:g}R"
            probability = models[target].predict(event.features)
            bins = calibration[target]
            matching = next(
                (
                    item
                    for item in bins
                    if float(item["min_probability"])
                    <= probability
                    <= float(item["max_probability"])
                ),
                min(bins, key=lambda item: abs(float(item["mean_probability"]) - probability))
                if bins
                else None,
            )
            lower = float(matching["wilson_lower_90"]) if matching else 0.0
            cost = event.cost_r * cost_multiplier
            conservative_ev = lower * (target_r - cost) + (1 - lower) * (-1 - cost)
            point_ev = probability * (target_r - cost) + (1 - probability) * (-1 - cost)
            proposal = (conservative_ev, target, probability, point_ev)
            if best is None or proposal[0] > best[0]:
                best = proposal
        if best and best[0] > 0:
            candidates.append((event.signal_index, best[0], event, best[1], best[2], best[3]))
    # One position at a time and one candidate per signal bar; choose highest
    # conservative EV using only probabilities and development calibration.
    grouped: dict[
        int, list[tuple[int, float, CandidateEvent, str, float, float]]
    ] = defaultdict(list)
    for item in candidates:
        grouped[item[0]].append(item)
    selected: list[tuple[CandidateEvent, str, float, float]] = []
    available_index = -1
    for signal_index in sorted(grouped):
        if signal_index <= available_index:
            continue
        choice = max(grouped[signal_index], key=lambda item: item[1])
        event, target = choice[2], choice[3]
        selected.append((event, target, choice[4], choice[5]))
        available_index = event.exit_indices[target]
    returns = [
        event.net_r[target] - event.cost_r * (cost_multiplier - 1)
        for event, target, _, _ in selected
    ]
    equity = 0.0
    peak = 0.0
    max_drawdown = 0.0
    for value in returns:
        equity += value
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, peak - equity)
    positives = [value for value in returns if value > 0]
    negatives = [value for value in returns if value <= 0]
    return {
        "trades": len(selected),
        "win_rate": len(positives) / len(selected) if selected else None,
        "net_r": sum(returns),
        "expectancy_r": mean(returns) if returns else None,
        "profit_factor_r": sum(positives) / abs(sum(negatives)) if negatives else None,
        "max_drawdown_r": max_drawdown,
        "average_predicted_probability": mean(item[2] for item in selected) if selected else None,
        "average_point_ev": mean(item[3] for item in selected) if selected else None,
        "by_model": {
            model: {
                "trades": sum(event.model == model for event, _, _, _ in selected),
                "net_r": sum(
                    value
                    for (event, _, _, _), value in zip(selected, returns, strict=True)
                    if event.model == model
                ),
            }
            for model in MODEL_NAMES
        },
        "by_session": {
            session: {
                "trades": sum(event.session == session for event, _, _, _ in selected),
                "net_r": sum(
                    value
                    for (event, _, _, _), value in zip(selected, returns, strict=True)
                    if event.session == session
                ),
            }
            for session in ("overnight", "new_york")
        },
        "target_selection": {
            target: sum(chosen == target for _, chosen, _, _ in selected)
            for target in (f"{value:g}R" for value in TARGETS)
        },
    }


def run_refresh_research(
    development_bars: list[Bar], validation_bars: list[Bar], config: StrategyConfig
) -> dict[str, Any]:
    development = extract_events(development_bars, config)
    validation = extract_events(validation_bars, config)
    cutoff = int(len(development) * 0.75)
    train = development[:cutoff]
    calibrate = development[cutoff:]
    models: dict[str, LogisticModel] = {}
    calibration_bins: dict[str, list[dict[str, float | int]]] = {}
    calibration_reports: dict[str, Any] = {}
    validation_reports: dict[str, Any] = {}
    for target_r in TARGETS:
        target = f"{target_r:g}R"
        model = _fit_linear_logistic(
            [event.features for event in train], [event.outcomes[target] for event in train]
        )
        _fit_platt(
            model,
            [event.features for event in calibrate],
            [event.outcomes[target] for event in calibrate],
        )
        models[target] = model
        calibration_probabilities = [model.predict(event.features) for event in calibrate]
        validation_probabilities = [model.predict(event.features) for event in validation]
        calibration_reports[target] = _calibration_metrics(
            calibration_probabilities, [event.outcomes[target] for event in calibrate]
        )
        calibration_bins[target] = calibration_reports[target]["bins"]
        validation_reports[target] = _calibration_metrics(
            validation_probabilities, [event.outcomes[target] for event in validation]
        )
    by_model = {
        model: {
            "development": {
                f"{target:g}R": _summary(
                    [event for event in development if event.model == model], f"{target:g}R"
                )
                for target in TARGETS
            },
            "validation": {
                f"{target:g}R": _summary(
                    [event for event in validation if event.model == model], f"{target:g}R"
                )
                for target in TARGETS
            },
        }
        for model in MODEL_NAMES
    }
    feature_coefficients = {
        target: {
            "intercept": model.weights[0],
            "calibration_intercept": model.calibration_intercept,
            "calibration_slope": model.calibration_slope,
            "coefficients": dict(zip(FEATURE_NAMES, model.weights[1:], strict=True)),
        }
        for target, model in models.items()
    }
    return {
        "protocol": {
            "development_events": len(development),
            "training_events": len(train),
            "calibration_events": len(calibrate),
            "validation_events": len(validation),
            "holdout_opened": False,
            "features": list(FEATURE_NAMES),
            "models": list(MODEL_NAMES),
            "targets": list(TARGETS),
            "warning": (
                "OHLCV liquidity proxies do not observe resting orders, actual stops, "
                "queue position, or intrabar path. Model probabilities are research "
                "estimates, not certainties."
            ),
        },
        "by_model": by_model,
        "probability_model": {
            "development_calibration": calibration_reports,
            "validation_calibration": validation_reports,
            "coefficients": feature_coefficients,
        },
        "adaptive_policy": {
            "development_calibration_period": _policy_evaluation(
                calibrate, models, calibration_bins
            ),
            "validation_base_costs": _policy_evaluation(validation, models, calibration_bins),
            "validation_costs_1_25x": _policy_evaluation(
                validation, models, calibration_bins, 1.25
            ),
            "validation_costs_1_50x": _policy_evaluation(
                validation, models, calibration_bins, 1.5
            ),
        },
    }
