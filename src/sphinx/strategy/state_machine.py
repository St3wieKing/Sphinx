"""Deterministic strategy state machine (STATE-*).

States:
  IDLE -> WAITING_FOR_MARKET -> WAITING_FOR_SETUP -> SETUP_DETECTED
       -> ENTRY_PENDING -> POSITION_OPEN -> EXIT_PENDING -> IDLE
  SESSION_LOCKED / RISK_LOCKED / ERROR are absorbing for the session.

Transitions (no hidden paths):
  WAITING_FOR_SETUP -> SETUP_DETECTED  : Signal.result in {LONG, SHORT}
                                         AND risk.can_trade()
  WAITING_FOR_SETUP -> SESSION_LOCKED  : Signal.result == NO_TRADE
  SETUP_DETECTED   -> ENTRY_PENDING    : order submitted at signal_time
  ENTRY_PENDING    -> POSITION_OPEN    : fill received within timeout
  ENTRY_PENDING    -> SESSION_LOCKED   : timeout/reject (missed entry is
                                         NOT chased after 15:31:00)
  POSITION_OPEN    -> EXIT_PENDING     : MOC submitted / disaster stop hit
  EXIT_PENDING     -> IDLE             : exit fill confirmed
  any              -> ERROR            : unrecoverable data/broker failure
"""
from __future__ import annotations

from enum import Enum, auto


class State(Enum):
    IDLE = auto()
    WAITING_FOR_MARKET = auto()
    WAITING_FOR_SETUP = auto()
    SETUP_DETECTED = auto()
    ENTRY_PENDING = auto()
    POSITION_OPEN = auto()
    EXIT_PENDING = auto()
    SESSION_LOCKED = auto()
    RISK_LOCKED = auto()
    ERROR = auto()


ALLOWED = {
    State.IDLE: {State.WAITING_FOR_MARKET, State.ERROR},
    State.WAITING_FOR_MARKET: {State.WAITING_FOR_SETUP, State.SESSION_LOCKED, State.ERROR},
    State.WAITING_FOR_SETUP: {State.SETUP_DETECTED, State.SESSION_LOCKED, State.RISK_LOCKED, State.ERROR},
    State.SETUP_DETECTED: {State.ENTRY_PENDING, State.SESSION_LOCKED, State.RISK_LOCKED, State.ERROR},
    State.ENTRY_PENDING: {State.POSITION_OPEN, State.SESSION_LOCKED, State.ERROR},
    State.POSITION_OPEN: {State.EXIT_PENDING, State.ERROR},
    State.EXIT_PENDING: {State.IDLE, State.ERROR},
    State.SESSION_LOCKED: {State.IDLE},
    State.RISK_LOCKED: {State.IDLE},
    State.ERROR: {State.IDLE},
}


class StateMachine:
    def __init__(self, logger=None):
        self.state = State.IDLE
        self.history = []
        self.logger = logger

    def transition(self, new: State, trigger: str):
        if new not in ALLOWED[self.state]:
            raise RuntimeError(f"illegal transition {self.state} -> {new} ({trigger})")
        self.history.append((self.state, new, trigger))
        if self.logger:
            self.logger.info(f"STATE {self.state.name} -> {new.name} | {trigger}")
        self.state = new
