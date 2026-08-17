"""Structured JSONL logging + alert hooks (MON-*).

MON-01 every signal, order, fill, state transition and risk event is
       appended to logs/sphinx_YYYYMMDD.jsonl
MON-02 alerts: DATA_FAILURE, EXECUTION_FAILURE, POSITION_MISMATCH,
       RISK_LIMIT_BREACH, ABNORMAL_SLIPPAGE, STRATEGY_DEVIATION
MON-03 if position or data state cannot be safely determined the engine
       must stop opening new trades (handled by RiskState lockout).
"""
from __future__ import annotations

import json
import os
import time
from enum import Enum


class Alert(Enum):
    DATA_FAILURE = "DATA_FAILURE"
    EXECUTION_FAILURE = "EXECUTION_FAILURE"
    POSITION_MISMATCH = "POSITION_MISMATCH"
    RISK_LIMIT_BREACH = "RISK_LIMIT_BREACH"
    ABNORMAL_SLIPPAGE = "ABNORMAL_SLIPPAGE"
    STRATEGY_DEVIATION = "STRATEGY_DEVIATION"


class JsonLogger:
    def __init__(self, log_dir: str = "logs", stdout: bool = False):
        os.makedirs(log_dir, exist_ok=True)
        self.path = os.path.join(log_dir, f"sphinx_{time.strftime('%Y%m%d')}.jsonl")
        self.stdout = stdout
        self.alert_handlers = []

    def _write(self, level: str, msg: str, **kw):
        rec = {"ts": time.time(), "level": level, "msg": str(msg), **kw}
        with open(self.path, "a") as f:
            f.write(json.dumps(rec, default=str) + "\n")
        if self.stdout:
            print(f"[{level}] {msg}")

    def info(self, msg, **kw):
        self._write("INFO", msg, **kw)

    def error(self, msg, **kw):
        self._write("ERROR", msg, **kw)

    def alert(self, alert: Alert, msg: str = "", **kw):
        self._write("ALERT", f"{alert.value}: {msg}", alert=alert.value, **kw)
        for h in self.alert_handlers:
            h(alert, msg)
