# Sphinx

An evidence-labelled, mechanically testable **Matthew Scriv–inspired** NQ day-trading research system.

> **Research and paper simulation only.** This repository does not claim to reproduce Matthew Scriv's full discretionary process, does not establish profitability, and contains no live-money broker adapter.

## What was actually extracted

The primary public video demonstrates a short-term consolidation break, an evolving origin-to-extreme range, entry on a 50% retracement, a 40-tick or pivotal stop, a first target at the prior extreme, and an optional runner toward equal highs/obvious liquidity. SMT, OTE/rejection wicks, and FVG/IFVG are shown as discretion or confluence rather than a complete mandatory formula. Bias and several visual choices remain under-specified.

See:

1. [Source research and evidence labels](docs/research_report.md)
2. [Mechanical strategy specification](docs/strategy_specification.md)
3. [Complete pseudocode](docs/pseudocode.md)
4. [Software architecture](docs/architecture.md)
5. [Validation protocol](docs/validation_protocol.md)
6. [Current research results / no-claim boundary](docs/research_results.md)
7. [NQ/MNQ deep-backtest runbook](docs/nq_mnq_deep_backtesting.md)
8. [Signal Desk website](docs/dashboard.md)
9. [TradingView Pine v6 indicator](docs/tradingview.md)
10. [Machine-readable strategy spec](spec/strategy_spec.json)

## Features

- explicit state machine rather than unrelated indicator voting;
- 2m execution plus causal 5m/15m/1h/4h aggregation;
- delayed fixed/fractal pivots and online ATR/percentage alternatives;
- liquidity metadata, equal levels, sweep/consume lifecycle, and ranking;
- causal FVG/IFVG tracking and optional synchronized NQ/ES SMT proxy;
- conservative OHLC execution with spread, slippage, fees, gap stops, and adverse same-bar rules;
- equity-risk sizing, daily/session limits, cooldowns, maximum drawdown, and kill switches;
- locked 60/20/20 split, walk-forward utilities, execution scenarios, Monte Carlo, and experiment ledger;
- bounded NQ/MNQ deep suite with walk-forward, one-factor sensitivity, bootstrap, risk and execution scenarios;
- polished paper Signal Desk website with contract switch, setup chart, checklist, levels, metrics, ledger, and research view;
- Pine Script® v6 TradingView overlay with state, swings, FVG context, long/short, stop, TP1/TP2, dashboard, and alerts;
- public-data downloader plus strict one-minute-to-two-minute normalization and provenance manifests;
- hash-chained audit JSONL and explanatory paper-trading daily reports;
- zero runtime dependencies beyond Python 3.11.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .

sphinx validate-config --config config/baseline.json
sphinx inspect-data --data /path/to/nq_2m.csv
sphinx backtest --data /path/to/nq_2m.csv --partition development \
  --output artifacts/development.json
sphinx paper --data /path/to/nq_2m.csv --output-directory artifacts

# NQ + MNQ bounded deep research; final holdout remains locked
sphinx deep-backtest --nq-data /path/to/nq_2m.csv --mnq-data /path/to/mnq_2m.csv \
  --output artifacts/deep_research.json

# Paper signal website
sphinx dashboard --host 0.0.0.0 --port 8000 \
  --nq-data /path/to/nq_2m.csv --mnq-data /path/to/mnq_2m.csv \
  --deep-report artifacts/deep_research.json

# Or start receive-only TradingView paper webhook intake with a local token
scripts/start_paper_signal_desk.sh
```

Without installation:

```bash
PYTHONPATH=src python -m sphinx_bot validate-config
```

## Engineering-only demo

```bash
sphinx generate-demo --days 15 --output artifacts/synthetic.csv
sphinx backtest --data artifacts/synthetic.csv --partition development \
  --output artifacts/synthetic_check.json
```

The generator deliberately inserts patterns to exercise software paths. Its P&L is **not market evidence**.

## Historical-data requirements

Provide licensed, timezone-aware completed NQ 2-minute bars. Document vendor, individual contracts, rollover and adjustment, exchange calendar, timestamp semantics, gaps, and a SHA-256 hash. Optional ES bars must be synchronized. No interpolation occurs. See [`data/README.md`](data/README.md).

## Holdout protection

The CLI defaults to development and has no “all” option. A holdout run fails unless:

1. `research.strategy_frozen` is explicitly set to `true`; and
2. `--allow-holdout` is explicitly passed.

Do not freeze or open holdout until all hypotheses, costs, code, and selection criteria are fixed.

## Testing

```bash
python -m unittest discover -s tests -v
# or, with the dev extra:
python -m pytest
```

## Safety behavior

New entries stop on stale active-session data, excessive spread, repeated rejection, daily loss, maximum drawdown, invalid account/risk state, execution errors, or position mismatch. Pending entries are cancelled; configured critical kills flatten the paper position; logs are preserved. Critical kills remain latched for review.

This is software for hypothesis testing—not financial advice, a return promise, or authorization for live deployment.
