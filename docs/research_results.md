# Deliverable 6 — Research Results and Claim Boundary

## Current evidence status

| Required result | Status | Why |
|---|---|---|
| Source extraction | Complete for the requested public video | See `research_report.md`. |
| Mechanical baseline | Implemented | See runtime config, machine spec, and tests. |
| Historical baseline result | **Not run / no claim** | No licensed, point-in-time 2-minute NQ or MNQ contract dataset was supplied or committed. |
| Development experiments | **Not run** | Running synthetic data would not answer the trading hypothesis. |
| Validation result | **Untouched** | Intentionally unavailable until development hypothesis exists. |
| Final holdout | **Locked and untouched** | Config remains `strategy_frozen=false`. |
| Execution stress | Tool implemented; market result pending | Requires the same real partition. |
| Monte Carlo | Tool implemented; market result pending | Requires a sufficient observed trade series. |
| Final selected profitable configuration | **None** | There is no empirical basis to select or claim one. |
| Paper deployment | CSV-replay paper system implemented | This validates architecture, not expectancy. |

## Honest baseline conclusion

The software makes the source-inspired hypothesis testable. It does **not** establish that it works. A selected YouTube winner cannot provide expectancy, realistic drawdown, or regime robustness. Synthetic fixture results are prohibited from being presented as trading research because the generator contains deliberately structured moves for software-path testing.

The answer to “does this demonstrate robust performance after costs?” is currently **unknown**, not yes.

## Engineering validation (not trading research)

On 2026-08-14:

- all **28** standard-library unit/integration tests passed;
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
