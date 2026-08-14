# Full System Refresh, Research Audit, and Rebuild

**Date:** 2026-08-14  
**Scope:** NQ/MNQ research system, data, strategy logic, probability research, execution simulator, risk, monitoring, dashboard, TradingView, and deployment boundary  
**Final decision:** **NO AUTONOMOUS STRATEGY SELECTED — SIGNALS SUSPENDED**  
**Final holdout:** **LOCKED AND UNOPENED (104,691 bars)**

> This is a research result, not financial advice, a profitability claim, or authorization to trade. The correct output of a strategy-selection process can be “do nothing.” That is the output here.

---

# PART 1 — EXECUTIVE SUMMARY

## What changed

The system was treated as potentially wrong rather than incrementally optimized.

1. The original Scriv-inspired 50% retracement strategy remains empirically rejected.
2. The Bryan/Powell key-open rejection-block experiment remains rejected.
3. Five new objective liquidity/rejection families were defined and evaluated:
   - A — basic sweep/rejection;
   - B — directional-close confirmation;
   - C — post-sweep structure shift;
   - D — higher-timeframe/reference-level sweep;
   - E — displacement confirmation.
4. A causal event lab now evaluates 1R, 1.5R, 2R, 3R, and 4R counterfactual targets after modeled costs.
5. An interpretable L2-regularized logistic probability model was trained on the first 75% of development events, Platt-calibrated on the last 25%, and evaluated once on validation.
6. The adaptive target policy requires positive expected value using a **90% Wilson lower confidence bound**, not merely a point probability.
7. That uncertainty-aware policy selected **zero trades** in both development calibration and validation. It correctly refused to manufacture confidence from weak predictors.
8. The dashboard now always reports `WAIT` and `RESEARCH_SUSPENDED_NO_VALIDATED_EDGE`.
9. The TradingView indicator is renamed rejected/disabled and has signals disabled by default.
10. A malformed multi-timeframe assumption was corrected: 2-minute bars cannot causally create exact 5-minute or 15-minute bars because they straddle boundaries. Invalid intermediate aggregation was removed and the resampler now rejects non-divisible intervals.
11. A weekly 2.5% loss kill was added between the 1% daily loss limit and 5% maximum drawdown.
12. A detailed, hash-chained decision-log schema was added for rejected, skipped, approved-paper, and closed-paper decisions.
13. Historical configurations were preserved as `*_v0_2_legacy.json` for fingerprint provenance, not deployment.

## Why no replacement strategy was selected

The broad result is negative:

- Models A, B, D, and E had negative after-cost expectancy in both development and validation at every reported target.
- Model C was negative in development and only marginally positive in validation at 2R–4R. That is non-persistent and fails the acceptance gate.
- Validation Brier skill over a constant base-rate forecast was only **0.02% to 1.09%**, depending on target. The features barely improved probability forecasts.
- The confidence-bound EV gate selected no trades.
- No model passed development, validation, cost stress, persistence, and uncertainty requirements together.

The rebuild therefore improves safety, auditability, and research capability—but does not pretend the available evidence supports autonomous trading.

---

# PART 2 — OLD SYSTEM AUDIT

## System-wide findings

### Strategies

| Component | Purpose | Evidence | Incremental/OOS finding | Decision |
|---|---|---|---|---|
| Scriv-inspired consolidation → displacement → 50% retest | Mechanize the public walkthrough | Explicit public concepts, but deterministic details were inferred | Development PF 0.971; validation PF 0.395; after-cost expectancy negative | **REMOVE FROM ACTIVE USE / retain as rejected research** |
| Bryan/Powell key-open rejection block | Tight structural entry from 00:00/02:00 rejection wick | Public rejection-block material plus secondary public implementation | Development worsened and hit 5% DD; validation improvement failed dual-metric and pessimistic-cost gates | **REMOVE FROM ACTIVE USE / retain as rejected research** |
| Arbitrary setup score | Rank location, displacement, liquidity, context, freshness | Weights were opinion-based | Never calibrated as a probability and did not gate risk | **REMOVE FROM ACTION PATH** |
| Arbitrary liquidity score | Rank pivot/equal/session levels | Plausible inputs, subjective weights | No demonstrated incremental OOS value | **REMOVE FROM ACTION PATH; research features retained** |
| FVG/IFVG score | Context and confluence | Objective gap detection; quality weights subjective | Not independently shown to improve OOS expectancy | **REMOVE FROM ACTION PATH** |
| SMT proxy | NQ/ES divergence | Mechanically causal when synchronized | No ES dataset supplied, so no real test | **UNCONFIRMED / inactive** |

