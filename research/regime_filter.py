"""Regime-filter definition — TRAIN ONLY sweep, then one VAL confirmation.

Filter form (pre-specified, mechanism-based, single parameter):
    trade only when rv20 >= V  (rv20 = annualized stdev of the prior 20
    close-to-close returns — strictly prior data, self-contained).

The threshold is chosen on TRAIN as the middle of a positive, stable
plateau (NOT the argmax).  VAL is then evaluated ONCE for confirmation.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd

from sphinx.data.loader import load_all, day_arrays
from sphinx.backtest.costs import CostModel
from sphinx.backtest import metrics as M
import candidates as C
from tournament import run_candidate, get_days

BASE = {"predictor": "both", "entry_time": 930, "min_move_frac": 0.10}
SIMPLE = {"predictor": "both", "entry_time": 930, "min_move_frac": 0.0}


def run_filtered(params, days, sessions, arrs, costs, vmin):
    sub = [d for d in days if sessions.loc[d, "rv20"] >= vmin]
    return run_candidate("C5", C.c5_intraday_momentum, params, sub, sessions, arrs, costs)


def sweep(split, base=BASE, thresholds=(0.0, 0.10, 0.125, 0.15, 0.175, 0.20, 0.225, 0.25, 0.30)):
    costs = CostModel()
    rth, sessions = load_all()
    arrs = day_arrays(rth)
    days = get_days(sessions, split)
    rows = {}
    for v in thresholds:
        tf = run_filtered(base, days, sessions, arrs, costs, v)
        sc = M.scorecard(tf, sessions_in_period=len(days))
        rows[f"rv20>={v:.3f}"] = sc
    df = pd.DataFrame(rows).T
    cols = ["trades", "trades_per_year", "win_rate", "expectancy_bps", "t_stat",
            "profit_factor", "sharpe", "max_dd", "participation"]
    print(f"\n=== rv20 threshold sweep on {split.upper()} (PRIMARY base) ===")
    print(df[cols].round(3).to_string())
    df.to_csv(f"research/outputs/rv20_sweep_{split}.csv")
    return df


if __name__ == "__main__":
    sweep(sys.argv[1] if len(sys.argv) > 1 else "train")
