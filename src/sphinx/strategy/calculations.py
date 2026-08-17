"""Frozen strategy calculations (rule IDs CALC-*).

CALC-01 prev_close : last RTH 1-min close of the previous valid session
CALC-02 atr14      : mean of true range over the previous 14 sessions
                     (strictly prior; TR uses prev session close)
CALC-03 rv20       : stdev of the prior 20 close-to-close simple returns,
                     annualized with sqrt(252)  (strictly prior)
CALC-04 r_early    : close of last 1-min bar BEFORE 10:00 / prev_close - 1
CALC-05 r_od       : close of last 1-min bar BEFORE 15:30 / prev_close - 1
All are computed from validated RTH 1-minute bars only.
"""
from __future__ import annotations

import numpy as np


def r_early(arr, prev_close: float, early_mark_time: int = 600) -> float | None:
    """CALC-04."""
    m = arr["t"] < early_mark_time
    if not m.any():
        return None
    return float(arr["c"][m][-1] / prev_close - 1.0)


def r_od(arr, prev_close: float, signal_time: int = 930) -> float | None:
    """CALC-05."""
    m = arr["t"] < signal_time
    if not m.any():
        return None
    return float(arr["c"][m][-1] / prev_close - 1.0)


def last_price_before(arr, t_min: int) -> float | None:
    m = arr["t"] < t_min
    if not m.any():
        return None
    return float(arr["c"][m][-1])
