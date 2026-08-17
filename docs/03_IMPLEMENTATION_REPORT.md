# SPHINX-LHM v1.0.0 — Implementation & Fidelity Report

Deployment status: **PAPER TRADING ONLY. NOT APPROVED FOR LIVE CAPITAL** (locked-test fail; see `docs/01_RESEARCH_REPORT.md`).

## 1. Strategy interpretation document (Phase 1 rule extraction)

| Rule ID | Source (spec §) | Logic | Inputs | Output | Code | Test |
|---|---|---|---|---|---|---|
| DATA-01..05 | B | load/dedupe/sort 1-min RTH bars; staleness gate | raw csv / feed | minute_rth, sessions | `data/loader.py`, `data/validation.py` | `test_engine_validation.py` |
| CALC-01 | D | prev session last RTH close | sessions | prev_close | `data/loader.py::build_sessions` | fidelity |
| CALC-02 | D | ATR14, strictly prior | daily H/L/C | atr14 | same | fidelity |
| CALC-03 | D | RV20 annualized, strictly prior | daily closes | rv20 | same | fidelity |
| CALC-04 | D | r_early (prev_close → last bar < 10:00) | minute bars | float | `strategy/calculations.py` | `test_signals.py` |
| CALC-05 | D | r_od (prev_close → last bar < 15:30) | minute bars | float | same | `test_signals.py` (incl. no-lookahead) |
| FILT-01 | C | session validity gates | sessions | bool | `data/validation.py::valid_session_mask` | `test_fidelity.py` |
| FILT-02 | C | skip early-close sessions | sessions | bool | `strategy/signals.py` | `test_signals.py` |
| FILT-03 | C | rv20 ≥ 0.15 | sessions | bool | `strategy/signals.py` | `test_signals.py` |
| SETUP-01 | D | sign agreement ≠ 0 | CALC-04/05 | bool | `strategy/signals.py` | `test_signals.py` |
| SETUP-02 | D | magnitude ≥ 0.10 × ATR% | CALC-02/04/05 | bool | `strategy/signals.py` | `test_signals.py` |
| ENTRY-01 | E | marketable limit at 15:30, dir = sign | Signal | Order | `scripts/paper_trade.py`, `backtest/run_strategy.py` | fidelity, replay |
| ENTRY-02 | E | 60 s timeout, never chase | clock | cancel | `scripts/paper_trade.py` | replay |
| ENTRY-03 | E | duplicate-order guard | OrderManager | reject | `execution/orders.py` | `test_costs_risk.py` (via OM) |
| STOP-01 | F | disaster stop 2.0×ATR, OCO | Signal | Order | same as ENTRY-01 | `test_engine_validation.py` (fill semantics) |
| EXIT-01 | G | MOC full exit | position | Order | same | `test_engine_validation.py` |
| SIZE-01 | H | vol-scaled, 0.5% budget, 2× cap | equity, atr | shares | `risk/sizing.py` | `test_costs_risk.py` |
| RISK-01..05 | I/J | lockouts (daily, rolling-20, data, slippage) | trade log | can_trade | `risk/limits.py` | `test_costs_risk.py` |
| STATE-* | — | deterministic state machine, no hidden transitions | events | state | `strategy/state_machine.py` | `test_signals.py` |
| MON-01..03 | J | JSONL audit log + 6 alert types | all events | log/alerts | `monitoring/logger.py` | replay |

## 2. System architecture

```
Market Data (1-min bars, ET)
    ↓  data/loader.py            – dedupe, sort, session build
Data Validation                  – data/validation.py (FILT-01, staleness, integrity)
    ↓
Strategy Calculations            – strategy/calculations.py (CALC-01..05, strictly prior refs)
    ↓
Market / Setup Filters           – strategy/signals.py (FILT-02..03, SETUP-01..02)
    ↓
Signal Generation                – Signal{LONG|SHORT|NO_TRADE} + full explanation log
    ↓
Risk Validation                  – risk/limits.py (RISK-01..04 may only BLOCK)
    ↓
Order Management                 – execution/orders.py (dup guard, timeout, audit fields)
    ↓
Execution                        – execution/paper_broker.py (same fills/costs as backtest)
    ↓
Position Management / Exit       – OCO disaster stop + MOC (STOP-01, EXIT-01)
    ↓
Logging + Monitoring             – monitoring/logger.py (JSONL, alerts)
```
The backtester (`backtest/engine.py`, `backtest/run_strategy.py`) consumes the identical
signal, fill and cost code — research/production parity is enforced by `tests/test_fidelity.py`,
which asserts trade-for-trade equality between the frozen production path and the winning
research candidate.

