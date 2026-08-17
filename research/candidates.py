"""Candidate strategy definitions for the tournament.

Every candidate is a function:  (date, arr, sess_row, params) -> DayPlan | None
All rules are 100% objective; all reference values (prev_close, atr14, ...)
are strictly prior-day quantities; all intraday values are available at the
moment the plan element is armed.  One trade per day maximum, always flat
by the close, no overnight risk.

Time convention: minutes since midnight ET (09:30 = 570, 16:00 = 960).
"""
from __future__ import annotations

import numpy as np

from sphinx.backtest.engine import DayPlan

OPEN_T = 570
TICK = 0.01


def _or_range(arr, minutes: int):
    """High/low/open/close of the first `minutes` of the session."""
    t = arr["t"]
    m = (t >= OPEN_T) & (t < OPEN_T + minutes)
    if not m.any():
        return None
    return (arr["h"][m].max(), arr["l"][m].min(),
            arr["o"][m][0], arr["c"][m][-1], int(m.sum()))


# ---------------------------------------------------------------- C1
def c1_orb_immediate(date, arr, s, p):
    """Zarattini/Aziz-style: direction of first 5-min candle, market entry at
    09:35, stop at opposite extreme of the first candle, optional R target,
    otherwise exit on close."""
    orm = p.get("or_minutes", 5)
    r = _or_range(arr, orm)
    if r is None or r[4] < orm - 1:
        return None
    hi, lo, o5, c5, _ = r
    if c5 > o5:
        d, stop = 1, lo
    elif c5 < o5:
        d, stop = -1, hi
    else:
        return None
    risk = abs(c5 - stop)
    if risk < p.get("min_risk_ticks", 2) * TICK:
        return None
    tgt = None
    if p.get("target_R"):
        tgt = c5 + d * p["target_R"] * risk
    return DayPlan(direction=d, entry_type="market_at", entry_time=OPEN_T + orm,
                   stop_px=stop, target_px=tgt, exit_time=None,
                   meta={"cand": f"C1_ORB{orm}_imm"})


# ---------------------------------------------------------------- C2
def c2_orb_breakout(date, arr, s, p):
    """Classic ORB: stop-entry one tick beyond the opening range, direction =
    first side broken (days breaking both sides within one minute are
    skipped as ambiguous), stop at opposite side of range, EOD exit."""
    orm = p.get("or_minutes", 5)
    r = _or_range(arr, orm)
    if r is None or r[4] < orm - 1:
        return None
    hi, lo, _, _, _ = r
    rng = hi - lo
    if rng < p.get("min_range_ticks", 4) * TICK:
        return None
    if p.get("max_range_atr") and rng > p["max_range_atr"] * s["atr14"]:
        return None
    t, h, l = arr["t"], arr["h"], arr["l"]
    up_px, dn_px = hi + TICK, lo - TICK
    after = t >= OPEN_T + orm
    cancel = p.get("cancel_time", 720)
    live = after & (t < cancel)
    up_hit = h >= up_px
    dn_hit = l <= dn_px
    idx = np.nonzero(live & (up_hit | dn_hit))[0]
    if len(idx) == 0:
        return None
    i = idx[0]
    if up_hit[i] and dn_hit[i]:
        return None  # ambiguous 1-min bar
    d = 1 if up_hit[i] else -1
    entry_px = up_px if d == 1 else dn_px
    stop = lo - TICK if d == 1 else hi + TICK
    if p.get("stop_mode") == "half":
        mid = (hi + lo) / 2
        stop = mid
    tgt = None
    if p.get("target_R"):
        tgt = entry_px + d * p["target_R"] * abs(entry_px - stop)
    return DayPlan(direction=d, entry_type="stop", entry_time=OPEN_T + orm,
                   entry_px=entry_px, cancel_time=cancel, stop_px=stop,
                   target_px=tgt, exit_time=None,
                   meta={"cand": f"C2_ORB{orm}_bo"})


# ---------------------------------------------------------------- C5
def c5_intraday_momentum(date, arr, s, p):
    """Market intraday momentum (Gao/Han/Li/Zhou 2018): sign of the opening
    return (prev close -> HH:MM) traded over the last window of the day.

    predictor='r1'  : prev_close -> 10:00
    predictor='rod' : prev_close -> 15:30
    predictor='both': trade only when r1 and rod agree
    Entry market at 15:30 (t=930), exit on close (MOC proxy).
    Optional filter: |predictor| >= min_move_frac * atr14/prev_close.
    Half-day sessions are skipped (no 15:30)."""
    if s["is_half_day"]:
        return None
    t, c = arr["t"], arr["c"]
    entry_t = p.get("entry_time", 930)
    m1 = t < 600            # bars before 10:00
    mE = t < entry_t
    if not m1.any() or not mE.any():
        return None
    pc = s["prev_close"]
    r1 = c[m1][-1] / pc - 1.0
    rod = c[mE][-1] / pc - 1.0
    pred = p.get("predictor", "r1")
    if pred == "r1":
        sig = np.sign(r1)
        mag = abs(r1)
    elif pred == "rod":
        sig = np.sign(rod)
        mag = abs(rod)
    else:
        if np.sign(r1) != np.sign(rod):
            return None
        sig = np.sign(r1)
        mag = min(abs(r1), abs(rod))
    if sig == 0:
        return None
    thr = p.get("min_move_frac", 0.0) * (s["atr14"] / pc)
    if mag < thr:
        return None
    stop = None
    if p.get("stop_atr"):
        mEi = np.nonzero(mE)[0][-1]
        px = c[mEi]
        stop = px - sig * p["stop_atr"] * s["atr14"]
    return DayPlan(direction=int(sig), entry_type="market_at", entry_time=entry_t,
                   stop_px=stop, target_px=None, exit_time=None,
                   meta={"cand": f"C5_imom_{pred}"})