### Entry and market logic

- **Consolidation:** objectively defined and causal, but the complete strategy failed validation. It is not evidence of edge by itself.
- **Displacement:** body/ATR is measurable. New tests show displacement confirmation improves raw rejection results relative to basic rejection, but remains negative after costs.
- **50% midpoint:** explicit in the Scriv source, but no positive OOS result.
- **Touch entry:** highly fill-sensitive and vulnerable to OHLC ambiguity. Conservative stop-first ordering was correctly used.
- **Close-rejection entry:** more confirmation, but no independent validated edge.
- **Market structure:** delayed pivots avoid repainting. Labels are useful descriptive state, not proven forecasts.
- **Regime classifier:** simple path efficiency and range expansion. It is causal but too coarse and was never proven as an entry gate.
- **Premium/discount:** mechanically definable from a dealing range, but the choice of dealing range is not unique. Excluded from autonomous use.

### Exits and trade management

- The original TP1 partial plus break-even runner was deterministic and conservatively sequenced.
- Its value was not isolated from the rejected entry system.
- The fixed-or-pivotal stop included inferred choices and dev-sensitive stop behavior.
- The new research lab compares target probabilities and cost-adjusted EV rather than assuming a large R:R is superior.
- No adaptive target had sufficiently reliable probability estimates to trade.

### Risk

**Kept or strengthened:**

- bounded percent-risk sizing;
- instrument contract cap;
- notional exposure cap;
- one position at a time;
- 1% daily loss kill;
- **new 2.5% weekly loss kill**;
- 5% maximum drawdown kill;
- consecutive-loss cooldown;
- maximum trades per session;
- stale-data, abnormal-spread, invalid-data, execution-error, and position-mismatch kills.

**Not added:** confidence-proportional sizing. Calibration was too weak. Risk does not rise when a model reports higher confidence.

**Not applicable:** correlation-aware exposure while the engine permits only one position and has no validated multi-instrument strategy. It becomes mandatory before multi-instrument execution.

### Data

| Item | Audit result | Decision |
|---|---|---|
| CC0 NQ continuous OHLCV | Hash-pinned, deterministic normalization, clean ordering; rollover methodology still third-party | **KEEP for research with warning** |
| NQ 2-minute bars | 523,455 complete normalized bars | **KEEP** |
| MNQ modeled from NQ | Economics experiment only; not independent price evidence | **REMOVE from independent-evidence claims** |
| ES | Missing | SMT and intermarket claims cannot be validated |
| Level-2/order book | Missing | “Resting liquidity” cannot be directly observed |
| News calendar | Missing | Post-news regimes cannot be reliably labeled |
| 2m → 5m/15m aggregation | Invalid because source bars straddle target boundaries | **REMOVE and reject in code** |
| 2m → 1h/4h aggregation | Exact divisible intervals, emitted only after bucket completion | **KEEP** |
| 60/20/20 split | Strict chronological split | **KEEP** |
| Final 20% holdout | Never opened | **KEEP LOCKED** |

### Backtest and execution

**Kept:**

- completed-bar event loop;
- delayed pivot confirmation;
- completed higher-timeframe bars only;
- stop-first same-bar policy;
- no favorable exit on entry bar;
- adverse spread and slippage on every fill;
- worse opening fill through stops;
- commissions and exchange fees;
- force-flat at the last known in-session bar;
- mark-to-market risk monitoring.

**Limitations that remain:**

- OHLC cannot reveal exact intrabar path;
- spread is modeled, not historical bid/ask;
- no queue position or limit-order fill probability;
- no partial-fill model;
- no exchange-specific variable latency;
- continuous-contract execution cannot reproduce actual contract-roll fills;
- the paper trader is historical replay, not a resilient real-time execution service.

