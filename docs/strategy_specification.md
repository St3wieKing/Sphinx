# Deliverable 2 — Mechanical Strategy Specification

> **Historical rejected specification.** This strategy failed validation and is not active. It is retained for reproducibility only; the dashboard is forced to `WAIT`. See `full_system_refresh_2026-08-14.md`.

The canonical machine-readable research specification is [`spec/strategy_spec.json`](../spec/strategy_spec.json). Runtime values are in [`config/baseline.json`](../config/baseline.json), validated by both Python and [`config/strategy.schema.json`](../config/strategy.schema.json).

## 1. Baseline identity

- **Name:** Scriv-inspired 50% retracement research baseline
- **Mode:** historical simulation and paper replay only
- **Instrument:** NQ, tick size 0.25, point value $20/point per full contract
- **Optional relative-value series:** synchronized ES 2-minute bars for SMT proxy
- **Trade window:** 00:00 inclusive to 04:00 exclusive, configured as America/New_York
- **Execution bars:** completed 2-minute OHLCV
- **Intermediate bars:** causally aggregated completed 5-minute and 15-minute
- **Context bars:** causally aggregated completed 1-hour and 4-hour
- **Default direction:** both long and short, symmetric rules

The session timezone is an automation assumption. NQ contract month/continuous-series construction belongs to the data manifest, not the strategy.

## 2. Inputs and data contract

Each bar requires:

```text
timestamp, open, high, low, close
```

Optional fields:

```text
volume, symbol, interval_seconds
```

Constraints:

1. Timestamp is timezone-aware and normalized to UTC; `Z` is recommended.
2. Rows are strictly increasing and unique.
3. OHLC invariants hold (`low ≤ open/close ≤ high`).
4. Bars represent completed intervals, not updates to an open candle.
5. Raw OHLC is chart/mid price. The simulator separately applies spread, slippage, fees, and commissions.
6. The user must document source, contract, rollover, exchange timezone, missing-bar handling, and whether prices are back-adjusted.

No missing bar is synthesized. A gap inside the active trade session above the configured threshold latches the stale-data kill switch.

## 3. Causal market structure

### ATR

```text
TR[t] = max(high[t]-low[t], |high[t]-close[t-1]|, |low[t]-close[t-1]|)
ATR[t] = arithmetic mean of latest P completed TR values
```

The breakout at `t` uses `ATR[t-1]` for location and threshold tests.

### Fixed pivot method (default)

With left window `L` and right window `R`, candidate bar `c=t-R` becomes a swing high at `t` only when:

```text
high[c] > every high in c-L ... c-1
high[c] >= every high in c+1 ... c+R
```

Swing lows are inverse. `occurred_at=c`, `confirmed_at=t`. No strategy component may consume the pivot before `confirmed_at`.

### Alternative methods

- **Fractal:** same delayed algorithm with 2 left and 2 right bars.
- **ATR reversal:** online candidate extreme confirms only after reversal of configured ATR multiple.
- **Percentage reversal:** online candidate extreme confirms only after configured percentage reversal.

Methods are compared as controlled experiments; none is selected because it produces the prettiest development curve.

### Labels and structure

New highs/lows are compared with the prior same-kind confirmed pivot using tick tolerance:

```text
HH / LH / equal high
HL / LL / equal low
```

A close through the latest confirmed high is bullish BOS; through the latest confirmed low is bearish BOS. A BOS opposite the current tracked trend is a mechanical market-structure-shift proxy. These labels are context/analytics and are not baseline entry requirements.

### Regime

Over a completed rolling window:

```text
efficiency = |last close - first close| / Σ|close[i]-close[i-1]|
```

- recent mean range sufficiently above older mean range → expansion;
- efficiency above threshold → up/down trend by net direction;
- otherwise → range;
- insufficient history → unknown.

Regimes are reported, not optimized in baseline.

## 4. Liquidity engine

Every confirmed pivot becomes a level with price, side, type, timeframe, strength, touches, creation and confirmation timestamps, distance, scope, sweep/consumption state, and source IDs.

### Level lifecycle

- Highs are buy-side liquidity; lows are sell-side.
- Pivots within configured tick tolerance merge into an equal-high/equal-low level.
- **Touch:** high reaches buy-side level or low reaches sell-side level after confirmation.
- **Sweep/reclaim:** excursion exceeds level by threshold and the same completed bar closes back through it.
- **Consumed:** close exceeds the level plus threshold; consumed levels are inactive.
- **Internal:** inside latest confirmed high-low dealing range (with tolerance).
- **External:** outside that range.

### Rank

```text
score = weighted mean(
    timeframe importance,
    capped touch count,
    recency decay,
    equal-level cleanliness proxy,
    inverse normalized distance,
    session-reference relevance
)
```

Weights are configurable. “Cleanliness” is a proxy based on merged equal levels, not visual judgment. Runner selection chooses nearest eligible same-side active liquidity first, then score as tie-breaker. This reflects “first logical” target rather than maximizing historical profit.

## 5. AOI engine

### FVG

At completed bar `t`, using bars `t-2`, `t-1`, `t`:

```text
bullish FVG when low[t] - high[t-2] >= minimum gap
zone = [high[t-2], low[t]]

bearish FVG when low[t-2] - high[t] >= minimum gap
zone = [high[t], low[t-2]]
```

The FVG does not exist before bar `t` closes. Interactions, partial fill, complete mitigation, age, and invalidation are tracked.

### IFVG

- bullish FVG closes below lower boundary → invalidated and creates bearish IFVG at that close;
- bearish FVG closes above upper boundary → invalidated and creates bullish IFVG.