## 3. Completeness audit (Phase 2)

All 15 audit questions answered by the spec; items resolved during implementation:
- Bar labeling verified bar-start (median 390 bars in 09:30–15:59 window; closes match official prints).
- Early-close sessions detected by last-bar-before-14:00 when no calendar present (documented in spec DATA-03).
- Duplicate vendor timestamps: keep-last (documented; 15,318 rows ≈ 0.3%).

**UNRESOLVED SPECIFICATION ITEMS (safe no-trade defaults active):**
1. Live MOC submission deadline (exchange cutoff 15:50 ET for NYSE MOC) — the backtest proxy uses the 15:59 bar close; the paper trader submits MOC at entry fill (before cutoff). For live use, broker-specific auction rules must be encoded. Default if uncertain: marketable exit 15:59:00.
2. Corporate-action handling for instruments other than SPY is unspecified (SPY had no splits in-sample). Default: NO_TRADE on any session flagged with a corporate action.

## 4. Extra-logic audit (Phase 15)

Every piece of logic that can affect opening, sizing or closing a position:

| Logic | In strategy spec? | Execution infra? | Safety control? | Keep? |
|---|---|---|---|---|
| FILT/SETUP/ENTRY/STOP/EXIT/SIZE rules | Yes | — | — | Yes |
| Duplicate-order guard (ENTRY-03) | Yes (E) | Yes | — | Yes |
| Entry timeout + never-chase (ENTRY-02) | Yes (E) | Yes | — | Yes |
| RiskState lockouts (RISK-01..04) | Yes (I) | — | Yes | Yes |
| Abnormal-slippage alert (RISK-05) | Yes (J) | — | Yes (alert-only, cannot open/close) | Yes |
| Conservative same-bar stop-before-target fill assumption | — | Yes (backtest realism) | — | Yes |
| Anything else (indicators, ML, extra filters) | — | — | — | **None present** |

No RSI, moving-average, MACD, VWAP, order-block, liquidity, ML, sentiment or news logic exists anywhere in the codebase (VWAP code exists only in `research/candidates.py` as a rejected tournament candidate and is not imported by production modules).

## 5. Final acceptance criteria

- [x] Every strategy rule has an implementation mapping (§1)
- [x] No undefined trading rules silently invented (2 unresolved items → documented safe defaults)
- [x] No unrelated strategy mixed in (§4)
- [x] No look-ahead bias (strictly-prior refs; `test_no_lookahead_bars_after_1530_cannot_change_signal`)
- [x] Costs modeled (base + stress; commissions, spread, slippage, stop-gap)
- [x] Execution assumptions documented (spec §E–G, M)
- [x] Every trade has a complete audit trail (trade_id, rule IDs, raw+net prices, signal explanation)
- [x] Sizing follows predetermined risk constraints (SIZE-01)
- [x] All no-trade conditions enforced (`run_frozen` census: LOW_VOL_REGIME 811, NO_AGREEMENT 147, MOVE_TOO_SMALL 83, HALF_DAY 2, DATA_VALIDATION_FAILURE 2 on TEST)
- [x] Risk controls tested (`test_costs_risk.py`)
- [x] Data failures ⇒ safe behavior (NO_TRADE; lockout after 3)
- [x] Order failures handled (timeout/cancel/reject paths)
- [x] Backtest reproducible (`test_backtest_reproducible`)
- [x] Validation data separated from final testing (pre-registered splits; test run once)
- [x] Paper trading implemented and REQUIRED before any real-money use — **and real-money use is currently NOT approved**

## 6. Test suite summary

35 tests: fills (9), engine/validation (7), costs/risk/sizing (8), signals/state machine (9, incl. no-lookahead), fidelity/reproducibility/no-trade-enforcement (3, data-gated). Run: `python -m pytest tests -q`.
