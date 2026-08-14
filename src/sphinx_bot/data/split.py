"""Chronological dataset partitions and walk-forward folds."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from ..models import Bar


@dataclass(frozen=True)
class DatasetSplit:
    development: tuple[Bar, ...]
    validation: tuple[Bar, ...]
    holdout: tuple[Bar, ...]

    def get(self, name: str, *, strategy_frozen: bool, allow_holdout: bool) -> tuple[Bar, ...]:
        if name == "development":
            return self.development
        if name == "validation":
            return self.validation
        if name == "holdout":
            if not strategy_frozen or not allow_holdout:
                raise PermissionError(
                    "holdout is locked: freeze the strategy config and pass explicit holdout consent"
                )
            return self.holdout
        if name == "all":
            raise PermissionError("running optimization/backtests on all partitions is prohibited")
        raise ValueError(f"unknown partition: {name}")


def chronological_split(
    bars: Sequence[Bar],
    development_fraction: float,
    validation_fraction: float,
    holdout_fraction: float,
    minimum_bars: int = 1,
) -> DatasetSplit:
    if abs(development_fraction + validation_fraction + holdout_fraction - 1.0) > 1e-9:
        raise ValueError("partition fractions must sum to one")
    count = len(bars)
    development_end = int(count * development_fraction)
    validation_end = development_end + int(count * validation_fraction)
    parts = (
        tuple(bars[:development_end]),
        tuple(bars[development_end:validation_end]),
        tuple(bars[validation_end:]),
    )
    if any(len(part) < minimum_bars for part in parts):
        raise ValueError(
            f"each partition requires at least {minimum_bars} bars; "
            f"got {[len(part) for part in parts]}"
        )
    return DatasetSplit(*parts)


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    development: tuple[Bar, ...]
    validation: tuple[Bar, ...]


def expanding_walk_forward(
    bars: Sequence[Bar], initial_development: int, validation_size: int, step: int | None = None
) -> tuple[WalkForwardFold, ...]:
    if initial_development <= 0 or validation_size <= 0:
        raise ValueError("window sizes must be positive")
    step = step or validation_size
    folds: list[WalkForwardFold] = []
    end = initial_development
    fold = 0
    while end + validation_size <= len(bars):
        folds.append(
            WalkForwardFold(
                fold=fold,
                development=tuple(bars[:end]),
                validation=tuple(bars[end : end + validation_size]),
            )
        )
        fold += 1
        end += step
    return tuple(folds)