# ---------------------------------------------------------------- C6
def c6_gap_fade(date, arr, s, p):
    """Fade the overnight gap toward the prior close.
    Trade only when min_gap <= |gap|/ATR% <= max_gap.  Enter market at 09:31,
    target = prior close, stop = gap-size multiple beyond entry, EOD exit."""
    pc = s["prev_close"]
    atr_frac = s["atr14"] / pc
    gap = s["gap"]
    if atr_frac <= 0 or np.isnan(gap):
        return None
    gsz = abs(gap) / atr_frac
    if gsz < p.get("min_gap_atr", 0.3) or gsz > p.get("max_gap_atr", 2.0):
        return None
    d = -1 if gap > 0 else 1
    o = arr["o"][0]
    stop_dist = p.get("stop_gap_mult", 1.0) * abs(o - pc)
    stop = o - d * stop_dist
    return DayPlan(direction=d, entry_type="market_at", entry_time=OPEN_T + 1,
                   stop_px=stop, target_px=pc, exit_time=None,
                   meta={"cand": "C6_gapfade"})


# ---------------------------------------------------------------- C4
def c4_vwap_revert_custom(date, arr, s, p, costs):
    """VWAP mean reversion — custom loop (dynamic exit at VWAP).
    From t_start to t_end: if close deviates more than a*ATR14 from session
    VWAP, fade toward VWAP.  Exit when close crosses VWAP, or stop at b*ATR14
    deviation, or 15:55 time exit.  One trade per day."""
    from sphinx.backtest.engine import Trade
    t, o, h, l, c, v = arr["t"], arr["o"], arr["h"], arr["l"], arr["c"], arr["v"]
    if s["is_half_day"]:
        return None
    atr = s["atr14"]
    a, b = p.get("entry_atr", 0.5), p.get("stop_atr", 1.0)
    t0, t1 = p.get("t_start", 630), p.get("t_end", 900)
    tp = (h + l + c) / 3.0
    cum_v = np.cumsum(v)
    cum_pv = np.cumsum(tp * v)
    vwap = np.where(cum_v > 0, cum_pv / np.maximum(cum_v, 1e-9), c)
    n = len(t)
    i = 0
    while i < n:
        if t[i] < t0:
            i += 1
            continue
        if t[i] >= t1:
            return None
        dev = c[i] - vwap[i]
        if dev > a * atr:
            d = -1
        elif dev < -a * atr:
            d = 1
        else:
            i += 1
            continue
        # enter at next bar open
        if i + 1 >= n:
            return None
        e_raw = o[i + 1]
        e_net = costs.entry_price(e_raw, d)
        e_time = t[i + 1]
        stop = vwap[i] - d * b * atr   # frozen at entry decision
        for j in range(i + 1, n):
            if t[j] >= 955:
                x_raw = o[j]
                return Trade(date, d, e_time, e_net, e_raw, t[j],
                             costs.exit_price(x_raw, d), x_raw, "time",
                             stop, None, {"cand": "C4_vwap"})
            f = None
            if d == 1 and l[j] <= stop:
                f = min(o[j], stop)
            elif d == -1 and h[j] >= stop:
                f = max(o[j], stop)
            if f is not None:
                return Trade(date, d, e_time, e_net, e_raw, t[j],
                             costs.exit_price(f, d, is_stop=True), f, "stop",
                             stop, None, {"cand": "C4_vwap"})
            if (d == 1 and c[j] >= vwap[j]) or (d == -1 and c[j] <= vwap[j]):
                if j + 1 < n:
                    x_raw = o[j + 1]
                    return Trade(date, d, e_time, e_net, e_raw, t[j + 1],
                                 costs.exit_price(x_raw, d), x_raw, "target",
                                 stop, None, {"cand": "C4_vwap"})
        x_raw = c[-1]
        return Trade(date, d, e_time, e_net, e_raw, t[-1],
                     costs.exit_price(x_raw, d), x_raw, "eod",
                     stop, None, {"cand": "C4_vwap"})
    return None
