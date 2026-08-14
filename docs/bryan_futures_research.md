# Bryan Futures public-method research and experiment

Research date: 2026-08-14  
Status: **candidate rejected; not promoted to paper signals**  
Holdout: **locked and unopened**

## Identity and source boundary

The requested trader was confirmed as Instagram **@bryanfutures**. His public profile describes his focus as “rejection blocks” and links **@thankunq**. Public posts also tag Matthew Scriv, and a separately tagged trader credits both Matthew Scriv and @bryanfutures for teaching him. These observations support the collaboration claim, but they do not prove performance.

Primary public pages reviewed:

- Instagram profile: <https://www.instagram.com/bryanfutures/>
- Public mirror of profile/posts: <https://imginn.com/bryanfutures/>
- “Free INFO” post (2026-07-23): <https://imginn.com/p/DbJOxnqusP5/>
- Earlier post tagging Matthew Scriv: <https://imginn.com/p/DWRSS8eDeYn/>
- Public key-open rejection-block specification by FWS: <https://www.tradingview.com/script/PGP60HkE-Powell-Key-Opens-KO-Rejection-Blocks-by-FWS/>
- Public rejection-block/CE specification by FWS: <https://www.tradingview.com/script/xWAzSVpj-Rejection-Block-by-FWS-Powell-RBs/>

Instagram did not expose a reliable transcript through the research environment. Therefore, viewer comments under “Free INFO” (“key open rejection block” and “Powell’s model”) were treated as secondary descriptions—not as Bryan’s verbatim rules. No private course or premium material was used.

## Evidence map

- **EXPLICIT RULE:** Bryan’s public profile says “rejection blocks.”
- **VISUAL EXAMPLE:** His public feed contains NQ/trading posts and tags Matthew Scriv. A chart image alone is not enough to infer a complete algorithm.
- **LIKELY INFERENCE:** The “Free INFO” lesson is a Powell-style key-open rejection-block model. This is supported by multiple public viewer descriptions and an independently published TradingView implementation, but not by a first-party transcript.
- **EXPLICIT RULE (independent public implementation):** Key opens include 00:00 and 02:00 New York. A bearish block has an upper wick reaching/crossing the key open while the candle body remains below it; bullish is the mirror. A block is invalidated when price trades beyond its tip.
- **LIKELY INFERENCE:** Entry at consequent encroachment, the 50% midpoint of the rejection wick.
- **UNCONFIRMED:** A universal one-tick stop buffer and fixed 3R target. These were deterministic research choices, not attributed to Bryan.
- **UNCONFIRMED:** Bryan’s win rate, expectancy, or risk-adjusted profitability. Social payouts and testimonials are not a verified track record.

## Predeclared candidate (EXP-BRYAN-RB-001)

Before viewing results, the candidate was frozen as follows:

1. Keep the existing NQ 2-minute data, 00:00–04:00 New York session, costs, risk limits, and 60/20/20 chronological split.
2. Record only the 00:00 and 02:00 New York opening prices.
3. Form a bearish block when a completed bar’s upper wick reaches a key open and the entire body stays below; bullish is mirrored.
4. Keep the most extreme block for each key open/direction.
5. Never enter on the formation bar. On a later bar, enter at the 50% wick midpoint.
6. Invalidate before filling if the same OHLC bar trades beyond the wick tip (conservative ambiguity policy).
7. Stop one tick beyond the tip; no partial; target 3R.
8. Compare both win rate and realized payoff ratio (average win / average loss) with the unchanged baseline on development and validation.
9. Reject rather than tune if both measures do not improve robustly.

Candidate config fingerprint: `a77d519521fbc6aa1c5bd38da4bbe00387dff0460e30884485a3a3e56ad7b3ae`.

## Results after modeled costs

| Partition/model | Trades | Win rate | Avg win / avg loss | Net P&L | PF | Expectancy | Max DD |
|---|---:|---:|---:|---:|---:|---:|---:|
| Development baseline | 49 | 48.98% | 1.01 | -$136.50 | 0.971 | -$2.79 | 2.40% |
| Development candidate | 526 | 42.78% | 1.23 | -$2,331.40 | 0.917 | -$4.43 | 5.02% |
| Validation baseline | 19 | 15.79% | 2.11 | -$1,843.60 | 0.395 | -$97.03 | 2.00% |
| Validation candidate | 313 | 42.17% | 1.79 | +$6,727.20 | 1.308 | +$21.49 | 2.01% |

Additional observations:

- Candidate development gross P&L was +$19,445, but $21,776.40 of modeled costs turned it negative. The 5% max-drawdown kill fired on 2023-12-14, so the candidate failed the safety rule before completing development.
- Validation bootstrap (5,000 trade resamples): mean expectancy $21.58; p05 $3.60; p50 $21.45; p95 $39.67; P(positive) 97.52%. This is conditional on the observed trades and does not repair the failed development regime.
- Validation execution stress: optimistic +$15,252 / PF 1.84; base +$6,727.20 / PF 1.31; pessimistic **-$5,160.25 / PF 0.16**, with a 5.16% max-drawdown kill.
- Candidate maximum losing streaks were 13 in development and 17 in validation.

## Decision

**REJECT_AND_DO_NOT_PROMOTE.**

The candidate did not meet the user’s requested dual improvement:

- Development win rate fell from 48.98% to 42.78%, while net P&L, PF, expectancy, drawdown, and losing streak worsened.
- Validation win rate and expectancy improved substantially, but realized payoff ratio fell from 2.11 to 1.79.
- Results reversed sharply between development and validation and failed pessimistic execution stress.
- The development safety kill fired.

Accordingly, the active dashboard, TradingView indicator, and frozen baseline were **not changed** to use this candidate. The implementation and config remain only as an auditable rejected experiment; no post-result parameter tuning was performed. Neither the rejected baseline nor this rejected candidate supports a profitability or live-readiness claim.

## Engineering correction exposed by the experiment

Frequent candidate signals revealed that internal risk-policy denials (for example, “maximum trades per session reached”) were incorrectly counted as broker/exchange order rejections. Three ordinary policy denials could latch the repeated-order-rejection kill for the remainder of a backtest. The backtest now distinguishes pre-order policy denials from actual broker rejection events. Regression coverage was added. Rerunning the original baseline after this correction reproduced its prior headline metrics, so the baseline conclusion did not change.
