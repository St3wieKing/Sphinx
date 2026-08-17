"""Walk-forward analysis (expanding window, yearly reselection).

For each year Y in 2008..2020: select (predictor, min_move_frac, rv20_min)
from the pre-defined grid using ONLY data < Y (criterion: per-trade t-stat,
minimum 150 trades in the lookback), then trade year Y with the selection.
The final locked test period (2021+) is NOT touched here.
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
from sphinx.backtest import metrics as M
import candidates as C
from tournament import run_candidate

GRID = [{"predictor": p, "entry_time": 930, "min_move_frac": mm, "rv20_min": v}
        for p in ("r1", "rod", "both")
        for mm in (0.0, 0.10, 0.25)
        for v in (0.0, 0.10, 0.15, 0.20)]


def run_cfg(cfg, days, sessions, arrs, costs):
    sub = [d for d in days if sessions.loc[d, "rv20"] >= cfg["rv20_min"]]
    p = {k: v for k, v in cfg.items() if k != "rv20_min"}
    return run_candidate("C5", C.c5_intraday_momentum, p, sub, sessions, arrs, costs)


def main():
    costs = CostModel()
    rth, sessions = load_all()
    arrs = day_arrays(rth)
    mask = valid_session_mask(sessions)
    all_days = sessions.index[mask & (sessions.index >= "2003-01-02") & (sessions.index <= "2020-12-31")]

    picks, oos_frames = [], []
    for year in range(2008, 2021):
        lookback = [d for d in all_days if d.year < year]
        target = [d for d in all_days if d.year == year]
        best, best_t = None, -1e9
        for cfg in GRID:
            tf = run_cfg(cfg, lookback, sessions, arrs, costs)
            if len(tf) < 150:
                continue
            sc = M.scorecard(tf)
            if sc["t_stat"] > best_t:
                best_t, best = sc["t_stat"], cfg
        tf_oos = run_cfg(best, target, sessions, arrs, costs)
        sc_oos = M.scorecard(tf_oos) if len(tf_oos) else {"trades": 0}
        picks.append({"year": year, **best, "lookback_t": best_t,
                      "oos_trades": sc_oos.get("trades", 0),
                      "oos_exp_bps": sc_oos.get("expectancy_bps", float("nan")),
                      "oos_win": sc_oos.get("win_rate", float("nan"))})
        if len(tf_oos):
            oos_frames.append(tf_oos)

    pk = pd.DataFrame(picks)
    print("=== walk-forward parameter picks & yearly OOS ===")
    print(pk.round(3).to_string(index=False))
    pk.to_csv("research/outputs/walkforward_picks.csv", index=False)

    oos = pd.concat(oos_frames, ignore_index=True)
    sc = M.scorecard(oos)
    print("\n=== concatenated walk-forward OOS 2008-2020 ===")
    print(pd.Series(sc).round(4).to_string())
    oos.to_csv("research/outputs/walkforward_oos_trades.csv", index=False)


if __name__ == "__main__":
    main()
