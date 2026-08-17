"""FINAL LOCKED TEST — run exactly once, after the strategy freeze.

Steps:
 1. Fidelity: run the frozen production path on TRAIN and VAL and compare
    with the research-phase numbers (must reproduce).
 2. THE single locked evaluation on TEST (2021-01-04 .. end of data),
    including cost stress, yearly, regime and Monte Carlo breakdowns.
No strategy parameter may be changed after this file is executed.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pandas as pd

from sphinx.backtest.run_strategy import run_frozen, summarize
from sphinx.backtest.costs import CostModel
from sphinx.backtest import metrics as M
from sphinx.config import load_config
from sphinx.data.loader import load_all

OUT = os.path.join(os.path.dirname(__file__), "..", "research", "outputs")

SPLITS = {"train": ("2003-01-02", "2014-12-31"),
          "val": ("2015-01-02", "2020-12-31"),
          "test": ("2021-01-04", "2099-01-01")}


def norm(tf):
    return tf.rename(columns={"entry_px_net": "entry_px", "exit_px_net": "exit_px"})


def main():
    cfg = load_config()
    rth, sessions = load_all()
    for split, (a, b) in SPLITS.items():
        tf, signals, eq = run_frozen(a, b, cfg)
        n_sess = int(((sessions.index >= a) & (sessions.index <= b)).sum())
        sc = summarize(tf, sessions_in_period=n_sess)
        print(f"\n================ {split.upper()} {a}..{b} (frozen production path) ================")
        print(pd.Series(sc).round(4).to_string())
        tfn = norm(tf)
        print("\n-- yearly --")
        print(M.by_year(tfn).round(2).to_string())
        print("\n-- regimes --")
        print(M.by_regime(tfn, sessions).round(2).to_string())
        tf.to_csv(f"{OUT}/frozen_{split}_trades.csv", index=False)
        if split == "test":
            for st in (2.0, 3.0):
                cm = CostModel(
                    commission=cfg["costs_model"]["commission_per_share"],
                    half_spread=cfg["costs_model"]["half_spread"],
                    slippage=cfg["costs_model"]["slippage"],
                    stop_gap_extra=cfg["costs_model"]["stop_gap_extra"],
                    stress=st)
                tf2, _, _ = run_frozen(a, b, cfg, costs=cm)
                sc2 = summarize(tf2)
                print(f"\n-- TEST cost stress x{st} --")
                print(pd.Series({k: sc2[k] for k in ('trades', 'expectancy_bps', 't_stat', 'profit_factor', 'sharpe') if k in sc2}).round(4).to_string())
            mc = M.monte_carlo_dd(tfn)
            print("\n-- TEST Monte Carlo (trade resampling) --")
            print(mc)
            # NO_TRADE reason census
            reasons = pd.Series([s.reason for s in signals]).value_counts()
            print("\n-- TEST signal reason census --")
            print(reasons.to_string())


if __name__ == "__main__":
    main()
