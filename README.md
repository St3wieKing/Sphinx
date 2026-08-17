# Sphinx

**Systematic day-trading research program + deterministic execution engine.**

> ⚠️ **DEPLOYMENT STATUS: PAPER TRADING ONLY — NOT APPROVED FOR LIVE CAPITAL.**
> The tournament-winning strategy (SPHINX-LHM v1.0) **failed its single locked
> out-of-sample test** (2021→2026: −0.18 bps/trade, t = −0.09). Under the
> pre-registered protocol that is a NO-GO, and it is reported as such.
> Nothing here claims or guarantees future profitability.

## What this repository contains

An end-to-end, evidence-driven investigation of intraday strategy families on
26 years of SPY 1-minute data (2000–2026, 4.6M bars), followed by a complete,
fidelity-tested implementation of the single most robust candidate:

| Deliverable | Location |
|---|---|
| Research report (20 critical questions, tournament, walk-forward, locked-test verdict, failure analysis) | [`docs/01_RESEARCH_REPORT.md`](docs/01_RESEARCH_REPORT.md) |
| Frozen strategy specification (A–J, parameters, pseudocode) | [`docs/02_STRATEGY_SPEC.md`](docs/02_STRATEGY_SPEC.md) |
| Implementation & fidelity report (rule mapping, extra-logic audit, acceptance checklist) | [`docs/03_IMPLEMENTATION_REPORT.md`](docs/03_IMPLEMENTATION_REPORT.md) |
| Reproducible backtest report (all splits, costs, regimes, Monte Carlo) | [`docs/04_BACKTEST_REPORT.md`](docs/04_BACKTEST_REPORT.md) |
| Production engine (data → validation → signal → risk → execution → monitoring) | [`src/sphinx/`](src/sphinx) |
| Frozen machine-readable parameters | [`config/strategy.json`](config/strategy.json) |
| Research tournament code + all raw outputs | [`research/`](research) |
| Test suite (35 tests incl. no-lookahead, fidelity, reproducibility) | [`tests/`](tests) |

## Headline findings (all net of realistic costs)

- **Opening-range breakouts** (immediate and stop-entry, 5/15/30-min, with/without R-targets): **negative expectancy across the entire parameter grid** on SPY.
- **VWAP-band mean reversion**: negative across its grid.
- **Overnight-gap fading**: positive but statistically insufficient (t ≤ 1.2).
- **Late-day intraday momentum** (Gao-Han-Li-Zhou 2018; Baltussen et al. 2021 mechanism): strong in 2003-2014 (+6.9 bps, t 2.9), weak in 2015-2020 (+1.7 bps), walk-forward +3.3 bps (t 2.6) — **then zero/negative in the locked 2021-2026 test**, with evidence the close-auction mechanism inverted in 2025 (0DTE-era dealer-gamma dynamics).

The honest conclusion of a skeptical process: **no tested price-pattern day-trading
family retains a deployable post-cost edge on SPY in the most recent five years.**
The infrastructure is strategy-agnostic and ready for the documented next research
paths (options-positioning-conditioned end-of-day reversal; cross-sectional
relative-volume ORB; futures replication).

## Quick start

```bash
pip install -r requirements.txt
python scripts/download_data.py          # 53 MB SPY 1-minute dataset (2000-2026)
python -m pytest tests -q                # 35 tests
python research/tournament.py train      # reproduce the candidate tournament
python scripts/run_locked_test.py        # reproduce every number in docs/04
python scripts/paper_trade.py 2024-08-05 # replay a session through the paper trader
```

## Architecture

```
Market Data → Data Validation → Strategy Calculations → Market/Setup Filters
→ Signal Generation (explained) → Risk Validation → Order Management
→ Execution (paper) → Position/Exit Management → Logging + Monitoring
```

One shared engine serves research and production; `tests/test_fidelity.py`
asserts trade-for-trade equality between the two paths.
