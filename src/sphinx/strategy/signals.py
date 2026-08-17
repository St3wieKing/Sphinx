"""Frozen strategy signal engine — SPHINX-LHM v1.0.0.

Every trading decision traces to a rule ID (see docs/02_STRATEGY_SPEC.md):

FILT-01  session data valid (coverage, refs present, |gap| < 20%)
FILT-02  not a half-day session
FILT-03  rv20 >= rv20_min                      (regime gate)
SETUP-01 sign(r_early) == sign(r_od) != 0      (direction agreement)
SETUP-02 min(|r_early|,|r_od|) >= min_move_frac_atr * atr14/prev_close
ENTRY-01 marketable entry at signal_time (15:30) in the agreed direction
STOP-01  disaster stop at entry_ref -/+ 2.0*atr14 (safety only)
EXIT-01  market-on-close exit (16:00 auction)
The engine emits LONG / SHORT / NO_TRADE with a complete explanation log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .calculations import r_early, r_od, last_price_before


@dataclass
class Signal:
    date: object
    result: str                    # 'LONG' | 'SHORT' | 'NO_TRADE'
    direction: int = 0
    reason: str = ""
    checks: dict = field(default_factory=dict)
    r_early: Optional[float] = None
    r_od: Optional[float] = None
    entry_ref_px: Optional[float] = None
    stop_px: Optional[float] = None

    def explain(self) -> str:
        lines = [f"Signal {self.date} -> {self.result} ({self.reason})"]
        for k, v in self.checks.items():
            lines.append(f"  {k}: {v}")
        return "\n".join(lines)


def evaluate_day(date, arr, sess_row, cfg, session_valid: bool) -> Signal:
    """Pure function: one Signal per session. No hidden state."""
    sc = cfg["signal"]
    checks = {}

    checks["FILT-01 session_valid"] = session_valid
    if not session_valid:
        return Signal(date, "NO_TRADE", reason="DATA_VALIDATION_FAILURE", checks=checks)

    checks["FILT-02 full_session"] = not bool(sess_row["is_half_day"])
    if sess_row["is_half_day"]:
        return Signal(date, "NO_TRADE", reason="HALF_DAY", checks=checks)

    rv = float(sess_row["rv20"])
    checks[f"FILT-03 rv20>={sc['rv20_min']}"] = f"rv20={rv:.4f} -> {rv >= sc['rv20_min']}"
    if not rv >= sc["rv20_min"]:
        return Signal(date, "NO_TRADE", reason="LOW_VOL_REGIME", checks=checks)

    pc = float(sess_row["prev_close"])
    re_ = r_early(arr, pc, sc["early_mark_time"])
    ro_ = r_od(arr, pc, sc["signal_time"])
    checks["CALC-04 r_early"] = re_
    checks["CALC-05 r_od"] = ro_
    if re_ is None or ro_ is None:
        return Signal(date, "NO_TRADE", reason="DATA_VALIDATION_FAILURE", checks=checks)

    s1 = (re_ > 0) - (re_ < 0)
    s2 = (ro_ > 0) - (ro_ < 0)
    agree = s1 != 0 and s1 == s2
    checks["SETUP-01 sign_agreement"] = f"sign(r_early)={s1} sign(r_od)={s2} -> {agree}"
    if not agree:
        return Signal(date, "NO_TRADE", reason="NO_AGREEMENT", checks=checks,
                      r_early=re_, r_od=ro_)

    thr = sc["min_move_frac_atr"] * float(sess_row["atr14"]) / pc
    mag = min(abs(re_), abs(ro_))
    checks["SETUP-02 magnitude"] = f"min(|r1|,|rod|)={mag:.5f} thr={thr:.5f} -> {mag >= thr}"
    if mag < thr:
        return Signal(date, "NO_TRADE", reason="MOVE_TOO_SMALL", checks=checks,
                      r_early=re_, r_od=ro_)

    ref = last_price_before(arr, sc["signal_time"])
    stop = ref - s1 * cfg["exit"]["disaster_stop_atr_mult"] * float(sess_row["atr14"])
    checks["ENTRY-01 direction"] = "LONG" if s1 > 0 else "SHORT"
    checks["STOP-01 disaster_stop"] = stop
    return Signal(date, "LONG" if s1 > 0 else "SHORT", direction=int(s1),
                  reason="SETUP_COMPLETE", checks=checks, r_early=re_, r_od=ro_,
                  entry_ref_px=ref, stop_px=stop)
