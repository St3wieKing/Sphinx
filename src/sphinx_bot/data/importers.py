"""External research-data download and normalization helpers.

Downloaded vendor/public data remains outside Git. Every normalized output gets a
manifest with source metadata and hashes. No credentials are collected here.
"""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import urllib.request
import zipfile
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from ..models import Bar
from ..research.synthetic import write_bars_csv

PUBLIC_DATASETS = {
    "kaggle-nq-2022-2025": {
        "url": "https://www.kaggle.com/api/v1/datasets/download/tgtanalytics/nq-futures-1min-bar-2022-2025",
        "page": "https://www.kaggle.com/datasets/tgtanalytics/nq-futures-1min-bar-2022-2025",
        "license": "CC0: Public Domain (as declared by dataset publisher)",
        "expected_file": "Dataset_NQ_1min_2022_2025.csv",
        "timezone": "America/New_York",
        "symbol": "NQ",
        "warning": "Third-party continuous-series construction and rollover methodology require independent verification.",
    }
}


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_public_dataset(dataset_id: str, destination: str | Path) -> dict[str, Any]:
    if dataset_id not in PUBLIC_DATASETS:
        raise ValueError(f"unknown public dataset: {dataset_id}")
    metadata = PUBLIC_DATASETS[dataset_id]
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    archive = root / f"{dataset_id}.zip"
    request = urllib.request.Request(
        metadata["url"],
        headers={"User-Agent": "SphinxResearch/1.0 (paper-only quantitative research)"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response, archive.open("wb") as output:
            shutil.copyfileobj(response, output)
    except Exception as exc:
        raise ConnectionError(
            "Public dataset download failed. This environment may block Kaggle downloads; "
            "download it from the documented page and run normalize-data locally. "
            f"Underlying error: {exc}"
        ) from exc
    if not zipfile.is_zipfile(archive):
        raise ValueError("download did not produce a valid ZIP archive")
    extracted: list[str] = []
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError("unsafe path in downloaded archive")
            bundle.extract(member, root)
            if not member.is_dir():
                extracted.append(str(root / member.filename))
    manifest = {
        "dataset_id": dataset_id,
        **metadata,
        "downloaded_at": datetime.now(UTC).isoformat(),
        "archive": str(archive),
        "archive_sha256": sha256_file(archive),
        "extracted": extracted,
    }
    (root / f"{dataset_id}.manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest


def _normalized_headers(fieldnames: list[str]) -> dict[str, str]:
    return {name.strip().lower().replace(" ", "_").replace("-", "_"): name for name in fieldnames}


def _choose(headers: dict[str, str], *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in headers:
            return headers[candidate]
    return None


def _parse_external_timestamp(
    value: str,
    timezone_name: str,
    previous: datetime | None,
) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        for pattern in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%Y%m%d %H%M%S",
        ):
            try:
                parsed = datetime.strptime(normalized, pattern)  # noqa: DTZ007
                break
            except ValueError:
                continue
    if parsed is None:
        raise ValueError(f"unrecognized timestamp: {value!r}")
    if parsed.tzinfo is None:
        zone = ZoneInfo(timezone_name)
        first = parsed.replace(tzinfo=zone, fold=0).astimezone(UTC)
        second = parsed.replace(tzinfo=zone, fold=1).astimezone(UTC)
        if previous is not None and first <= previous < second:
            return second
        return first
    return parsed.astimezone(UTC)


def read_external_csv(
    path: str | Path,
    *,
    symbol: str,
    source_timezone: str,
    source_interval_seconds: int = 60,
) -> list[Bar]:
    source = Path(path)
    bars: list[Bar] = []
    with source.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("external CSV has no header")
        headers = _normalized_headers(reader.fieldnames)
        date_column = _choose(headers, "date", "trading_date")
        timestamp_column = _choose(
            headers,
            "timestamp",
            "timestamp_et",
            "datetime",
            "date_time",
        )
        clock_column = _choose(headers, "clock", "time") if date_column else None
        if timestamp_column is None and date_column is None:
            timestamp_column = _choose(headers, "time")
        columns = {
            name: _choose(headers, name, name.capitalize())
            for name in ("open", "high", "low", "close", "volume")
        }
        if not timestamp_column and not (date_column and clock_column):
            raise ValueError(f"cannot identify timestamp column from {reader.fieldnames}")
        if any(columns[name] is None for name in ("open", "high", "low", "close")):
            raise ValueError(f"cannot identify OHLC columns from {reader.fieldnames}")
        previous: datetime | None = None
        for line_number, row in enumerate(reader, start=2):
            try:
                raw_timestamp = (
                    row[timestamp_column]
                    if timestamp_column
                    else f"{row[date_column]} {row[clock_column]}"
                )
                timestamp = _parse_external_timestamp(raw_timestamp, source_timezone, previous)
                bar = Bar(
                    timestamp=timestamp,
                    open=float(row[columns["open"]]),
                    high=float(row[columns["high"]]),
                    low=float(row[columns["low"]]),
                    close=float(row[columns["close"]]),
                    volume=float(row[columns["volume"]] or 0.0) if columns["volume"] else 0.0,
                    symbol=symbol,
                    interval_seconds=source_interval_seconds,
                )
            except Exception as exc:
                raise ValueError(f"external CSV line {line_number}: {exc}") from exc
            if previous is not None and timestamp <= previous:
                raise ValueError(
                    f"external CSV line {line_number}: duplicate/out-of-order timestamp {timestamp}"
                )
            bars.append(bar)
            previous = timestamp
    if not bars:
        raise ValueError("external CSV contains no rows")
    return bars


def resample_complete_bars(bars: list[Bar], target_seconds: int) -> list[Bar]:
    if not bars:
        return []
    if target_seconds < bars[0].interval_seconds:
        raise ValueError("target interval cannot be smaller than source interval")
    if target_seconds % bars[0].interval_seconds:
        raise ValueError("target interval must be a multiple of source interval")
    expected_count = target_seconds // bars[0].interval_seconds
    buckets: dict[int, list[Bar]] = defaultdict(list)
    for bar in bars:
        epoch = int(bar.timestamp.timestamp())
        start = epoch - epoch % target_seconds
        buckets[start].append(bar)
    completed: list[Bar] = []
    for start, values in sorted(buckets.items()):
        if len(values) != expected_count:
            continue
        expected_timestamps = [
            start + index * values[0].interval_seconds for index in range(expected_count)
        ]
        if [int(value.timestamp.timestamp()) for value in values] != expected_timestamps:
            continue
        completed.append(
            Bar(
                timestamp=datetime.fromtimestamp(start, UTC),
                open=values[0].open,
                high=max(value.high for value in values),
                low=min(value.low for value in values),
                close=values[-1].close,
                volume=sum(value.volume for value in values),
                symbol=values[0].symbol,
                interval_seconds=target_seconds,
            )
        )
    if not completed:
        raise ValueError("no complete target bars remained after resampling")
    return completed


def normalize_external_data(
    source: str | Path,
    destination: str | Path,
    *,
    symbol: str,
    source_timezone: str,
    source_interval_seconds: int,
    target_interval_seconds: int = 120,
    provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    raw = read_external_csv(
        source,
        symbol=symbol,
        source_timezone=source_timezone,
        source_interval_seconds=source_interval_seconds,
    )
    normalized = resample_complete_bars(raw, target_interval_seconds)
    output = write_bars_csv(destination, normalized)
    manifest = {
        "source": str(source),
        "source_sha256": sha256_file(source),
        "source_timezone": source_timezone,
        "source_interval_seconds": source_interval_seconds,
        "symbol": symbol,
        "target": str(output),
        "target_sha256": sha256_file(output),
        "target_interval_seconds": target_interval_seconds,
        "source_rows": len(raw),
        "normalized_rows": len(normalized),
        "dropped_incomplete_source_rows": len(raw)
        - len(normalized) * (target_interval_seconds // source_interval_seconds),
        "first_timestamp": normalized[0].timestamp.isoformat(),
        "last_timestamp": normalized[-1].timestamp.isoformat(),
        "normalized_at": datetime.now(UTC).isoformat(),
        "provenance": provenance or {},
        "warnings": [
            "Verify rollover/back-adjustment methodology before interpreting results.",
            "Resampling drops incomplete target buckets; it never forward-fills missing bars.",
        ],
    }
    manifest_path = Path(destination).with_suffix(Path(destination).suffix + ".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest
