"""Parameter-sensitivity maps per candidate family — TRAIN ONLY.

No result from this file is allowed to touch the validation or final test
periods.  Emits one grid per family to research/outputs/.
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


def grid(name, fn, plist, days, sessions, arrs, costs):
    rows = []
    for p in plist:
        tf = run_candidate(name, fn, p, days, sessions, arrs, costs)
        sc = M.scorecard(tf)
        sc["params"] = str(p)
        rows.append(sc)
    df = pd.DataFrame(rows).set_index("params")
    cols = [c for c in ["trades", "win_rate", "expectancy_bps", "t_stat",
                        "profit_factor", "sharpe", "max_dd", "stop_rate"] if c in df.columns]
    df = df[cols]
    print(f"\n=== {name} ===")
    print(df.round(3).to_string())
    df.to_csv(f"research/outputs/grid_train_{name}.csv")
    return df


def main():
    costs = CostModel()
    rth, sessions = load_all()
    arrs = day_arrays(rth)
    days = get_days(sessions, "train")

    # C1 family
    grid("C1", C.c1_orb_immediate,
         [{"or_minutes": m, "target_R": r} for m in (5, 15, 30) for r in (None, 5, 10)],
         days, sessions, arrs, costs)

    # C2 family
    grid("C2", C.c2_orb_breakout,
         [{"or_minutes": m, "cancel_time": ct, "target_R": r}
          for m in (5, 15, 30) for ct in (660, 720, 780) for r in (None, 2)],
         days, sessions, arrs, costs)

    # C4 family
    grid("C4", "custom_vwap",
         [{"entry_atr": a, "stop_atr": b} for a in (0.4, 0.5, 0.75, 1.0) for b in (1.0, 1.5)],
         days, sessions, arrs, costs)

    # C6 family
    grid("C6", C.c6_gap_fade,
         [{"min_gap_atr": lo, "max_gap_atr": hi, "stop_gap_mult": sm}
          for lo in (0.2, 0.3, 0.5) for hi in (1.5, 2.0) for sm in (1.0, 1.5)],
         days, sessions, arrs, costs)

    # C5 family — predictor / timing / filter / stop
    plist = []
    for pred in ("r1", "rod", "both"):
        for entry_t in (900, 930):
            for mm in (0.0, 0.1, 0.25):
                plist.append({"predictor": pred, "entry_time": entry_t, "min_move_frac": mm})
    for sa in (0.5, 1.0):  # stop variants on the base config
        plist.append({"predictor": "both", "entry_time": 930, "min_move_frac": 0.0, "stop_atr": sa})
    g5 = grid("C5", C.c5_intraday_momentum, plist, days, sessions, arrs, costs)

    # yearly stability for headline C5 configs
    for pred in ("r1", "rod", "both"):
        tf = run_candidate("C5", C.c5_intraday_momentum,
                           {"predictor": pred, "entry_time": 930}, days, sessions, arrs, costs)
        yr = M.by_year(tf)
        print(f"\n--- yearly C5 {pred} (train) ---")
        print(yr.round(2).to_string())
        yr.to_csv(f"research/outputs/yearly_train_C5_{pred}.csv")


if __name__ == "__main__":
    main()
