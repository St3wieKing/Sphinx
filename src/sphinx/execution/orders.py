"""Order management (EXEC-*).

EXEC-01 one order per signal; duplicate submission for the same
        (strategy, date, signal) key is rejected.
EXEC-02 entry orders are marketable limits priced at decision price
        +/- max_entry_slippage_bps; unfilled after entry_timeout_seconds
        -> cancel, session locked (missed entries are never chased).
EXEC-03 every order carries strategy_id, signal_id, rule_id, timestamps,
        intended price and (once known) fill price.
"""
from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from typing import Optional

_seq = itertools.count(1)


@dataclass
class Order:
    strategy_id: str
    signal_id: str
    rule_id: str
    side: str                  # 'BUY' | 'SELL'
    qty: int
    order_type: str            # 'LIMIT' | 'MOC' | 'STOP'
    limit_px: Optional[float] = None
    stop_px: Optional[float] = None
    intended_px: Optional[float] = None
    status: str = "NEW"        # NEW/SUBMITTED/FILLED/CANCELLED/REJECTED
    order_id: int = field(default_factory=lambda: next(_seq))
    created_ts: float = field(default_factory=time.time)
    fill_px: Optional[float] = None
    fill_qty: int = 0
    fill_ts: Optional[float] = None


class OrderManager:
    def __init__(self, logger=None):
        self.orders = {}
        self._signal_keys = set()
        self.logger = logger

    def submit(self, order: Order) -> Order:
        key = (order.strategy_id, order.signal_id, order.rule_id, order.order_type)
        if key in self._signal_keys:
            order.status = "REJECTED"
            if self.logger:
                self.logger.error(f"EXEC-01 duplicate order rejected: {key}")
            return order
        self._signal_keys.add(key)
        order.status = "SUBMITTED"
        self.orders[order.order_id] = order
        if self.logger:
            self.logger.info(f"ORDER SUBMITTED {order}")
        return order

    def on_fill(self, order_id: int, px: float, qty: int):
        o = self.orders[order_id]
        o.fill_px, o.fill_qty, o.fill_ts = px, qty, time.time()
        o.status = "FILLED"
        if self.logger:
            self.logger.info(f"ORDER FILLED {o}")
        return o

    def cancel(self, order_id: int, reason: str = ""):
        o = self.orders[order_id]
        if o.status == "SUBMITTED":
            o.status = "CANCELLED"
            if self.logger:
                self.logger.info(f"ORDER CANCELLED {o.order_id} {reason}")
        return o

    def open_orders(self):
        return [o for o in self.orders.values() if o.status == "SUBMITTED"]
