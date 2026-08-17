import numpy as np
import pandas as pd
import pytest

from sphinx.config import load_config
from sphinx.strategy.signals import evaluate_day
from sphinx.strategy.state_machine import StateMachine, State

CFG = load_config()


def synth_day(prices_by_minute):
    """prices_by_minute: dict {t: close}; builds flat OHLC bars."""
    ts = sorted(prices_by_minute)
    c = np.array([prices_by_minute[t] for t in ts], dtype=float)
    return {"t": np.array(ts), "o": c.copy(), "h": c + 0.01, "l": c - 0.01,
            "c": c, "v": np.ones_like(c) * 1000}


def sess_row(prev_close=100.0, atr14=1.0, rv20=0.20, half=False):
    return pd.Series({"prev_close": prev_close, "atr14": atr14, "rv20": rv20,
                      "is_half_day": half, "close": prev_close, "sma200": prev_close})


def full_day(up=True):
    px0, drift = 100.0, (1.0 if up else -1.0)
    d = {}
    for i, t in enumerate(range(570, 960)):
        d[t] = px0 + drift * (i / 390) * 2
    return synth_day(d)


def test_long_signal_when_both_positive_and_vol_ok():
    sig = evaluate_day("d", full_day(True), sess_row(), CFG, True)
    assert sig.result == "LONG" and sig.direction == 1
    assert sig.stop_px < sig.entry_ref_px


def test_short_signal():
    sig = evaluate_day("d", full_day(False), sess_row(), CFG, True)
    assert sig.result == "SHORT" and sig.stop_px > sig.entry_ref_px


def test_low_vol_regime_blocks():
    sig = evaluate_day("d", full_day(True), sess_row(rv20=0.10), CFG, True)
    assert sig.result == "NO_TRADE" and sig.reason == "LOW_VOL_REGIME"


def test_half_day_blocks():
    sig = evaluate_day("d", full_day(True), sess_row(half=True), CFG, True)
    assert sig.reason == "HALF_DAY"


def test_invalid_session_blocks():
    sig = evaluate_day("d", full_day(True), sess_row(), CFG, False)
    assert sig.reason == "DATA_VALIDATION_FAILURE"


def test_disagreement_blocks():
    # early up, then well below prev close by 15:30
    d = {}
    for t in range(570, 600):
        d[t] = 100.4
    for t in range(600, 960):
        d[t] = 99.5
    sig = evaluate_day("d", synth_day(d), sess_row(), CFG, True)
    assert sig.reason == "NO_AGREEMENT"


def test_magnitude_threshold_blocks():
    # both positive but move < 0.10 * ATR% (ATR%=1% -> thr=0.1%)
    d = {t: 100.05 for t in range(570, 960)}
    sig = evaluate_day("d", synth_day(d), sess_row(), CFG, True)
    assert sig.reason == "MOVE_TOO_SMALL"


def test_no_lookahead_bars_after_1530_cannot_change_signal():
    base = full_day(True)
    m = base["t"] < 930
    truncated = {k: v[m] for k, v in base.items()}
    crashed = {k: v.copy() for k, v in base.items()}
    crashed["c"][~m] = 50.0  # absurd post-signal crash
    s1 = evaluate_day("d", truncated, sess_row(), CFG, True)
    s2 = evaluate_day("d", crashed, sess_row(), CFG, True)
    assert s1.result == s2.result == "LONG"
    assert s1.r_early == s2.r_early and s1.r_od == s2.r_od


def test_state_machine_rejects_illegal_transition():
    sm = StateMachine()
    sm.transition(State.WAITING_FOR_MARKET, "t")
    with pytest.raises(RuntimeError):
        sm.transition(State.POSITION_OPEN, "illegal jump")
