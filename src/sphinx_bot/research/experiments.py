"""Append-only experiment ledger with holdout-use controls."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    created_at: str
    hypothesis: str
    parameters_changed: dict[str, Any]
    reason: str
    development_result: dict[str, Any] | None
    validation_result: dict[str, Any] | None
    holdout_result: dict[str, Any] | None
    decision: str
    config_fingerprint: str
    strategy_frozen_before_holdout: bool
    notes: str = ""


class ExperimentLedger:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def append(
        self,
        *,
        experiment_id: str,
        hypothesis: str,
        parameters_changed: dict[str, Any],
        reason: str,
        config_fingerprint: str,
        development_result: dict[str, Any] | None = None,
        validation_result: dict[str, Any] | None = None,
        holdout_result: dict[str, Any] | None = None,
        decision: str = "pending",
        strategy_frozen_before_holdout: bool = False,
        notes: str = "",
    ) -> Experiment:
        if not experiment_id.strip() or not hypothesis.strip() or not reason.strip():
            raise ValueError("experiment id, hypothesis, and reason are required")
        if holdout_result is not None and not strategy_frozen_before_holdout:
            raise PermissionError("cannot record holdout results before strategy freeze")
        existing = {item.experiment_id for item in self.read_all()}
        if experiment_id in existing:
            raise ValueError(f"duplicate experiment id: {experiment_id}")
        experiment = Experiment(
            experiment_id=experiment_id,
            created_at=datetime.now(UTC).isoformat(),
            hypothesis=hypothesis,
            parameters_changed=parameters_changed,
            reason=reason,
            development_result=development_result,
            validation_result=validation_result,
            holdout_result=holdout_result,
            decision=decision,
            config_fingerprint=config_fingerprint,
            strategy_frozen_before_holdout=strategy_frozen_before_holdout,
            notes=notes,
        )
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(experiment), sort_keys=True) + "\n")
        return experiment

    def read_all(self) -> tuple[Experiment, ...]:
        experiments: list[Experiment] = []
        with self.path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    experiments.append(Experiment(**json.loads(line)))
                except Exception as exc:
                    raise ValueError(f"invalid ledger line {line_number}: {exc}") from exc
        return tuple(experiments)
