# Deliverable 6 — Research Results and Claim Boundary

## Current evidence status

| Required result | Status | Why |
|---|---|---|
| Source extraction | Complete for the requested public video | See `research_report.md`. |
| Mechanical baseline | Implemented | See runtime config, machine spec, and tests. |
| Historical baseline result | **Run on real public NQ data — no edge found** | CC0 Kaggle NQ 1-minute data (2022-12-26 → 2025-12-11) normalized to 523,455 two-minute bars; results in the section below. |
| Development experiments | **Not run** | Baseline alone shows no development edge to compound; any future change must be predeclared in `research/experiments.jsonl`. |
| Validation result | **Negative** | 19 trades, expectancy −97.03/trade after costs; bootstrap P(positive) ≈ 4%. |
| Final holdout | **Locked and untouched** | Config remains `strategy_frozen=false`. |
| Execution stress | Tool implemented; run on real validation partition | Optimistic/base/pessimistic scenarios in the deep report. |
| Monte Carlo | Tool implemented; market run pending | 19 validation trades are too few for a stable equity simulation; bootstrap was used instead. |
| Final selected profitable configuration | **None** | There is no empirical basis to select or claim one. |
| Paper deployment | CSV-replay paper system implemented | This validates architecture, not expectancy. |

## Real-data baseline result (2026-08-14)

