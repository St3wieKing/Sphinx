"""Paper broker — fills orders against a bar stream using the exact same
fill rules and cost model as the backtester (research/production parity).
This is the ONLY deployment mode currently authorized (see docs)."""
from __future__ import annotations

from typing import Optional

from ..backtest.costs import CostModel
from .fills import protective_stop_fill, target_fill
from .orders import Order, OrderManager


class PaperBroker:
    def __init__(self, costs: CostModel = None, logger=None):
        self.costs = costs or CostModel()
        self.om = OrderManager(logger)
        self.position = 0
        self.avg_px = 0.0
        self.logger = logger

    def submit(self, order: Order) -> Order:
        return self.om.submit(order)

    def on_bar(self, o: float, h: float, l: float, c: float, is_last_bar: bool):
        """Attempt fills for all open orders on this 1-min bar."""
        fills = []
        for od in list(self.om.open_orders()):
            d = 1 if od.side == "BUY" else -1
            px: Optional[float] = None
            reason = ""
            if od.order_type == "LIMIT":
                # marketable limit: fills unless bar never trades at/therough limit
                if d == 1 and l <= od.limit_px:
                    px = min(o, od.limit_px)
                elif d == -1 and h >= od.limit_px:
                    px = max(o, od.limit_px)
                if px is not None:
                    px = self.costs.entry_price(px, d)
                    reason = "entry"
            elif od.order_type == "STOP":
                raw = protective_stop_fill(-d, od.stop_px, o, h, l)
                if raw is not None:
                    px = self.costs.exit_price(raw, -d, is_stop=True)
                    reason = "stop"
            elif od.order_type == "MOC":
                if is_last_bar:
                    px = self.costs.exit_price(c, -d if self.position * d < 0 else d, is_stop=False)
                    reason = "moc"
            if px is not None:
                self.om.on_fill(od.order_id, px, od.qty)
                self.position += d * od.qty
                fills.append((od, px, reason))
        return fills
