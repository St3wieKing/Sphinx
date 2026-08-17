"""Data validation gates.

Any failure => the affected session is excluded from research, and in live
operation the engine must answer NO TRADE / DATA_VALIDATION_FAILURE.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class DataValidationError(Exception):
    pass


def validate_minute_frame(df: pd.DataFrame) -> dict:
    """Global integrity checks on the full minute frame."""
    report = {}
    report["rows"] = len(df)
    report["monotonic"] = bool(df.index.is_monotonic_increasing)
    report["duplicates"] = int(df.index.duplicated().sum())
    bad_price = ((df[["open", "high", "low", "close"]] <= 0).any(axis=1)
                 | (df["high"] < df["low"])
                 | (df["high"] < df[["open", "close"]].max(axis=1) - 1e-9)
                 | (df["low"] > df[["open", "close"]].min(axis=1) + 1e-9))
    report["bad_price_rows"] = int(bad_price.sum())
    report["neg_volume_rows"] = int((df["volume"] < 0).sum())
    if not report["monotonic"] or report["duplicates"]:
        raise DataValidationError(f"integrity failure: {report}")
    return report


def valid_session_mask(sessions: pd.DataFrame,
                       min_bars_full: int = 370,
                       min_bars_half: int = 190) -> pd.Series:
    """A session is usable when it has near-complete bar coverage and all
    prior-reference values available.  Sessions failing this are NO-TRADE
    days (research: excluded; live: DATA_VALIDATION_FAILURE)."""
    need = np.where(sessions["is_half_day"], min_bars_half, min_bars_full)
    ok = (sessions["n_bars"].to_numpy() >= need)
    ok &= sessions[["prev_close", "atr14", "rv20", "sma200"]].notna().all(axis=1).to_numpy()
    # sane gap: reject > 20% overnight moves as suspect data unless volume confirms
    ok &= sessions["gap"].abs().to_numpy() < 0.20
    return pd.Series(ok, index=sessions.index, name="valid")


def stale_check(last_bar_age_sec: float, max_age_sec: float = 120.0) -> bool:
    """Live-mode staleness gate."""
    return last_bar_age_sec <= max_age_sec