### Brokerage and APIs

- No Tradovate, Interactive Brokers, or live-money adapter exists.
- TradingView webhook intake is authenticated, size-limited, hash-chained, and receive-only.
- It does not route orders.
- No restart reconciliation, broker position reconciliation, idempotent order keys, or disaster recovery exists because there is no broker adapter.
- Live readiness is therefore **false**.

### Logging and operations

- Hash-chained JSONL audit is useful for tamper evidence.
- A new detailed decision schema records features, probabilities, uncertainty, target candidates, EV, stop logic, expected/actual fills, slippage, outcome, R, MAE, and MFE.
- JSONL is not a transactional database; process crash durability and cross-process locking are limited.
- Before a real broker integration, storage needs atomic writes/fsync or a transactional database, idempotency, restart snapshots, and reconciliation tests.

---

# PART 3 — RESEARCH FINDINGS

## Research foundation

The rebuild used two kinds of source material:

1. **Primary public methodology:** Inter Equity Trading’s own YouTube transcripts.
2. **Independent quantitative caution/evidence:** market-microstructure and backtest-overfitting research.

Key independent findings:

- Osler documents clustering of stop-loss and take-profit orders around salient price levels in FX, providing a plausible mechanism for rapid movement or reversal—but not proof that every candle-chart “liquidity pool” predicts NQ [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=923370).
- Bailey and López de Prado show that multiple testing and non-normal returns inflate backtest Sharpe estimates; trial counts and selection bias matter [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551).
- Bajgrowicz and Scaillet find that many technical rules lose apparent value after transaction costs and persistence testing [Journal of Financial Economics abstract](https://www.sciencedirect.com/science/article/abs/pii/S0304405X1200116X).
- Probability forecasts require calibration as well as ranking. Brier score and reliability bins were therefore implemented.

## Liquidity research

### What OHLCV can objectively approximate

- confirmed swing highs/lows;
- equal/clustered highs and lows within a tick tolerance;
- previous-day and previous-week highs/lows;
- overnight highs/lows once the overnight period is complete;
- 00:00, 08:30, and 09:30 opening prices;
- wick excursion through a known level;
- close back through the level;
- continuation versus reversal after the event;
- event age, prior clustering, ATR-scaled excursion, volume z-score, session, and trend efficiency.

### What OHLCV cannot prove

- actual resting order quantity;
- actual stop inventory;
- spoofing, pulling, absorption, queue position, or iceberg orders;
- that a sweep was intentional;
- which market participant was “trapped.”

The implementation therefore calls these **liquidity proxies**, not measured liquidity.

### Liquidity quality score result

The old score used subjective weights. The refresh replaced that hypothesis with model features and out-of-sample calibration. Features included cluster count, age, reference-level type, sweep/ATR, reclaim/ATR, wick properties, volume, session, trend efficiency, and confirmation family.

The learned model had almost no OOS skill over the base rate:

| Target | Validation Brier | Base-rate Brier | Brier skill | ECE (5 equal-count bins) |
|---|---:|---:|---:|---:|
| 1R | 0.24598 | 0.24642 | 0.18% | 1.30% |
| 1.5R | 0.22617 | 0.22629 | 0.05% | 1.87% |
| 2R | 0.20158 | 0.20162 | 0.02% | 2.04% |
| 3R | 0.15384 | 0.15497 | 0.73% | 1.60% |
| 4R | 0.11821 | 0.11951 | 1.09% | 0.93% |

Low ECE alone is not sufficient: a nearly constant base-rate forecast can be calibrated but useless for selection. The tiny Brier skill shows weak resolution. **No live liquidity quality score was approved.**

## Rejection-block research

Objective definitions were tested rather than choosing one visual interpretation:

- **A Basic:** confirmed level sweep by at least one tick, wick, and close back through the level.
- **B Confirmed close:** A plus a later directional candle close within five bars.
- **C Structure shift:** A plus a later close through the opposite five-bar pre-sweep structure within five bars.
- **D Multi-timeframe/reference:** A at previous-day/week, overnight, or key-open proxy.
- **E Displacement:** A plus a later directional body of at least 0.8 ATR within five bars.

The variants were evaluated independently across 1R–4R targets with structural stops one tick beyond the sweep and a 30-bar/session horizon.

Main finding: more confirmation generally reduced losses, but only Model C reached marginal positive validation expectancy—and it was negative in development. That is not persistence.

## Market structure

- Fixed 3-left/3-right pivots are causal but delayed.
- A post-sweep structure shift was the strongest family tested.
- Its validation results were small: +0.0066R at 2R, +0.0191R at 3R, and +0.0370R at 4R.
- Development was negative at the same targets: −0.0899R, −0.0629R, and −0.0488R.
- Therefore structure confirmation is **research-interesting but not deployable**.

## Risk/reward research

A fixed high R:R did not solve weak entries. For each event, 1R, 1.5R, 2R, 3R, and 4R outcomes were measured. Larger nominal targets lowered hit rates. Cost in R was especially damaging when structural stops were tight.

The adaptive policy computes:

`EV = calibrated P(target) × (target_R − cost_R) + (1 − P(target)) × (−1 − cost_R)`

It then repeats the calculation using the 90% lower confidence estimate for target probability. A target is eligible only if conservative EV is positive. None survived.

---

# PART 4 — INTER EQUITY TRADING INTEGRATION

## Primary public material reviewed

- [Liquidity Inducement Masterclass Ep. 1](https://www.youtube.com/watch?v=htyknOTK-xs)
- [Liquidity Inducement Masterclass Ep. 2](https://www.youtube.com/watch?v=0whEBw9aHKM)
- [Liquidity Inducement Masterclass Ep. 3](https://www.youtube.com/watch?v=x4ZUCA0GO48)
- [Liquidity Inducement Trading — Entries](https://www.youtube.com/watch?v=60yOXkGhdW8)
- [Liquidity Blocks](https://www.youtube.com/watch?v=GIYrW7FC06M)
- [Liquidity Inducement Trading is All You Need](https://www.youtube.com/watch?v=3Xgukzx6nOw)
- Training the Eyes episodes 3, 7, and 10.

## Extracted concepts and decisions

| Public concept | Objective translation | Status |
|---|---|---|
| A prior high/low is respected and liquidity builds beyond it | Causally confirmed pivots and equal clusters | **Implemented/tested** |
| Taking a high induces buyers; taking a low induces sellers | Crossing a confirmed pivot/reference level | **Implemented as neutral proxy; the psychological attribution is unconfirmed** |
| “Trap” after false reaction | Sweep plus close reclaim | **Implemented/tested; negative basic model** |
| Liquidity block is a high/low that swept prior liquidity and moved away | Sweep extreme retained as structural invalidation zone | **Implemented/tested** |
| Liquidity block provides stop placement | Stop one tick beyond sweep extreme | **Implemented/tested; tight-stop costs were material** |
| Entry from the left when a prior block exists | Sweep/reclaim at a pre-existing reference zone | **Approximated by D HTF/reference; negative** |
| Confirmation entry when no left block exists | Wait for directional close, structure shift, or displacement | **Implemented as B/C/E** |
| Target intact opposing liquidity | Counterfactual fixed-R targets; logical-level targeting remains ambiguous | **Partly implemented; no approved adaptive target** |
| Higher timeframe to lower timeframe narrative | Previous day/week/overnight levels plus lower-TF sweep | **Implemented as causal proxies** |
| New York timing | Separate 08:00–12:00 ET session feature | **Implemented/tested** |
| Do not trade every liquidity block | Probability/uncertainty EV gate | **Implemented; selected zero trades** |
| “No liquidity block, no stop loss” | Reject entry without objective invalidation | **Kept as safety principle** |
| Bias/direction from the market “story” | No unique computer definition in public material | **Unable to automate faithfully; excluded** |
| Trader intent, induced/trapped participants | Not observable from OHLCV | **Excluded as factual claim** |
| Precise M1 refinement | Requires a separate predeclared 1-minute execution study | **Not forced into this 2-minute experiment** |

Public examples and creator performance claims are **visual examples**, not statistical evidence. Affiliate links, testimonials, payout screenshots, and selected trade walkthroughs were not treated as proof of expectancy.

---

# PART 5 — FINAL STRATEGY LOGIC

There is no approved entry strategy. The final production decision tree is intentionally short:

1. **System status check**
   - If no strategy has passed all research gates: `WAIT`.
2. **Data integrity check**
   - Invalid ordering, stale data, incompatible timeframe aggregation, or missing required feed: disable.
3. **Risk state check**
   - Daily, weekly, or maximum-drawdown kill: disable.
4. **Strategy approval check**
   - Candidate must have positive after-cost expectancy in development and validation, stability across folds/definitions, positive pessimistic-cost result, calibrated probability resolution, and adequate sample size.
5. **Current state**
   - No candidate passes step 4.
6. **Decision**
   - `DO NOTHING`.

The research pipeline can generate and score hypotheses offline, but it cannot promote itself.

---

# PART 6 — TRADE PROBABILITY MODEL

## Inputs

Twenty causal features:

- direction;
- model-family one-hot flags;
- wick/range;
- wick/ATR;
- body/range;
- sweep/ATR;
- reclaim/ATR;
- level age;
- cluster count;
- volume z-score;
- signed trend efficiency;
- recent/older ATR ratio;
- confirmation strength;
- cyclical hour;
- overnight versus New York session.

## Model

- L2-regularized logistic regression;
- no external ML dependency;
- first 75% of development events for fitting;
- final 25% of development events for Platt calibration and uncertainty bins;
- validation evaluated once;
- separate model for each target.

## Calibration

Reported:

- Brier score;
- constant base-rate Brier comparator;
- Brier skill;
- equal-count reliability bins;
- expected calibration error;
- 90% Wilson lower bounds.

## Limitations

- Events and model variants are correlated, so event count is not independent sample size.
- Calibration can look acceptable when predictions stay near the base rate.
- Tiny Brier skill means the model cannot meaningfully rank trades.
- No predicted probability is used for position sizing.
- No model is deployed.

---

# PART 7 — ADAPTIVE RISK/REWARD

## Research implementation

For each event:

1. Stop = one tick beyond the sweep extreme.
2. Risk includes adverse entry/exit spread, slippage, commission, and exchange fee.
3. Candidate targets = 1R, 1.5R, 2R, 3R, and 4R.
4. Stop wins ambiguous same-bar target/stop cases.
5. Event exits at target, stop, end of session, or 30 bars.
6. Probability is calibrated separately for each target.
7. Both point EV and confidence-bound EV are calculated.
8. Target with highest confidence-bound EV is considered.
9. If the best confidence-bound EV is not positive, reject the trade.

## Result

No event in the development calibration period or validation passed the conservative EV gate. The adaptive system therefore chose no target and no trade.

Partials and runners were not activated because target probabilities lacked sufficient predictive resolution. Adding more trade-management branches would increase multiple-testing risk without evidence.

---

# PART 8 — BACKTEST AND EVENT-STUDY RESULTS

## Previously rejected baseline

| Partition | Trades | Win rate | Net | PF | Expectancy | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| Development | 49 | 48.98% | −$136.50 | 0.971 | −$2.79 | 2.40% |
| Validation | 19 | 15.79% | −$1,843.60 | 0.395 | −$97.03 | 2.00% |

The audited v0.3 rerun, after removing invalid intermediate aggregation and adding weekly risk control, reproduced these trade metrics exactly.

## Refresh event counts

- Development events: **34,757**
- Model training: **26,067**
- Development calibration: **8,690**
- Validation events: **11,991**
- Holdout events: **not generated**

## Model-family after-cost results

The table reports average net R / R-based profit factor.

| Model | Dev 1R | Val 1R | Dev 2R | Val 2R | Dev 3R | Val 3R | Dev 4R | Val 4R |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A Basic | −0.427 / 0.42 | −0.374 / 0.47 | −0.369 / 0.59 | −0.318 / 0.62 | −0.361 / 0.63 | −0.277 / 0.70 | −0.361 / 0.65 | −0.271 / 0.72 |
| B Confirmed | −0.339 / 0.52 | −0.264 / 0.60 | −0.318 / 0.63 | −0.254 / 0.68 | −0.320 / 0.65 | −0.241 / 0.72 | −0.304 / 0.68 | −0.219 / 0.75 |
| C Structure | −0.087 / 0.83 | −0.006 / 0.99 | −0.090 / 0.85 | +0.007 / 1.01 | −0.063 / 0.90 | +0.019 / 1.03 | −0.049 / 0.92 | +0.037 / 1.06 |
| D HTF/reference | −0.210 / 0.66 | −0.202 / 0.67 | −0.162 / 0.79 | −0.169 / 0.78 | −0.143 / 0.83 | −0.138 / 0.83 | −0.162 / 0.81 | −0.071 / 0.92 |
| E Displacement | −0.208 / 0.65 | −0.128 / 0.77 | −0.183 / 0.74 | −0.112 / 0.84 | −0.165 / 0.78 | −0.085 / 0.88 | −0.146 / 0.81 | −0.072 / 0.90 |

Validation event counts: A 4,879; B 3,874; C 852; D 423; E 1,963.

## Adaptive policy

| Period/scenario | Trades | Net R | Reason |
|---|---:|---:|---|
| Development calibration | 0 | 0 | No confidence-bound positive EV |
| Validation base costs | 0 | 0 | No confidence-bound positive EV |
| Validation costs ×1.25 | 0 | 0 | No eligible trade |
| Validation costs ×1.50 | 0 | 0 | No eligible trade |

This is not “zero drawdown alpha.” It is a refusal to trade because the evidence threshold was not met.

---

# PART 9 — ROBUSTNESS TESTING

## Time separation

- Strict 60/20/20 chronological split.
- Internal development split: 75% fit / 25% calibration.
- Validation used once for the frozen refresh definitions.
- Holdout remained inaccessible.

## Definition and target sensitivity

- Five distinct rejection definitions.
- Five target distances.
- No single positive result persisted from development to validation.
- Model C’s sign flip is a warning, not a selection opportunity.

## Cost sensitivity

- Every event includes spread, slippage, commissions, and exchange fees.
- Tight-stop models averaged large costs in R.
- The approved policy remains empty at 1.25× and 1.5× costs.

## Walk-forward

The old baseline walk-forward folds alternated positive and negative and ended unstable: +583.30, −646.70, −805.60, +611.20, −434.50, −1,438.80.

A selected refresh strategy does not exist, so running a trade-order walk-forward or claiming a Sharpe would be statistically meaningless. The event families already fail development persistence.

## Monte Carlo

- Existing baseline validation bootstrap gave only 4.3% probability of positive mean expectancy.
- The refresh selects zero trades, so trade-order Monte Carlo is undefined.
- Monte Carlo cannot create an edge that the observed process does not contain.

## Multiple testing

All five models and five target paths remain in the report. No isolated maximum was selected. The ledger records the trials and decisions. The final holdout was not used to rescue a candidate.

---

# PART 10 — FAILURE MODES

1. **Costs dominate tight stops.** Small structural stops produce high cost measured in R.
2. **Sweep continuation.** A level can be crossed and continue rather than reverse; “liquidity collection” is not automatically contrarian.
3. **Regime instability.** Structure-shift rejection improved later but not earlier.
4. **Weak model resolution.** Calibrated-looking probabilities remain close to target base rates.
5. **OHLC ambiguity.** Stop and target may both appear inside a bar; exact sequence is unknown.
6. **Latent liquidity is unobserved.** Candle levels are proxies, not actual order inventory.
7. **Continuous-contract limitations.** Actual roll execution is absent.
8. **Historical spread approximation.** No bid/ask series exists.
9. **News blindness.** No point-in-time economic calendar is integrated.
10. **Intermarket blindness.** ES data is absent; SMT is untested.
11. **Selection bias in educational material.** Public examples are selected and discretionary.
12. **Concept overlap.** Structure, liquidity, FVG, blocks, and premium/discount all derive from the same price history; stacking them does not create independent information.
13. **Sparse deployed evidence.** The original strategy had only 19 validation trades.
14. **Operational incompleteness.** No broker reconciliation, idempotent order service, or restart recovery exists.
15. **Model drift.** Even a future calibrated model can become stale; no automatic capital increase is allowed.

---

# PART 11 — FINAL CODE AND ARCHITECTURE REVIEW

## Bugs and flaws fixed

- UTC-labeled hourly metrics corrected to session timezone (prior work).
- Dashboard holdout replay leak corrected (prior work).
- Internal risk-policy denials no longer count as broker order rejections (prior work).
- Invalid 2m → 5m/15m aggregation removed and prevented.
- Weekly loss kill added.
- Dashboard and TradingView rejected signals suspended.
- Overview now reports excluded holdout bars.

## Look-ahead and leakage review

- pivots expose `confirmed_at`, not occurrence time;
- ATR and consolidation use completed data;
- higher-timeframe buckets emit after completion;
- invalid timeframe ratios now fail;
- refresh reference levels become available only after their source day/week/session completes;
- confirmation variants enter only after confirming bars;
- validation is separate from fitting/calibration;
- holdout is locked.

## Race conditions and storage

- Dashboard webhook in-memory list and audit writes are protected by a process lock.
- The HTTP server is threaded, but static research payloads are read-only.
- AuditLogger itself is not a multi-process transactional store.
- No broker execution threads exist.
- Before broker work: add a database, unique event/order IDs, atomic state snapshots, restart recovery, and broker reconciliation.

## API and execution failures

- Webhook token comparison is constant-time.
- Query tokens are redacted from server logs.
- Request size and numeric/order validation exist.
- Webhook status remains `RECEIVED_NOT_ROUTED`.
- No external broker outage behavior exists because no broker is connected.

## New controlled research architecture

`market data → causal event extraction → feature log → development fit → development calibration → validation → uncertainty-aware EV gate → paper candidate (only if passed) → monitored paper period → manual promotion review`

There is no path from a new observation directly to live execution.

## Required future evidence before reconsideration

1. Native contract-specific NQ/MNQ data with documented roll methodology.
2. Historical bid/ask or tick data for spread and intrabar sequencing.
3. ES data for intermarket hypotheses.
4. Point-in-time news calendar.
5. A newly predeclared hypothesis—not target/feature fishing from these results.
6. Positive development and validation after costs.
7. Stable neighboring definitions and rolling windows.
8. Positive pessimistic execution result.
9. Useful OOS Brier skill and calibration.
10. A multi-month real-time paper sample.
11. Only then, broker-demo reconciliation and restart testing.

---

# FINAL KEEP / MODIFY / REMOVE SUMMARY

## KEEP

- strict chronological partitions and holdout lock;
- causal pivots and completed bars;
- deterministic data hashing and manifests;
- conservative stop-first execution assumptions;
- fees/spread/slippage modeling and stress;
- bounded sizing and hard risk kills;
- hash-chained audit records;
- receive-only TradingView webhook;
- offline hypothesis ledger;
- research event/probability/calibration tooling.

## MODIFY

- risk: weekly loss control added;
- resampling: exact interval divisibility enforced;
- dashboard: diagnostic only, action forced to WAIT;
- TradingView: rejected indicator disabled by default;
- logging: detailed feature/probability/EV decision schema added;
- “liquidity”: always labeled an OHLCV proxy unless order-book data exists.

## REMOVE FROM ACTIVE DECISIONS

- original 50% retracement strategy;
- Bryan key-open rejection strategy;
- arbitrary liquidity/setup/FVG scores;
- unvalidated confluence stacking;
- fixed target assumptions;
- confidence-based sizing;
- modeled MNQ as independent evidence;
- malformed 5m/15m context aggregation;
- any suggestion of live readiness.

## FINAL SYSTEM STATE

**Research platform: operational.**  
**Validated autonomous strategy: none.**  
**Paper signal authorization: suspended.**  
**Live trading authorization: nonexistent.**  
**Correct action: WAIT.**