Dataset: public CC0 [NQ Futures 1-minute 2022–2025](https://www.kaggle.com/datasets/tgtanalytics/nq-futures-1min-bar-2022-2025) (publisher: TGT Analytics). The operator supplied the publisher ZIP via a GitHub repository; it was hash-pinned and normalized to strict two-minute buckets in `America/New_York` (no forward-fill, incomplete buckets dropped). Source rows 1,048,575 → 523,455 target bars. Rollover scan: gaps around all quarterly roll dates are small (typically ≤25 points), consistent with a back-adjusted continuous series; the largest session-reopen gaps are news-driven (2025-04-06 −926; 2025-02-02 −552; 2025-10-12 +520), not roll artifacts.

| Partition | Bars | Trades | Net after costs | Profit factor | Win rate | Expectancy | Max DD | Max consec. losses |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Development (60%) | 314,073 | 49 | **−$136.50** | 0.971 | 48.98% | −2.79/trade | 2.40% | 8 |
| Validation (20%) | 104,691 | 19 | **−$1,843.60** | 0.395 | 15.79% | −97.03/trade | 2.00% | 7 |
| Holdout (20%) | 104,691 | — | — | — | — | — | — | — |

Development details (all after costs): longs −593.10 on 22 trades, shorts +456.60 on 27 trades. Range regime +890.20 on 44 trades, expansion regime −1,026.70 on 5 trades (0/5 wins). Gross P&L before costs was +1,312.50 against total costs of 1,449.00 — costs consumed the entire pre-cost edge.

Validation bootstrap (5,000 resamples of the 19 observed trades): mean expectancy −97.26/trade, 95th percentile −5.38/trade, probability of positive expectancy ≈ 4.3%.

MNQ companion run (same price path, MNQ economics — point value $2.00, $0.85 commission + $0.35 exchange fee per side, 20-contract cap; **not independent MNQ evidence**): development expectancy −51.19/trade (PF 0.50, 49 trades); validation expectancy −89.71/trade (PF 0.34, 19 trades). Recorded as `EXP-MNQ-REAL-000`.

Entry-hour breakdown on the development partition (ET): 01:00 and 02:00 entries were net positive (+1,059 and +1,129 before partition aggregation) while 00:00 and 03:00 entries were net negative (−1,126 and −1,200). Small samples; this is descriptive observation, not a fitted rule. Any hour-based change would need to be predeclared as a new experiment and survive validation unchanged.

## Honest baseline conclusion

The software makes the source-inspired hypothesis testable. On the first real dataset, the frozen baseline **fails** to demonstrate positive expectancy: development is breakeven before costs and costs wipe it out; validation is clearly negative with only 4% bootstrap probability of a positive true mean. This is a scientific negative, not a tuning invitation: no parameter was changed in response to this result, the holdout was not opened, and the experiment is recorded as `EXP-NQ-REAL-000` with decision `REJECT_POSITIVE_EXPECTANCY_AT_BASELINE`.

The answer to “does this demonstrate robust performance after costs?” is currently **no evidence**, not yes.

Known weaknesses of this evaluation (not excuses): one third-party continuous series; no bid/ask or tick data; no MNQ-native series (MNQ was run as NQ prices with MNQ economics and is explicitly labeled non-independent); only 68 observed trades across both partitions; the source methodology's discretionary bias selection and “pivotal” stop remain under-specified, so the mechanical proxy may simply not capture the edge.

## Engineering validation (not trading research)

On 2026-08-14:

- all **31** standard-library unit/integration tests passed (30 → 31 after the timezone-hour-bucketing regression test);
- strict config and all JSON deliverables parsed;
- editable installation and console entry point were exercised in an isolated virtual environment;
- deterministic synthetic replay exercised signal, risk, fill, trade, metric, paper artifact, and hash-chain paths;
- the development-partition demo produced multiple executed paths, but its P&L is deliberately not promoted here because those patterns were inserted by the generator;
- audit-chain verification passed after replay, and its tamper test correctly failed after record alteration.

The subsequent NQ/MNQ extension also exercises external one-minute normalization, the locked deep-research suite, website payloads, packaged Pine-source parity, and public-data provenance controls. These checks establish internal behavior and causal safeguards. They do not validate market expectancy, queue fills, TradingView feed parity, or live reliability.

## Baseline hypothesis

> Completed overnight NQ consolidation displacement followed by a return to the causally known 50% impulse midpoint has positive out-of-sample expectancy after spread, slippage, commissions, fees, strict stops, and risk constraints.

Reasons this may fail:

- direction-of-break proxy may not reproduce Scriv's discretionary bias;
- midpoint triggers may be crowded/noisy;
- a 40-tick stop may be mismatched to volatility regimes;
- overnight fills and spread may be materially worse than bar simulation;
- “first logical liquidity” may not be stable;
- sample frequency may be too low for reliable inference;
- continuous-futures construction may distort old price levels or session boundaries.

## Predeclared experiment sequence

Only one conceptual change per experiment unless explicitly factorial.

| ID | Hypothesis | Change | Decision gate |
|---|---|---|---|
| EXP-000 | Core proxy has expectancy | Baseline exactly as configured | Descriptive starting point; no tuning. |
| EXP-001 | Close rejection reduces false touches | `entry_confirmation: touch → close_rejection` | Keep only if validation expectancy improves without unstable frequency collapse. |
| EXP-002 | ATR stop is more regime-stable | Compare fixed 40 with predeclared ATR stop extension | Reject if improvement is development-only or neighboring values are fragile. |
| EXP-003 | SMT is useful, not decorative | Require causal synchronized ES proxy | Require sufficient paired-data sample and validation improvement after costs. |
| EXP-004 | HTF FVG location improves selection | Require only completed context AOI | Reject if trade count becomes too small or effect concentrates in one period. |
| EXP-005 | Overnight subwindows differ | Predeclare hourly groups; no post-hoc cherry-pick | Any disabled hour needs repeated walk-forward support. |
| EXP-006 | Structure method is stable | Fixed vs fractal vs ATR vs percentage | Select stability across folds/neighboring settings, not max development return. |

No experiment may look at holdout. Record each with `sphinx record-experiment` before running.

## Acceptance criteria before frozen holdout

These are research gates, not guarantees:

1. Sufficient trades across multiple years and at least several volatility/range/trend regimes.
2. Positive net expectancy and profit factor above 1 in aggregate development **and** validation.
3. No single month, side, hour, or regime explains most net P&L.
4. Maximum drawdown fits the predeclared risk budget.
5. Base and pessimistic execution do not reverse the entire conclusion.
6. Neighboring consolidation/displacement/retrace parameters produce a stable region.
7. Walk-forward folds show repeatability, not one exceptional interval.
8. Monte Carlo drawdown/loss probability remains acceptable at 0.10%, 0.25%, and 0.50% risk settings.
9. All data quality, rollover, timezone, and news-calendar limitations are documented.
10. Strategy and runtime config are fingerprinted and frozen before one holdout evaluation.

## Rejection criteria

Reject rather than keep tuning when:

- net expectancy is non-positive after base costs;
- pessimistic costs erase the edge;
- validation materially disagrees with development;
- results depend on a tiny trade count or one market period;
- best parameters are isolated spikes;
- maximum drawdown/losing streak violates controls;
- plausible one-bar entry delay reverses the result;
- required data cannot establish causal fills.

## Result template for a real dataset

```text
Dataset ID and SHA-256:
Vendor / contract months / rollover:
Timezone / session calendar:
Date coverage:
Partition evaluated:
Config fingerprint:

Trades:
Gross P&L before costs:
Spread + slippage cost:
Commissions + fees:
Net P&L:
Expectancy:
Profit factor:
Max/average drawdown:
Sharpe/Sortino (if sample appropriate):
Maximum consecutive losses:
MAE/MFE:
By hour / direction / regime:

Optimistic / base / pessimistic:
Walk-forward folds:
Monte Carlo assumptions and drawdown percentiles:
Known limitations:
Decision: keep / reject / gather more data
```

## What must never be inferred from future output

- A positive backtest is not a guarantee.
- Passing a prop-account rule is not proof of persistent edge.
- Copied positions across accounts are one economic trade, not independent observations.
- High win rate does not replace expectancy and tail-loss analysis.
- Paper fills do not establish live queue priority or capacity.
- Similarity to a public chart does not establish exact replication of Matthew Scriv's private/discretionary process.
