# SPHINX-LHM v1.0.0 — Reproducible Backtest Report

Reproduce with: `python scripts/download_data.py && python scripts/run_locked_test.py`
Engine: frozen production path (`sphinx/backtest/run_strategy.py`); costs $0.0135/share/side base; conservative fills; sizing 0.5% risk budget, 2× cap.

## Headline results by period (net of costs)

| Metric | TRAIN 2003-14 | VAL 2015-20 | WALK-FWD 2008-20 | **TEST 2021-26 (locked)** |
|---|---|---|---|---|
| Trades | 645 | 294 | 1,346 | **277** |
| Trades/yr | 53.8 | 49.8 | 103.8 | 53.5 |
| Win rate | 56.4% | 51.4% | 51.6% | 52.0% |
| Avg win (bps) | +36.8 | +35.9 | +27.2 | +23.0 |
| Avg loss (bps) | −31.9 | −34.3 | −22.2 | −25.3 |
| **Expectancy (bps)** | **+6.86** | **+1.74** | **+3.31** | **−0.18** |
| t-stat | 2.86 | 0.48 | 2.58 | −0.09 |
| Profit factor | 1.49 | 1.10 | 1.31 | 0.99 |
| Sharpe (daily, sized) | 1.57 | −0.36 | 1.12 | 0.32 |
| Max DD (sized) | −6.3% | −7.2% | −7.2% | −5.5% |
| Participation | 21.4% | 19.8% | — | 21.0% |
| Stop-outs | 0.16% | 0.34% | 0% | 0% |

Expectancy identity check (TEST): 0.520×23.0 − 0.480×25.3 = −0.19 bps ✓

## Yearly (frozen path)

| Year | Trades | Exp (bps) | Win% | | Year | Trades | Exp (bps) | Win% |
|---|---|---|---|---|---|---|---|---|
| 2003 | 90 | +3.7 | 59% | | 2015 | 52 | +7.0 | 63% |
| 2004 | 7 | +4.9 | 57% | | 2016 | 40 | −2.0 | 48% |
| 2005 | 8 | −0.5 | 62% | | 2017 | 0 | — | — |
| 2006 | 6 | −2.8 | 33% | | 2018 | 61 | −6.2 | 48% |
| 2007 | 59 | +12.3 | 68% | | 2019 | 36 | −0.1 | 53% |
| 2008 | 116 | +26.5 | 67% | | 2020 | 105 | +5.8 | 49% |
| 2009 | 120 | −3.1 | 49% | | **2021** | 38 | +2.1 | 50% |
| 2010 | 83 | +3.3 | 54% | | **2022** | 134 | +1.0 | 53% |
| 2011 | 88 | +5.4 | 56% | | **2023** | 37 | +8.0 | 68% |
| 2012 | 32 | −4.0 | 47% | | **2024** | 13 | −2.4 | 54% |
| 2013 | 18 | −1.2 | 39% | | **2025** | 50 | **−10.7** | 38% |
| 2014 | 18 | +2.5 | 39% | | **2026** (to Apr 9) | 5 | +1.3 | 60% |

## Regime breakdown (rv20 terciles within period; trend vs 200SMA)

| Regime | TRAIN exp | VAL exp | TEST exp |
|---|---|---|---|
| High vol | **+14.0** | **+10.1** | **−4.6** ← inversion |
| Mid vol | +4.4 | −5.7 | +1.8 |
| Low vol | +2.2 | +0.9 | +2.2 |
| Above 200SMA | −1.5 | −3.5 | +2.0 |
| Below 200SMA | **+14.1** | **+7.4** | **−1.8** ← inversion |

## Cost sensitivity (TEST)

| Cost stress | Expectancy | t | PF |
|---|---|---|---|
| 1× ($0.0135/side) | −0.18 bps | −0.09 | 0.985 |
| 2× | −0.64 bps | −0.33 | 0.948 |
| 3× | −1.10 bps | −0.56 | 0.913 |

(TRAIN for reference: 1× +6.86 / 2× +4.4 / 3× +1.9 bps.)

## Monte Carlo (2,000 resampled paths, sized)

| Percentile | TRAIN | TEST |
|---|---|---|
| Max DD p50 | −6.3% | −1.3% |
| Max DD p95 | −10.4% | −2.7% |
| Max DD p99 | −12.3% | −3.5% |
| Losing streak p95 | 12 | 10 |

## Signal census on TEST (1,322 sessions)

SETUP_COMPLETE 277 · LOW_VOL_REGIME 811 · NO_AGREEMENT 147 · MOVE_TOO_SMALL 83 · HALF_DAY 2 · DATA_VALIDATION_FAILURE 2.

## Conclusion

Positive and significant in-sample and in a 13-year walk-forward; statistically and economically **zero in the locked 2021-2026 test**, with the failure concentrated in the 2025 high-volatility episodes where the historical mechanism appears to have inverted (see failure analysis, research report §6). **Result: NO-GO for live deployment; paper trading is the only authorized mode.** All artifacts to re-derive every number in this report live in `research/outputs/`.
