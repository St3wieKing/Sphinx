# NQ and MNQ Deep-Backtest Runbook

## Current result boundary

The deep research engine is implemented and tested. On 2026-08-14 the operator supplied the public CC0 NQ dataset (see below) and the frozen baseline was evaluated end-to-end on real data — see `research_results.md` for the numbers. Result: **no evidence of positive after-cost expectancy** (dev PF 0.97, validation PF 0.40, bootstrap P(positive) ≈ 4.3%). The holdout remains unopened and no parameter was tuned in response.

## Real-data run record (2026-08-14)

```text
source   : user-supplied ZIP via GitHub (publisher: Kaggle/TGT Analytics, CC0)
archive  : archive.zip  sha256 8d3f157a422636e5b8dda51cc3a3d9209c50cb53f9b279d3e14b627ce59370dc
csv      : Dataset_NQ_1min_2022_2025.csv  72,522,264 bytes  1,048,575 rows
           sha256 1577e60a7feab411e49da7a56c7052a64738cd1757cfd60aa11fd783ff43b60b
range    : 2022-12-26 18:01 ET -> 2025-12-11 20:52 ET (1-minute, America/New_York)
normalize: sphinx normalize-data -> artifacts/data/nq_2m.csv  523,455 bars
           sha256 1948b37e85fd7560c0772476c75dc765c1d1c86d22242c90efe8392409895284
quality  : 0 duplicates, 0 out-of-order, 0 interval mismatches
rollover : quarterly roll-date reopen gaps typically <= 25 points; series appears
           back-adjusted; largest reopen gaps are news-driven (see research_results.md)
suite    : sphinx deep-backtest --nq-data artifacts/data/nq_2m.csv
           --bootstrap-simulations 5000 -> artifacts/deep_research.json
MNQ      : artifacts/data/mnq_2m_modeled_from_nq.csv (NQ price path, MNQ economics;
           NOT independent MNQ evidence — see manifest for the exact warning)
```

The metrics-level `by_entry_hour` breakdown was initially bucketed in UTC; it was
fixed to the config session timezone (`America/New_York`) with a regression test
(`test_metrics_by_entry_hour_respects_timezone`), and the deep report was regenerated.

A public [CC0 NQ dataset covering approximately December 2022–December 2025](https://www.kaggle.com/datasets/tgtanalytics/nq-futures-1min-bar-2022-2025) is wired into the downloader as a possible first-pass research source. Its publisher describes one-minute Eastern-time NQ data; its continuous-contract roll/back-adjustment methodology must be independently verified. It does not provide independent MNQ execution evidence.

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
