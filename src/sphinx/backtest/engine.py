"""Event-driven day simulator.

A strategy hands the engine one `DayPlan` per session (or None = no trade).
The engine walks the session's 1-minute bars chronologically and produces
at most one trade, applying the shared fill rules and cost model.
This engine knows nothing about WHY a plan exists — it only executes it,
so no strategy logic can leak into execution.

DayPlan fields
--------------
direction     : +1 long / -1 short
entry_type    : 'market_at' (marketable order at bar open of entry_time)
                'stop' (stop-entry at entry_px, armed from entry_time)
entry_time    : minutes-since-midnight; order active from this bar on
entry_px      : required for entry_type='stop'
cancel_time   : stop-entries not filled by this time are cancelled
stop_px       : protective stop (absolute price), may be None
target_px     : profit target (absolute price), may be None
exit_time     : forced flat time (minutes since midnight); the engine
                exits at the OPEN of the first bar at/after exit_time,
                or at the session's last bar close if exit_time is at or
                beyond the session end (MOC proxy).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..backtest.costs import CostModel
from ..execution.fills import stop_entry_fill, protective_stop_fill, target_fill


@dataclass
class DayPlan:
    direction: int
    entry_type: str
    entry_time: int
    entry_px: Optional[float] = None
    cancel_time: Optional[int] = None
    stop_px: Optional[float] = None
    target_px: Optional[float] = None
    exit_time: Optional[int] = None
    meta: Optional[dict] = None


@dataclass
class Trade:
    date: object
    direction: int
    entry_time: int
    entry_px: float          # net of costs
    entry_px_raw: float
    exit_time: int
    exit_px: float           # net of costs
    exit_px_raw: float
    exit_reason: str         # 'stop' | 'target' | 'time' | 'eod'
    stop_px: Optional[float]
    target_px: Optional[float]
    meta: Optional[dict] = None

    @property
    def pnl_per_share(self) -> float:
        return self.direction * (self.exit_px - self.entry_px)

    @property
    def risk_per_share(self) -> Optional[float]:
        if self.stop_px is None:
            return None
        return abs(self.entry_px_raw - self.stop_px)

    @property
    def r_multiple(self) -> Optional[float]:
        r = self.risk_per_share
        if not r:
            return None
        return self.pnl_per_share / r

    @property
    def ret(self) -> float:
        """Net simple return on entry notional."""
        return self.direction * (self.exit_px - self.entry_px) / self.entry_px_raw


def simulate_day(date, arr, plan: DayPlan, costs: CostModel) -> Optional[Trade]:
    """Run one DayPlan over one day's 1-minute arrays."""
    t, o, h, l, c = arr["t"], arr["o"], arr["h"], arr["l"], arr["c"]
    n = len(t)
    d = plan.direction
    in_pos = False
    e_raw = e_net = None
    e_time = None
    last_close = c[-1]
    session_end = t[-1]

    for i in range(n):
        ti = t[i]
        if not in_pos:
            if plan.cancel_time is not None and ti >= plan.cancel_time:
                return None
            if plan.entry_type == "market_at":
                if ti >= plan.entry_time:
                    e_raw = o[i]
                    e_net = costs.entry_price(e_raw, d)
                    e_time = ti
                    in_pos = True
                    # same-bar exit checks fall through below
                else:
                    continue
            elif plan.entry_type == "stop":
                if ti >= plan.entry_time:
                    f = stop_entry_fill(d, plan.entry_px, o[i], h[i], l[i])
                    if f is None:
                        continue
                    e_raw = f
                    e_net = costs.entry_price(f, d)
                    e_time = ti
                    in_pos = True
                else:
                    continue
            else:
                raise ValueError(plan.entry_type)

        # position open: check forced time exit first if this bar's open is
        # at/after exit_time (we exit at the bar open)
        if plan.exit_time is not None and ti >= plan.exit_time and ti > e_time:
            x_raw = o[i]
            x_net = costs.exit_price(x_raw, d, is_stop=False)
            return Trade(date, d, e_time, e_net, e_raw, ti, x_net, x_raw,
                         "time", plan.stop_px, plan.target_px, plan.meta)

        # stop first (conservative), then target — on entry bar, only price
        # action after entry can trigger; we conservatively still use bar
        # extremes (slightly pessimistic for stops).
        if plan.stop_px is not None:
            f = protective_stop_fill(d, plan.stop_px, o[i] if ti > e_time else e_raw, h[i], l[i])
            if f is not None:
                x_net = costs.exit_price(f, d, is_stop=True)
                return Trade(date, d, e_time, e_net, e_raw, ti, x_net, f,
                             "stop", plan.stop_px, plan.target_px, plan.meta)
        if plan.target_px is not None:
            f = target_fill(d, plan.target_px, o[i] if ti > e_time else e_raw, h[i], l[i])
            if f is not None:
                x_net = costs.exit_price(f, d, is_stop=False)
                return Trade(date, d, e_time, e_net, e_raw, ti, x_net, f,
                             "target", plan.stop_px, plan.target_px, plan.meta)

    if in_pos:
        # flat on close (MOC proxy at last RTH bar close)
        x_raw = last_close
        x_net = costs.exit_price(x_raw, d, is_stop=False)
        return Trade(date, d, e_time, e_net, e_raw, session_end, x_net, x_raw,
                     "eod", plan.stop_px, plan.target_px, plan.meta)
    return None
