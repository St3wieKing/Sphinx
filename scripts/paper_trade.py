"""Paper-trading session runner (PHASE 13) — the only authorized mode.

Runs the frozen strategy through the identical production signal path
against a bar feed.  A ReplayFeed is provided for dry runs; a live feed
adapter must supply validated 1-minute RTH bars with bar-start timestamps.

Usage (replay of a past session for operational verification):
  python scripts/paper_trade.py 2024-08-05
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import numpy as np
import pandas as pd

from sphinx.config import load_config
from sphinx.data.loader import load_all, day_arrays
from sphinx.data.validation import valid_session_mask
from sphinx.strategy.signals import evaluate_day
from sphinx.strategy.state_machine import StateMachine, State
from sphinx.risk.sizing import shares_for
from sphinx.risk.limits import RiskState
from sphinx.execution.orders import Order
from sphinx.execution.paper_broker import PaperBroker
from sphinx.monitoring.logger import JsonLogger, Alert


def run_session(date_str: str, equity: float = 100_000.0):
    cfg = load_config()
    log = JsonLogger(stdout=True)
    sm = StateMachine(logger=log)
    risk = RiskState()
    broker = PaperBroker(logger=log)

    rth, sessions = load_all()
    d = pd.Timestamp(date_str)
    if d not in sessions.index:
        log.alert(Alert.DATA_FAILURE, f"no session {date_str}")
        return
    arr = day_arrays(rth.loc[rth.index.normalize() == d])[d]
    s = sessions.loc[d]
    valid = bool(valid_session_mask(sessions).loc[d])

    sm.transition(State.WAITING_FOR_MARKET, "session start")
    sm.transition(State.WAITING_FOR_SETUP, "market open")

    sig_t = cfg["signal"]["signal_time"]
    n = len(arr["t"])
    signal = None
    entry_order = stop_order = moc_order = None
    for i in range(n):
        t = int(arr["t"][i])
        bar = (float(arr["o"][i]), float(arr["h"][i]), float(arr["l"][i]),
               float(arr["c"][i]), i == n - 1)
        # evaluate signal exactly once, at the first bar >= signal_time
        if signal is None and t >= sig_t:
            upto = {k: v[: i] for k, v in arr.items()}   # only PAST bars
            signal = evaluate_day(d, upto, s, cfg, valid)
            log.info(signal.explain())
            if signal.result == "NO_TRADE" or not risk.can_trade():
                sm.transition(State.SESSION_LOCKED, signal.reason)
            else:
                sm.transition(State.SETUP_DETECTED, "SETUP-01/02 true")
                qty = shares_for(equity, signal.entry_ref_px, s["atr14"], s["prev_close"], cfg)
                side = "BUY" if signal.direction > 0 else "SELL"
                lim = signal.entry_ref_px * (1 + signal.direction * cfg["entry"]["max_entry_slippage_bps"] / 1e4)
                entry_order = broker.submit(Order("SPHINX-LHM", f"SIG-{date_str}", "ENTRY-01",
                                                  side, qty, "LIMIT", limit_px=lim,
                                                  intended_px=signal.entry_ref_px))
                sm.transition(State.ENTRY_PENDING, "entry submitted")
        fills = broker.on_bar(*bar)
        for od, px, why in fills:
            if od is entry_order:
                sm.transition(State.POSITION_OPEN, f"entry fill {px:.4f}")
                slip_bps = abs(px - od.intended_px) / od.intended_px * 1e4
                if slip_bps > cfg["entry"]["max_entry_slippage_bps"]:
                    log.alert(Alert.ABNORMAL_SLIPPAGE, f"{slip_bps:.2f}bps")
                xside = "SELL" if od.side == "BUY" else "BUY"
                stop_order = broker.submit(Order("SPHINX-LHM", f"SIG-{date_str}", "STOP-01",
                                                 xside, od.qty, "STOP", stop_px=signal.stop_px))
                moc_order = broker.submit(Order("SPHINX-LHM", f"SIG-{date_str}", "EXIT-01",
                                                xside, od.qty, "MOC"))
            elif od in (stop_order, moc_order):
                other = moc_order if od is stop_order else stop_order
                if other and other.status == "SUBMITTED":
                    broker.om.cancel(other.order_id, "OCO")
                sm.transition(State.EXIT_PENDING, f"exit fill via {od.rule_id}")
                sm.transition(State.IDLE, "flat")
                ret = (px / entry_order.fill_px - 1) * (1 if entry_order.side == "BUY" else -1)
                risk.record_trade(ret, cfg)
                log.info(f"TRADE CLOSED ret={ret*1e4:.2f}bps reason={why}")
        # entry timeout: not filled by 15:31 -> cancel
        if entry_order and entry_order.status == "SUBMITTED" and t >= sig_t + 1:
            broker.om.cancel(entry_order.order_id, "EXEC-02 timeout")
            sm.transition(State.SESSION_LOCKED, "missed entry, not chased")
            entry_order = None
    if sm.state in (State.WAITING_FOR_SETUP,):
        sm.transition(State.SESSION_LOCKED, "no setup today")
    print(f"\nfinal state: {sm.state.name}, paper position: {broker.position}")


if __name__ == "__main__":
    run_session(sys.argv[1] if len(sys.argv) > 1 else "2024-08-05")
