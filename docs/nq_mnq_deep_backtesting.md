# NQ and MNQ Deep-Backtest Runbook

## Current result boundary

The deep research engine is implemented and tested, but this checkout still has **no committed licensed multi-year NQ or MNQ minute dataset**. Consequently, no synthetic result is promoted as market evidence and the final holdout remains unopened.

A public [CC0 NQ dataset covering approximately December 2022–December 2025](https://www.kaggle.com/datasets/tgtanalytics/nq-futures-1min-bar-2022-2025) is wired into the downloader as a possible first-pass research source. Its publisher describes one-minute Eastern-time NQ data, but its continuous-contract roll/back-adjustment methodology must be independently verified. It does not provide independent MNQ execution evidence.

For defensible testing, prefer individual NQ and MNQ contract data with bid/ask or tick information and a point-in-time rollover manifest. NQ and MNQ share Nasdaq-100 exposure; MNQ is an execution/risk-granularity variant, not a separate alpha confirmation.

## Instrument assumptions

| | NQ | MNQ |
|---|---:|---:|
| Tick size | 0.25 | 0.25 |
| Point value | $20 | $2 |
| Tick value | $5 | $0.50 |
| Baseline per-side commission | $2.50 | $0.85 |
| Baseline per-side exchange fee | $0.35 | $0.35 |
| Base spread/slippage | 1 tick / 1 tick | 1 tick / 1 tick |
| Risk budget | 0.25% closed equity | 0.25% closed equity |

Fees are configurable estimates, not a statement of a particular broker's current schedule. Replace them with the operator's all-in rate before evaluating results.

## Acquire and normalize

### Public NQ research starter

```bash
sphinx download-research-data \
  --dataset kaggle-nq-2022-2025 \
  --destination artifacts/external-data

sphinx normalize-data \
  --source artifacts/external-data/Dataset_NQ_1min_2022_2025.csv \
  --output artifacts/data/nq_2m.csv \
  --symbol NQ \
  --source-timezone America/New_York \
  --source-interval-seconds 60 \
  --provenance-note "CC0 Kaggle starter; rollover unverified"
```

If Kaggle downloads are blocked in the runtime, download from the documented dataset page and run only the normalization command. The normalizer:

- parses aware or declared-timezone timestamps;
- handles a repeated DST hour causally where possible;
- rejects duplicate/out-of-order rows;
- aggregates only complete two-minute buckets;
- drops rather than fills incomplete buckets;
- writes source and normalized SHA-256 hashes plus a manifest.

Normalize MNQ the same way from a properly licensed export:

```bash
sphinx normalize-data \
  --source /private/vendor/MNQ_1m.csv \
  --output artifacts/data/mnq_2m.csv \
  --symbol MNQ \
  --source-timezone America/Chicago \
  --source-interval-seconds 60 \
  --provenance-note "Vendor, contract list, roll rule, and adjustment here"
```

## Deep suite

```bash
sphinx deep-backtest \
  --nq-data artifacts/data/nq_2m.csv \
  --mnq-data artifacts/data/mnq_2m.csv \
  --bootstrap-simulations 5000 \
  --output artifacts/deep_research.json
```

For each supplied instrument this runs:

1. strict data-quality inspection and deterministic hashing;
2. chronological 60% development / 20% validation / 20% locked holdout;
3. untuned baseline on development and validation;
4. monthly, local-session-hour, side, and regime breakdowns;
5. optimistic/base/pessimistic execution on validation;
6. 0.10%, 0.25%, and 0.50% risk scenarios on validation;
7. validation expectancy bootstrap;
8. expanding walk-forward baseline windows;
9. predeclared one-factor development sensitivities:
   - consolidation lookback 8/16;
   - displacement 0.6/1.0 ATR;
   - stop cap 32/48 ticks;
   - delayed pivot windows 2/4;
10. neighboring-case stability summary;
11. NQ/MNQ side-by-side summary with a non-independence warning.

The suite never selects a winner automatically and never opens the holdout.

## Minimum interpretation gates

Do not freeze the strategy unless:

- each relevant validation sample has enough trades for meaningful inference;
- expectancy is positive after instrument-specific base costs;
- pessimistic execution does not reverse the entire conclusion;
- results are not concentrated in one month, hour, side, or regime;
- one-factor neighbors do not reveal an isolated optimum;
- walk-forward windows show repeatability;
- NQ/MNQ differences are explainable by point value, sizing, fees, and feed—not silent logic drift;
- rollover/session/DST gaps are resolved;
- paper signal parity is observed for a meaningful period.

A positive output is still not a guarantee or authorization for live funds.
