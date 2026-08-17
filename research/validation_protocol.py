"""Validation-phase protocol (pre-registered).

Committed BEFORE looking at 2015-2020 data:
  PRIMARY : C5 predictor='both', entry 15:30, min_move_frac=0.10, no stop
  SIMPLE  : C5 predictor='both', entry 15:30, min_move_frac=0.00, no stop
Robustness (reported, not used for selection): mm in {0.05,0.15,0.25},
predictors r1/rod alone, entry 15:00, disaster stop 2*ATR.
Cost stress on TRAIN and VAL: stress in {1.0, 2.0, 3.0}.
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

PRIMARY = {"predictor": "both", "entry_time": 930, "min_move_frac": 0.10}
SIMPLE = {"predictor": "both", "entry_time": 930, "min_move_frac": 0.0}

ROBUST = {
    "mm_0.05": {"predictor": "both", "entry_time": 930, "min_move_frac": 0.05},
    "mm_0.15": {"predictor": "both", "entry_time": 930, "min_move_frac": 0.15},
    "mm_0.25": {"predictor": "both", "entry_time": 930, "min_move_frac": 0.25},
    "r1_only": {"predictor": "r1", "entry_time": 930, "min_move_frac": 0.10},
    "rod_only": {"predictor": "rod", "entry_time": 930, "min_move_frac": 0.10},
    "entry_1500": {"predictor": "both", "entry_time": 900, "min_move_frac": 0.10},
    "disaster_stop": {"predictor": "both", "entry_time": 930, "min_move_frac": 0.10, "stop_atr": 2.0},
}


def run(split):
    rth, sessions = load_all()
    arrs = day_arrays(rth)
    days = get_days(sessions, split)
    rows = {}
    for label, params in {"PRIMARY": PRIMARY, "SIMPLE": SIMPLE, **ROBUST}.items():
        tf = run_candidate("C5", C.c5_intraday_momentum, params, days, sessions, arrs, CostModel())
        rows[label] = M.scorecard(tf, sessions_in_period=len(days))
        tf.to_csv(f"research/outputs/trades_{split}_C5_{label}.csv", index=False)
        if label in ("PRIMARY", "SIMPLE"):
            print(f"\n--- yearly {label} ({split}) ---")
            print(M.by_year(tf).round(2).to_string())
            print(f"--- regimes {label} ({split}) ---")
            print(M.by_regime(tf, sessions).round(2).to_string())
    df = pd.DataFrame(rows).T
    print(f"\n=== C5 configs on {split.upper()} (base costs) ===")
    print(df.round(3).to_string())
    df.to_csv(f"research/outputs/validation_{split}.csv")

    # cost stress on PRIMARY
    stress_rows = {}
    for st in (1.0, 2.0, 3.0):
        cm = CostModel(stress=st)
        tf = run_candidate("C5", C.c5_intraday_momentum, PRIMARY, days, sessions, arrs, cm)
        stress_rows[f"stress_x{st}"] = M.scorecard(tf)
    sdf = pd.DataFrame(stress_rows).T
    print(f"\n=== PRIMARY cost stress on {split.upper()} ===")
    print(sdf[["trades", "expectancy_bps", "t_stat", "profit_factor", "sharpe", "max_dd"]].round(3).to_string())
    sdf.to_csv(f"research/outputs/cost_stress_{split}.csv")

    # Monte Carlo on PRIMARY
    tf = run_candidate("C5", C.c5_intraday_momentum, PRIMARY, days, sessions, arrs, CostModel())
    mc = M.monte_carlo_dd(tf)
    print(f"\n=== PRIMARY Monte Carlo ({split}) ===\n{mc}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "train")
