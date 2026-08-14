# TradingView Indicator

Deliverable: [`tradingview/sphinx_signal_indicator.pine`](../tradingview/sphinx_signal_indicator.pine)

## Scope

The Pine Script® v6 indicator is a chart-side implementation of the public-source-inspired mechanical proxy. It is **not** a copy of undisclosed discretionary rules and it does not place orders.

Use it on a **2-minute NQ or MNQ chart**. The default session is 00:00–04:00 America/New_York, which remains a configurable timezone inference from the source.

## Displayed information

- approved session shading;
- waiting, tracking, active-long, active-short, and cooldown state;
- prior consolidation displacement;
- causally known evolving 50% midpoint;
- impulse origin;
- confirmed, delayed swing liquidity and equal-level highlighting;
- latest execution-timeframe bullish/bearish FVG boundaries;
- completed 1-hour and 4-hour FVG context;
- long/short labels;
- entry, invalidation/stop, TP1, TP2, expected R:R, score, regime, and target provenance;
- TP1, TP2, and stop events;
- compact state table.

## Causality controls

1. Signals require `barstate.isconfirmed`.
2. Breakout range and ATR use `[1]` values.
3. A tracked midpoint exists before its touch bar; an extreme updates only if that midpoint did not trigger.
4. `ta.pivothigh/ta.pivotlow` become available only after right-side confirmation.
5. Higher-timeframe requests use `lookahead_on` **only with historical offsets `[1]` and `[3]`**, exposing completed HTF candles rather than an unfinished value.
6. Outside-session and invalidated/expired candidates reset.
7. Stop is processed before targets in the visual position state.

## Alerts

The indicator defines separate global `alertcondition()` choices for:

- Sphinx Long;
- Sphinx Short;
- Stop / invalidation;
- TP1;
- TP2.

It also emits dynamic JSON through `alert()` on entries. TradingView's [Pine v6 alert documentation](https://www.tradingview.com/pine-script-docs/concepts/alerts/) explains that each global `alertcondition()` call in an indicator creates a selectable alert condition, while `alert()` calls can carry runtime strings. Create alerts with **once per bar close**. Do not connect these directly to live order routing.

Example dynamic payload:

```json
{
  "system": "sphinx",
  "mode": "paper",
  "side": "LONG",
  "ticker": "NQ1!",
  "entry": 0,
  "stop": 0,
  "tp1": 0,
  "tp2": 0
}
```

## Installation

1. Open TradingView and a 2-minute NQ/MNQ chart.
2. Open Pine Editor.
3. Paste the entire `.pine` file.
4. Save and select **Add to chart**.
5. Confirm the chart timezone/data session and the script's America/New_York session input.
6. Create long and short alerts separately; select once per bar close.
7. Paper-observe timestamp and level parity before using any webhook downstream.

## Important execution difference

The indicator confirms a touch after its bar closes. The Python base simulator models a known midpoint as a standing trigger-market level and then applies adverse spread/slippage. These are not identical execution assumptions. Compare **candidate setup timestamps and preexisting levels first**, then test fills separately.

TradingView's candles may also differ because of contract, continuous-series rollover, session, and vendor aggregation. NQ and MNQ should not be treated as independent strategy evidence simply because their charts agree.

## Validation status

The source is checked into the repository and guarded by a regression test that verifies the packaged website copy is identical and contains Pine v6, alerts, and offset higher-timeframe requests. This environment has no official TradingView compiler. The operator must perform final compile and chart-parity checks in TradingView before creating paper alerts.
