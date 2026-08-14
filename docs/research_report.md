# Deliverable 1 — Source Research and Strategy Extraction

## Research conclusion first

The public video supports a **50% retracement continuation model**, but it does not disclose a complete deterministic strategy. The reproducible core is:

1. form a short-term directional bias;
2. identify a consolidation and a directional break;
3. draw a range from the move's origin to its newest extreme;
4. keep moving the extreme while price does not retrace;
5. enter when price returns to 50%;
6. place a fixed 40-tick or “pivotal” stop;
7. take an initial profit near the prior extreme and optionally hold a runner toward equal highs/lows or other obvious liquidity.

The source does **not** objectively define bias, consolidation, a pivotal level, confirmation, liquidity ranking, or the choice between stop alternatives. It is one retrospective walkthrough of a winning trade, not a rulebook or performance study. This project therefore implements a transparent **Scriv-inspired proxy**, not an exact replication.

No profitability conclusion can be drawn from the source or from this repository without suitable licensed historical NQ data and untouched out-of-sample results.

## Source protocol

### Primary source

- Matthew Scriv / Scriv Trades, [“How I Made 16.5k Trading NQ Futures at 1 AM | Inside My Brain (In-Depth)”](https://www.youtube.com/watch?v=8G-RuiS6_ug), published 2025-10-01, 19:18.
- Source type: narrated, post-trade chart walkthrough of one selected NQ winner.
- Evidence used: spoken transcript plus chart narration.
- Timestamp ranges below are navigation aids. YouTube's auto-caption transcript is imperfect, so a statement—not a timestamp alone—is the evidence unit.

### Supplementary official material

Two later videos on the same official channel were reviewed only as a consistency check:

- [“The A+ Setups That Passed 20 Accounts In One Trading Day”](https://www.youtube.com/watch?v=RS9FUwexnFQ)
- [“Making $9,500 On A LIVE ACCOUNT Trading NQ1!”](https://www.youtube.com/watch?v=sALrHbf-WQQ)

They repeatedly describe consolidation → breakout → 50% retracement, a 40-tick stop, a 1.6/1.66 extension, and liquidity targets. They also introduce other ideas, especially standard deviation and true-day open. Those later ideas are **not silently imported into the baseline**, because the requested primary source says standard deviation was not used for its example.

Third-party summaries and comments were not treated as strategy evidence.

### Primary-video navigation index

These are intentionally broad, approximate sections rather than fabricated frame-accurate citations:

| Approximate segment | Material reviewed |
|---|---|
| 00:00–05:30 | Background, futures preference, copied prop accounts, selected-trade P&L context. |
| 05:30–08:10 | “Simple” strategy framing, ES/NQ SMT, preferred overnight window, and timeframe stack. |
| 08:10–10:20 | Midnight rejection wick, Fibonacci levels, OTE as discretion, and missed IFVG hypothetical. |
| 10:20–12:40 | Missed first 50% entry, moving the range to each new high, eventual midpoint tap. |
| 12:40–14:20 | Entry detail, bullish engulfing/rejection comments, pivotal versus 40-tick stop, adding ambiguity. |
| 14:20–17:10 | Equal-high/liquidity target, first partial, original range-high target, break-even behavior. |
| 17:10–18:15 | Summary: short-term bias → consolidation break → big move → 50% return → breakout. |
| 18:15–19:18 | Prop-account/payout discussion and closing commentary; no new complete mechanical rule set. |

Where auto-caption wording and chart narration conflict, the lower-confidence label is retained.

## Source limitations and integrity notes

1. **Selection bias:** only a winner is explained. No consecutive signal log is presented.
2. **No denominator:** “win rate is pretty good” is not accompanied by trades, dates, losses, costs, or methodology.
3. **Retrospective discretion:** the speaker repeatedly describes things he “likes,” would “hawk,” or uses for “confidence.”
4. **No exact market record:** contract month, trade date, chart timezone, and feed are not established in the narration.
5. **P&L transcription ambiguity:** $1,500 × 11 accounts equals $16,500, matching the title; an auto-caption renders one spoken amount as $165,000. P&L claims are not inputs to this research.
6. **Internal contradiction:** the source says the one-minute chart is never used, then later mentions adding when a one-minute candle starts rising. Pyramiding and one-minute confirmation are excluded.
7. **Affiliate/prop-firm discussion:** much of the video concerns account providers and payouts. None of it supplies evidence of strategy expectancy.

## Concept evidence matrix

Confidence means confidence in what the source demonstrates, not confidence that the idea is profitable.

| Concept | Evidence and source statement | Label | Confidence | Automation decision |
|---|---|---|---:|---|
| Market/instrument | The narrated trade is NQ/NASDAQ futures; ES is opened for comparison. | **EXPLICIT RULE** | High | Baseline NQ; optional synchronized ES context. |
| Overnight timing | He says his recent profitable window is roughly midnight to 3 or 4 a.m. and that he rarely trades New York. | **EXPLICIT RULE** for preference; timezone **UNCONFIRMED** | Medium | 00:00–04:00 America/New_York is a configurable inference, not a discovered fact. |
| Timeframes | “Two minute” for exact entries; 5/15 minute for 50% retrace; 1h/4h for FVGs; says he never uses 1m. | **EXPLICIT RULE** | High | 2m execution, 5m/15m intermediate, 1h/4h context. Baseline excludes 1m. |
| Short-term bias | He says the entire trade starts with a bias and emphasizes it need not be the full-day direction. | **EXPLICIT need**, construction **UNCONFIRMED** | High/Low | Mechanical proxy is direction of a qualified consolidation breakout. |
| ES/NQ SMT | He identifies divergent lows on ES and NQ as a major reversal/flip confluence. | **EXPLICIT confluence** | High | Causal rolling divergence detector exists; disabled by default because it is not stated as mandatory. |
| Rejection wick | He marks a midnight rejection wick and says it is discretion/confluence, not entirely his strategy. | **EXPLICIT discretionary context** | High | Not required. No subjective wick is promoted to a core rule. |
| Fibonacci / OTE | He uses 0, .5, .75 and 1, likes the reaction at an OTE level, and distinguishes it from his core. | **EXPLICIT tool**, role discretionary | High | Core uses only the 50% midpoint and configurable 1.66 extension fallback. OTE/premium-discount filter is absent. |
| IFVG | He shows an earlier IFVG entry he missed and says he probably would not have taken it. | **VISUAL EXAMPLE**, not taken | High | Deterministic IFVG detector exists for experiments; not an entry model in baseline. |
| Consolidation | In the closing summary he says he wants a break of consolidation, a big move, a return to 50%, then continuation. | **EXPLICIT sequence**, boundary **UNCONFIRMED** | High/Low | Prior N-bar range constrained by ATR. Parameters are experimental. |
| Evolving impulse range | After missing a retest he follows each new high; no entry exists until a newly drawn 50% is tapped. | **EXPLICIT RULE** | High | Extreme is updated only after each completed bar if the previously known midpoint was not touched. |
| 50% retest entry | He repeatedly calls the 50% retest the basic and most consistent strategy used about 90% of the time. | **EXPLICIT core rule** | High | Standing midpoint trigger in baseline. Optional close-rejection mode waits until next open. |
| Bullish engulfing/rejection | He says he also likes the bullish engulfing and later discusses averaging on rejection. | **LIKELY INFERENCE** as confirmation, not clearly required | Medium | Optional only. Touch is the baseline trigger. |
| Stop: 40 ticks | He says the original 50% entry had a 40-tick stop and generally tells people to use one. | **EXPLICIT RULE** | High | NQ 40 ticks = 10 points. Costs are added to loss sizing. |
| Stop: pivotal low/high | For a small range he uses a low whose break would imply continuation down; stops/targets should be “pivotal.” | **EXPLICIT concept**, selection **UNCONFIRMED** | Medium | If origin-plus-buffer is within 40 ticks, use it; otherwise fixed 40. This selection is an experimental deterministic interpretation. |
| First target | Original strategy takes the range high / approximately 1R and he takes half there. | **EXPLICIT RULE** | High | First target is the tracked impulse extreme. Integer contracts may make a partial impossible. |
| Runner target | He targets relative equal highs/obvious liquidity, watches an FVG, and describes 1.6/1.66 as a target elsewhere. | **EXPLICIT concept**, exact choice **UNCONFIRMED** | Medium | Nearest active confirmed same-side liquidity beyond target one; fallback 1.66 range extension. |
| Break-even | After taking a partial he moves the stop to break-even or slightly profitable, near the entry the model says should hold. | **EXPLICIT RULE** | High | Remainder stop becomes chart entry. Same-bar ambiguity is resolved adversely. |
| Trailing | Later, after breaking above a level, his stop goes to a newer low. | **VISUAL EXAMPLE**, thresholds unclear | Medium-Low | Not in baseline; break-even after partial is the only trail. |
| Trendline | He says the drawn line is doodling/peace of mind and not part of the strategy. | **EXPLICIT NON-RULE** | High | Excluded. |
| Standard deviation | He says it was not used for the primary trade. | **EXPLICIT NON-RULE for example** | High | Excluded from baseline. |
| Order blocks | Not established in the primary video. | **UNCONFIRMED** | High | Excluded. |
| Volume filter | No mechanical volume condition is stated. | **UNCONFIRMED** | High | Excluded. |
| News filter | No scheduled-event rule is stated. | **UNCONFIRMED** | High | No news-calendar integration. Operators must not represent this absence as evidence that news is safe. |
| Daily risk rules | No equity risk percentage, daily loss cap, maximum trades, or drawdown kill is taught. | **UNCONFIRMED** | High | Added safety constraints, clearly labeled experimental. |

## Actual source-derived sequence

```text
CONFIGURED OVERNIGHT SESSION
        ↓
Form a short-term directional bias
(source demonstrates SMT / OTE / rejection-wick confluence,
but does not provide a mandatory formula)
        ↓
Find short-term consolidation
        ↓
Large directional break / expansion?
        ├── No → Continue monitoring
        └── Yes
               ↓
        Draw origin → current extreme
               ↓
        50% retraced?
        ├── No → Move extreme after each completed extension
        └── Yes
               ↓
        Enter at 50% (rejection/engulfing liked but not proven mandatory)
               ↓
        Stop at pivotal low/high or roughly 40 ticks
               ↓
        First target: prior extreme / range high-low
               ↓
        Partial, then stop near break-even
               ↓
        Runner: relative equal high/low or obvious liquidity
               ↓
        Exit and review
```

## What is not safely automatable from the video

- The original directional-bias process.
- Which visual consolidation is meaningful.
- Which wick or low/high is “pivotal.”
- When to choose fixed rather than structural stop logic.
- What exact reaction invalidates a watched FVG.
- The exact definition and ranking of “obvious” liquidity.
- The discretionary add-on entry and size.
- Whether the session clock is Eastern, exchange, local, or chart time.

The implementation isolates every item above behind a named proxy/configuration. It does not relabel inference as source fact.

## Objective answer to the mission question

**Parts can be converted; the publicly observable methodology cannot be perfectly replicated.** The 50% retracement sequence is mechanically testable. The source's bias and discretionary confluence selection are under-specified, so any autonomous implementation necessarily tests a proxy hypothesis. Whether that proxy has positive expectancy remains unanswered until a properly licensed, high-quality, multi-year NQ dataset is run through development, validation, frozen holdout, and stress protocols.
