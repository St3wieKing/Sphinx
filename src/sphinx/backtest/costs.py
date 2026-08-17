"""Transaction cost model.

All costs are charged PER SHARE PER SIDE in dollars:
  total_per_side = commission + half_spread + slippage

Base assumptions (SPY, marketable orders, small size):
  commission  = $0.0035 (IBKR tiered incl. exchange/regulatory fees)
  half_spread = $0.005  (SPY is 1c wide essentially all day)
  slippage    = $0.005  (adverse drift/queue for marketable flow)
=> $0.0135 per share per side, $0.027 round trip.

Stops are assumed to fill WORSE than the stop price by `stop_gap_extra`
on top of normal costs (gap-through risk).  Stress multipliers scale the
half_spread+slippage component (commissions are contractual).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostModel:
    commission: float = 0.0035
    half_spread: float = 0.005
    slippage: float = 0.005
    stop_gap_extra: float = 0.01   # extra adverse fill on stop exits
    stress: float = 1.0            # multiplies (half_spread + slippage [+ stop gap])

    @property
    def per_side(self) -> float:
        return self.commission + (self.half_spread + self.slippage) * self.stress

    def entry_price(self, px: float, direction: int) -> float:
        """Effective fill for a marketable entry."""
        return px + direction * (self.half_spread + self.slippage) * self.stress

    def exit_price(self, px: float, direction: int, is_stop: bool = False) -> float:
        adverse = (self.half_spread + self.slippage) * self.stress
        if is_stop:
            adverse += self.stop_gap_extra * self.stress
        return px - direction * adverse

    def commissions_round_trip(self) -> float:
        return 2.0 * self.commission
