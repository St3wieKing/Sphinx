"""Production backtest of the FROZEN strategy through the production signal
path (sphinx.strategy.signals).  This is the code the paper trader runs; the
research candidates are NOT used here.  Emits a full audit-trail trade log.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import load_config
from ..data.loader import load_all, day_arrays
from ..data.validation import valid_session_mask
from ..strategy.signals import evaluate_day
from ..risk.sizing import shares_for, notional_fraction
from ..risk.limits import RiskState
from .costs import CostModel
from .engine import DayPlan, simulate_day
from . import metrics as M


def run_frozen(start: str, end: str, cfg=None, costs: CostModel = None,
               equity0: float = 100_000.0):
    cfg = cfg or load_config()
    costs = costs or CostModel(
        commission=cfg["costs_model"]["commission_per_share"],
        half_spread=cfg["costs_model"]["half_spread"],
        slippage=cfg["costs_model"]["slippage"],
        stop_gap_extra=cfg["costs_model"]["stop_gap_extra"],
    )
    rth, sessions = load_all()
    arrs = day_arrays(rth)
    mask = valid_session_mask(
        sessions,
        min_bars_full=cfg["data_requirements"]["min_bars_full_session"],
    )
    days = sessions.index[(sessions.index >= start) & (sessions.index <= end)]

    risk = RiskState()
    equity = equity0
    rows, signals = [], []
    for d in days:
        risk.new_session()
        arr = arrs.get(d)
        s = sessions.loc[d]
        valid = bool(mask.loc[d]) and arr is not None
        sig = evaluate_day(d, arr if arr is not None else {"t": np.array([])},
                           s, cfg, valid)
        signals.append(sig)
        if sig.result == "NO_TRADE":
            continue
        if not risk.can_trade():
            continue
        plan = DayPlan(direction=sig.direction, entry_type="market_at",
                       entry_time=cfg["entry"]["entry_time"],
                       stop_px=sig.stop_px, target_px=None, exit_time=None,
                       meta={"rules": "ENTRY-01,STOP-01,EXIT-01"})
        tr = simulate_day(d, arr, plan, costs)
        if tr is None:
            continue
        qty = shares_for(equity, tr.entry_px_raw, s["atr14"], s["prev_close"], cfg)
        nf = notional_fraction(s["atr14"], s["prev_close"], cfg)
        ret_on_equity = nf * tr.ret
        equity *= (1.0 + ret_on_equity)
        risk.record_trade(ret_on_equity, cfg)
        rows.append({
            "trade_id": f"LHM-{pd.Timestamp(d).date()}",
            "date": d, "direction": tr.direction, "qty": qty,
            "entry_time": tr.entry_time, "exit_time": tr.exit_time,
            "entry_px_raw": tr.entry_px_raw, "entry_px_net": tr.entry_px,
            "exit_px_raw": tr.exit_px_raw, "exit_px_net": tr.exit_px,
            "exit_reason": tr.exit_reason, "stop_px": tr.stop_px,
            "r_early": sig.r_early, "r_od": sig.r_od,
            "notional_frac": nf,
            "pnl_ps": tr.pnl_per_share, "ret": tr.ret, "bps": tr.ret * 1e4,
            "ret_on_equity": ret_on_equity, "equity_after": equity,
            "risk_ps": tr.risk_per_share, "r_mult": tr.r_multiple,
            "rules": "FILT-01..03,SETUP-01..02,ENTRY-01,STOP-01,EXIT-01,SIZE-01",
        })
    tf = pd.DataFrame(rows)
    return tf, signals, equity


def summarize(tf: pd.DataFrame, sessions_in_period=None):
    if tf.empty:
        return {"trades": 0}
    m = M.scorecard(tf.rename(columns={"entry_px_net": "entry_px", "exit_px_net": "exit_px"})
                    .assign(risk_ps=tf["risk_ps"]),
                    sessions_in_period=sessions_in_period)
    eq = tf["equity_after"]
    peak = eq.cummax()
    m["max_dd_sized"] = float((eq / peak - 1).min())
    m["final_equity_mult"] = float(eq.iloc[-1] / (eq.iloc[0] / (1 + tf["ret_on_equity"].iloc[0])))
    return m
