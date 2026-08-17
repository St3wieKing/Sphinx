"""Operational risk limits (RISK-*).  These may only BLOCK trading; they can
never generate or modify an alpha signal.

RISK-01 daily loss lockout   : realized day loss > max_daily_loss_frac -> RISK_LOCKED for the day
RISK-02 rolling-20-trade loss: cumulative return of last 20 trades < -max_20trade_loss_frac
                               -> RISK_LOCKED until human review (paper mode)
RISK-03 position cap         : notional > max_position_notional_frac * equity -> order rejected
RISK-04 data failure counter : >= max_consecutive_data_failures -> RISK_LOCKED until data recovers
RISK-05 abnormal slippage    : entry fill worse than max_entry_slippage_bps vs decision price
                               -> log STRATEGY_DEVIATION alert; position still managed by exits
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiskState:
    locked_day: bool = False
    locked_hard: bool = False
    day_pnl_frac: float = 0.0
    last20: list = field(default_factory=list)
    data_failures: int = 0

    def new_session(self):
        self.locked_day = False
        self.day_pnl_frac = 0.0

    def record_trade(self, ret_frac: float, cfg):
        self.day_pnl_frac += ret_frac
        self.last20.append(ret_frac)
        if len(self.last20) > 20:
            self.last20.pop(0)
        if self.day_pnl_frac < -cfg["risk_limits"]["max_daily_loss_frac"]:
            self.locked_day = True
        if len(self.last20) == 20 and sum(self.last20) < -cfg["risk_limits"]["max_20trade_loss_frac"]:
            self.locked_hard = True

    def record_data_failure(self, cfg):
        self.data_failures += 1
        if self.data_failures >= cfg["risk_limits"]["max_consecutive_data_failures"]:
            self.locked_day = True

    def record_data_ok(self):
        self.data_failures = 0

    def can_trade(self) -> bool:
        return not (self.locked_day or self.locked_hard)
