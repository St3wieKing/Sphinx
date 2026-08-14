"""CSV-replay paper deployment with persistent audit and daily reports.

There is deliberately no live-money broker adapter in this repository.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from ..config import StrategyConfig
from ..models import Bar
from ..monitoring.audit import AuditLogger
from ..monitoring.report import write_daily_reports
from ..research.backtest import BacktestEngine, BacktestResult


class PaperTrader:
    def __init__(self, config: StrategyConfig, output_root: str | Path | None = None) -> None:
        if not config.paper_only:
            raise ValueError("PaperTrader refuses configurations with paper_only=false")
        self.config = config
        root = Path(output_root or config.logging.output_directory)
        run_id = datetime.now(UTC).strftime("paper-%Y%m%dT%H%M%SZ")
        self.run_directory = root / run_id
        self.run_directory.mkdir(parents=True, exist_ok=False)

    def replay(self, bars: Sequence[Bar]) -> BacktestResult:
        audit_path = self.run_directory / "audit.jsonl"
        audit = AuditLogger(audit_path)
        result = BacktestEngine(self.config, audit=audit).run(bars)
        (self.run_directory / "config.snapshot.json").write_text(
            json.dumps(self.config.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (self.run_directory / "summary.json").write_text(
            json.dumps(result.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )
        write_daily_reports(self.run_directory / "daily_reports", result.trades, result.decisions)
        alerts = [record for record in audit.records if record["record_type"] == "kill_switch"]
        (self.run_directory / "alerts.json").write_text(
            json.dumps(alerts, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return result
