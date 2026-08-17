"""Position sizing (rule SIZE-01) — predetermined risk limits only.

notional_frac = min(leverage_cap, risk_budget_frac / (risk_proxy_atr_mult * atr14/prev_close))
shares        = floor(equity * notional_frac / entry_price)

The risk proxy (0.30 * ATR%) is a conservative estimate of the adverse move
achievable in the 30-minute holding window.  Sizing never depends on signal
'confidence'; only on predetermined risk constraints and volatility.
"""
from __future__ import annotations

import math


def notional_fraction(atr14: float, prev_close: float, cfg) -> float:
    sz = cfg["sizing"]
    atr_frac = atr14 / prev_close
    if atr_frac <= 0:
        return 0.0
    frac = sz["risk_budget_frac"] / (sz["risk_proxy_atr_mult"] * atr_frac)
    return min(frac, sz["leverage_cap"])


def shares_for(equity: float, entry_px: float, atr14: float, prev_close: float, cfg) -> int:
    if entry_px <= 0 or equity <= 0:
        return 0
    frac = notional_fraction(atr14, prev_close, cfg)
    frac = min(frac, cfg["risk_limits"]["max_position_notional_frac"])
    return int(math.floor(equity * frac / entry_px))
