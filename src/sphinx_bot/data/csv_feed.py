"""CSV market-data ingestion and deterministic validation."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from pathlib import Path

from ..models import Bar

REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close"}


@dataclass(frozen=True)
class DataQualityReport:
    rows: int
    duplicates: int
    out_of_order: int
    interval_mismatches: int
    large_gaps: int
    first_timestamp: datetime | None
    last_timestamp: datetime | None
    sha256: str

    @property
    def valid(self) -> bool:
        return self.rows > 0 and self.duplicates == 0 and self.out_of_order == 0


def parse_timestamp(value: str, assume_timezone: timezone | None = None) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        if assume_timezone is None:
            raise ValueError(
                f"naive timestamp {value!r}; input must include UTC offset (recommended: Z)"
            )
        parsed = parsed.replace(tzinfo=assume_timezone)
    return parsed.astimezone(UTC)


def read_bars(
    path: str | Path,
    *,
    symbol: str = "NQ",
    interval_seconds: int = 120,
    strict_interval: bool = True,
) -> list[Bar]:
    source = Path(path)
    bars: list[Bar] = []
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or ())
            raise ValueError(f"CSV is missing required columns: {sorted(missing)}")
        previous: datetime | None = None
        for line_number, row in enumerate(reader, start=2):
            try:
                timestamp = parse_timestamp(row["timestamp"])
                bar = Bar(
                    timestamp=timestamp,
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row.get("volume") or 0.0),
                    symbol=(row.get("symbol") or symbol).strip(),
                    interval_seconds=int(row.get("interval_seconds") or interval_seconds),
                )
            except Exception as exc:
                raise ValueError(f"invalid market data on CSV line {line_number}: {exc}") from exc
            if previous is not None:
                delta = (timestamp - previous).total_seconds()
                if delta <= 0:
                    raise ValueError(f"timestamps are duplicate/out of order on line {line_number}")
                if strict_interval and delta < interval_seconds:
                    raise ValueError(f"overlapping bars on line {line_number}: {delta}s gap")
            bars.append(bar)
            previous = timestamp
    if not bars:
        raise ValueError("CSV contains no data rows")
    return bars


def stream_bars(
    path: str | Path, *, symbol: str = "NQ", interval_seconds: int = 120
) -> Iterator[Bar]:
    """Stream validated bars. CSV replay is the only paper feed shipped in v0.1."""

    yield from read_bars(path, symbol=symbol, interval_seconds=interval_seconds)


def inspect_data(
    bars: Iterable[Bar], *, expected_interval_seconds: int, max_gap_seconds: int
) -> DataQualityReport:
    materialized = list(bars)
    duplicates = 0
    out_of_order = 0
    mismatches = 0
    gaps = 0
    digest = hashlib.sha256()
    previous: Bar | None = None
    for bar in materialized:
        digest.update(
            (
                f"{bar.timestamp.isoformat()}|{bar.open}|{bar.high}|{bar.low}|"
                f"{bar.close}|{bar.volume}\n"
            ).encode()
        )
        if bar.interval_seconds != expected_interval_seconds:
            mismatches += 1
        if previous:
            delta = (bar.timestamp - previous.timestamp).total_seconds()
            if delta == 0:
                duplicates += 1
            elif delta < 0:
                out_of_order += 1
            elif delta > max_gap_seconds:
                gaps += 1
        previous = bar
    return DataQualityReport(
        rows=len(materialized),
        duplicates=duplicates,
        out_of_order=out_of_order,
        interval_mismatches=mismatches,
        large_gaps=gaps,
        first_timestamp=materialized[0].timestamp if materialized else None,
        last_timestamp=materialized[-1].timestamp if materialized else None,
        sha256=digest.hexdigest(),
    )