FVG/IFVG is optional context and disabled as a required baseline condition.

### Excluded AOIs

Order blocks are absent because the primary source does not establish them. OTE beyond the midpoint and premium/discount filters are also absent from baseline. They must enter only as labeled experiments.

## 6. Setup state machine

### Consolidation

Before candidate breakout `t`, inspect exactly the prior `N` completed execution bars:

```text
range_high = max(high[t-N:t])
range_low  = min(low[t-N:t])
valid if range_high - range_low <= ATR[t-1] × max_range_ATR
```

### Displacement break

Long:

```text
close[t] > range_high + breakout_buffer_ticks × tick_size
body[t] >= ATR[t-1] × displacement_min_ATR
```

Short is inverse. If neither or both evaluate true, no setup.

### Impulse

Long origin is consolidation low; short origin is consolidation high. Initial extreme is breakout-bar high/low.

On each later completed bar:

1. Test invalidation and the midpoint that existed before this bar.
2. If that midpoint is not triggered, update extreme after close when a new directional extreme exists.
3. Recalculate midpoint for the next bar.

This ordering prevents using a same-bar new extreme to manufacture an earlier fill.

### Midpoint trigger

```text
midpoint = (origin + extreme) / 2
```

Default `touch` mode treats a later crossing of the previously known midpoint as a trigger-market signal. A long must span from at/above the midpoint to at/below midpoint plus tolerance; short is inverse.

Optional `close_rejection` requires touch plus a directionally aligned body closing beyond midpoint. It enters at the **next bar open**, never at the already-observed close.

### Expiration/invalidation

- expire after configured retrace bars;
- long invalidates on close below origin; short above origin;
- session exit cancels pending entries;
- no simultaneous setup while a position exists.

## 7. Stop, target, and management

### Stop

- **Fixed:** 40 NQ ticks (10 points) from chart entry.
- **Pivotal:** one configured tick beyond impulse origin.
- **Default fixed-or-pivotal:** choose pivotal only when its distance is positive and no more than 40 ticks; otherwise fixed.

The final selection rule is an automation assumption. Position sizing includes adverse entry and stop execution plus round-trip fees.

### Targets

1. Target one = tracked impulse extreme.
2. Target two = nearest eligible confirmed same-side liquidity beyond target one.
3. If none exists, target two = origin ± `1.66 × impulse width`.
4. Reject setup if target two does not preserve direction ordering or configured minimum R:R.

### Management

- Integer partial quantity = floor(total quantity × fraction) aligned to contract increment.
- If only one contract is allowed, no fractional futures contract is invented; target one is observational and full exit remains at target two.
- After actual target-one partial, remaining chart stop moves to chart entry.
- No discretionary averaging/pyramiding.
- Session-end force-flat is enabled.

## 8. Execution model

Base assumptions per side:

```text
spread = 1.0 tick round-trip quote width
slippage = 1.0 tick per fill
commission = $2.50 per contract
exchange fee = $0.35 per contract
```

A long entry pays midpoint chart price plus half spread plus slippage; long exits receive chart price minus the same. Shorts invert.

### OHLC ambiguity

- Existing stop and target in one bar → stop first.
- Entry bar → adverse stop is permitted; favorable exit is forbidden.
- Gap through stop → worse bar open before execution costs.
- Partial and break-even level both spanned → assume partial then break-even exit of remainder.
- Higher-timeframe aggregates appear only on the first lower-timeframe bar of the next bucket.

These assumptions intentionally bias away from attractive but unknowable fills.

## 9. Risk constraints

```text
risk budget = current closed equity × 0.25%
per-contract worst modeled loss =
    chart stop distance × point value
  + adverse entry and stop execution
  + round-trip commissions and fees
quantity = floor(risk budget / per-contract loss)
```

Then enforce quantity increment, maximum two contracts, one open position, and maximum notional exposure. Setup score never increases size.

Hard controls:

- 1% session marked-equity daily loss → no entries until next session;
- 5% maximum marked-equity drawdown → latched/manual review;
- maximum three trades/session;
- after two consecutive losses, 60-minute cooldown;
- repeated broker rejection kill;
- stale data, abnormal spread, execution error, position mismatch, invalid risk, or unexpected account state kills.

Critical kills cancel pending entries, stop new entries, preserve logs, and optionally flatten the simulated position. No live-money adapter exists.

## 10. Edge-case policy

| Edge case | Deterministic handling |
|---|---|
| Multiple liquidity pools | Nearest eligible active level, score tie-break. |
| Barely exceeds liquidity | Must meet excursion threshold; otherwise touch only. |
| Sweeps both sides in one bar | Both events may log; SMT outside bar emits no directional event. No baseline sweep entry. |
| Extremely volatile | ATR scales location/displacement; fixed stop still applies; size may become zero; spread kill remains hard. |
| Ranging market | Consolidation may form, but entry still requires buffered displacement. Regime is reported. |
| Overlapping FVGs | Retained as independent zones; no union that uses hindsight. |
| Several entries | Single-position rule; state machine tracks one impulse. |
| Scheduled event | No calendar supplied; this is a known unsupported safety input, not assumed safe. |
| Missing data | No interpolation. Active-session stale gap kills. |
| Excess spread/slippage | Spread above cap kills; slippage scenarios are stressed. |
| Stop and target same bar | Stop first. |
| New extreme and old midpoint touched same bar | Old, previously known midpoint triggers; new extreme cannot rewrite that fill. |
| One contract with 50% partial | No partial; hold to final target/stop. |
| Contract rollover | Input provider must split/normalize; no hidden rollover adjustment. |
| Session ends with position | Force close at last completed in-session close. |
