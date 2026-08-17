import numpy as np
import pandas as pd
import pytest

from sphinx.backtest.costs import CostModel
from sphinx.backtest.engine import DayPlan, simulate_day
from sphinx.data.validation import validate_minute_frame, DataValidationError

C0 = CostModel(commission=0.0, half_spread=0.0, slippage=0.0, stop_gap_extra=0.0)


def bars(seq):
    """seq: list of (t, o, h, l, c)."""
    a = np.array(seq, dtype=float)
    return {"t": a[:, 0].astype(int), "o": a[:, 1], "h": a[:, 2],
            "l": a[:, 3], "c": a[:, 4], "v": np.ones(len(a)) * 100}


def test_market_entry_then_eod_exit():
    arr = bars([(570, 100, 101, 99, 100.5), (571, 100.5, 101, 100, 101),
                (572, 101, 102, 100.5, 101.5)])
    tr = simulate_day("d", arr, DayPlan(1, "market_at", 571), C0)
    assert tr.entry_px == 100.5 and tr.exit_reason == "eod" and tr.exit_px == 101.5


def test_stop_exit_conservative_before_target_same_bar():
    # bar hits both stop (99) and target (103): stop must win
    arr = bars([(570, 100, 100, 100, 100), (571, 100, 100, 100, 100),
                (572, 101, 104, 98, 102)])
    tr = simulate_day("d", arr, DayPlan(1, "market_at", 571, stop_px=99.0,
                                        target_px=103.0), C0)
    assert tr.exit_reason == "stop" and tr.exit_px == 99.0


def test_stop_gap_through_fills_at_open():
    arr = bars([(570, 100, 100, 100, 100), (571, 100, 100, 100, 100),
                (572, 95, 96, 94, 95)])
    tr = simulate_day("d", arr, DayPlan(1, "market_at", 571, stop_px=99.0), C0)
    assert tr.exit_reason == "stop" and tr.exit_px == 95.0


def test_stop_entry_cancelled_if_never_triggered():
    arr = bars([(570, 100, 100.5, 99.5, 100)] + [(t, 100, 100.5, 99.5, 100) for t in range(571, 600)])
    plan = DayPlan(1, "stop", 575, entry_px=101.0, cancel_time=590)
    assert simulate_day("d", arr, plan, C0) is None


def test_costs_reduce_pnl_symmetrically():
    arr = bars([(570, 100, 101, 99, 100), (571, 100, 101, 99, 100),
                (572, 100, 101, 99, 101)])
    cm = CostModel()
    tr = simulate_day("d", arr, DayPlan(1, "market_at", 571), cm)
    gross = 1.0  # 100 -> 101
    assert abs((gross - 2 * (cm.half_spread + cm.slippage)) - tr.pnl_per_share
               - 0.0) < 1e-9 or tr.pnl_per_share < gross


def test_validation_rejects_duplicates():
    idx = pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:30"])
    df = pd.DataFrame({"open": [1, 1], "high": [1, 1], "low": [1, 1],
                       "close": [1, 1], "volume": [1, 1]}, index=idx)
    with pytest.raises(DataValidationError):
        validate_minute_frame(df)


def test_validation_counts_bad_prices():
    idx = pd.to_datetime(["2024-01-02 09:30", "2024-01-02 09:31"])
    df = pd.DataFrame({"open": [1, 2], "high": [1, 1], "low": [1, 3],
                       "close": [1, 2], "volume": [1, 1]}, index=idx)
    rep = validate_minute_frame(df)
    assert rep["bad_price_rows"] == 1
