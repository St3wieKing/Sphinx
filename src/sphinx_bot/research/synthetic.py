"""Deterministic synthetic bars for plumbing demos only—not strategy evidence."""

from __future__ import annotations

import csv
import random
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..models import Bar


def generate_synthetic_bars(days: int = 15, seed: int = 44) -> list[Bar]:
    if days <= 0:
        raise ValueError("days must be positive")
    rng = random.Random(seed)
    eastern = ZoneInfo("America/New_York")
    bars: list[Bar] = []
    price = 20_000.0
    session_date = date(2024, 1, 8)
    generated = 0
    while generated < days:
        if session_date.weekday() >= 5:
            session_date += timedelta(days=1)
            continue
        local_start = datetime.combine(session_date - timedelta(days=1), time(23, 0), eastern)
        day_rows: list[Bar] = []
        for index in range(160):
            timestamp = (local_start + timedelta(minutes=2 * index)).astimezone(UTC)
            if 43 <= index <= 54:
                change = rng.choice((-0.10, 0.0, 0.10))
                width = 0.35
            elif index == 55:
                change = 3.5 if generated % 2 == 0 else -3.5
                width = 0.5
            elif index == 56:
                change = 1.5 if generated % 2 == 0 else -1.5
                width = 0.6
            elif index == 57:
                change = -2.4 if generated % 2 == 0 else 2.4
                width = 0.8
            elif index in (58, 59, 60):
                change = 2.0 if generated % 2 == 0 else -2.0
                width = 0.6
            else:
                change = rng.gauss(0, 0.45)
                width = abs(rng.gauss(0.45, 0.12))
            open_price = price
            close = price + change
            high = max(open_price, close) + width
            low = min(open_price, close) - width
            price = close
            day_rows.append(
                Bar(timestamp, open_price, high, low, close, rng.randint(50, 500), "NQ", 120)
            )
        bars.extend(day_rows)
        generated += 1
        session_date += timedelta(days=1)
    return bars


def write_bars_csv(path: str | Path, bars: list[Bar]) -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["timestamp", "open", "high", "low", "close", "volume", "symbol", "interval_seconds"]
        )
        for bar in bars:
            writer.writerow(
                [
                    bar.timestamp.isoformat().replace("+00:00", "Z"),
                    f"{bar.open:.8f}",
                    f"{bar.high:.8f}",
                    f"{bar.low:.8f}",
                    f"{bar.close:.8f}",
                    bar.volume,
                    bar.symbol,
                    bar.interval_seconds,
                ]
            )
    return destination
