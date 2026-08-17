"""Conservative intrabar fill simulation on 1-minute bars.

Rules (identical for research and fidelity tests):

Stop-entry (buy stop at S, long):
  * if bar.open >= S -> filled at bar.open
  * elif bar.high >= S -> filled at S
Protective stop (long, stop at S):
  * if bar.open <= S -> filled at bar.open (gap through)
  * elif bar.low <= S -> filled at S
Target (long, limit at T):
  * if bar.open >= T -> filled at bar.open
  * elif bar.high >= T -> filled at T
Ambiguity: when BOTH protective stop and target could fill inside the
same 1-minute bar, the STOP is assumed to fill first (conservative).
Costs are applied by the CostModel on top of these raw fill prices.
"""
from __future__ import annotations


def stop_entry_fill(direction: int, stop_px: float, o: float, h: float, l: float):
    if direction > 0:
        if o >= stop_px:
            return o
        if h >= stop_px:
            return stop_px
    else:
        if o <= stop_px:
            return o
        if l <= stop_px:
            return stop_px
    return None


def protective_stop_fill(direction: int, stop_px: float, o: float, h: float, l: float):
    if direction > 0:  # long, sell stop below
        if o <= stop_px:
            return o
        if l <= stop_px:
            return stop_px
    else:              # short, buy stop above
        if o >= stop_px:
            return o
        if h >= stop_px:
            return stop_px
    return None


def target_fill(direction: int, target_px: float, o: float, h: float, l: float):
    if direction > 0:  # long, sell limit above
        if o >= target_px:
            return o
        if h >= target_px:
            return target_px
    else:
        if o <= target_px:
            return o
        if l <= target_px:
            return target_px
    return None
