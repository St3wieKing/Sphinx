"""Tournament runner — pre-registered protocol.

Splits (fixed BEFORE any strategy was evaluated; the final test period is
locked and only run once, after the winning strategy is frozen):
  TRAIN      2003-01-02 .. 2014-12-31
  VALIDATION 2015-01-02 .. 2020-12-31
  FINAL TEST 2021-01-04 .. end of data   <-- LOCKED

Usage:
  python research/tournament.py train        # candidates on TRAIN
  python research/tournament.py val          # frozen candidates on VALIDATION
  python research/tournament.py test C5 ...  # ONE-SHOT locked final test
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd

from sphinx.data.loader import load_all, day_arrays
from sphinx.data.validation import valid_session_mask
from sphinx.backtest.costs import CostModel
from sphinx.backtest.engine import simulate_day
from sphinx.backtest import metrics as M
import candidates as C

SPLITS = {
    "burnin": ("2000-01-01", "2002-12-31"),
    "train": ("2003-01-02", "2014-12-31"),
    "val": ("2015-01-02", "2020-12-31"),
    "test": ("2021-01-04", "2099-01-01"),
}

CANDS = {
    "C1_ORB5_imm": (C.c1_orb_immediate, {"or_minutes": 5}),
    "C1_ORB5_imm_10R": (C.c1_orb_immediate, {"or_minutes": 5, "target_R": 10}),
    "C2_ORB5_bo": (C.c2_orb_breakout, {"or_minutes": 5, "cancel_time": 720}),
    "C2_ORB15_bo": (C.c2_orb_breakout, {"or_minutes": 15, "cancel_time": 720}),
    "C2_ORB30_bo": (C.c2_orb_breakout, {"or_minutes": 30, "cancel_time": 720}),
    "C4_vwap_a50_b100": ("custom_vwap", {"entry_atr": 0.5, "stop_atr": 1.0}),
    "C5_imom_r1": (C.c5_intraday_momentum, {"predictor": "r1"}),
    "C5_imom_rod": (C.c5_intraday_momentum, {"predictor": "rod"}),
    "C5_imom_both": (C.c5_intraday_momentum, {"predictor": "both"}),
    "C6_gapfade": (C.c6_gap_fade, {"min_gap_atr": 0.3, "max_gap_atr": 2.0}),
}


def run_candidate(name, fn, params, days, sessions, arrs, costs):
    trades = []
    for d in days:
        arr = arrs.get(d)
        if arr is None:
            continue
        s = sessions.loc[d]
        if fn == "custom_vwap":
            tr = C.c4_vwap_revert_custom(d, arr, s, params, costs)
        else:
            plan = fn(d, arr, s, params)
            tr = simulate_day(d, arr, plan, costs) if plan else None
        if tr:
            trades.append(tr)
    return M.trades_frame(trades)


def get_days(sessions, split):
    a, b = SPLITS[split]
    mask = valid_session_mask(sessions)
    idx = sessions.index[(sessions.index >= a) & (sessions.index <= b) & mask]
    return list(idx)


def main():
    split = sys.argv[1] if len(sys.argv) > 1 else "train"
    only = sys.argv[2:] or None
    costs = CostModel()
    rth, sessions = load_all()
    arrs = day_arrays(rth)
    days = get_days(sessions, split)
    print(f"split={split} sessions={len(days)} costs/side=${costs.per_side:.4f}")
    rows = {}
    for name, (fn, params) in CANDS.items():
        if only and name not in only:
            continue
        tf = run_candidate(name, fn, params, days, sessions, arrs, costs)
        sc = M.scorecard(tf, sessions_in_period=len(days))
        rows[name] = sc
        tf.to_csv(f"research/outputs/trades_{split}_{name}.csv", index=False)
    out = pd.DataFrame(rows).T
    pd.set_option("display.width", 250)
    print(out.round(3).to_string())
    out.to_csv(f"research/outputs/scorecards_{split}.csv")


if __name__ == "__main__":
    main()
