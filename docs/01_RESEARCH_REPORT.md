# SPHINX Research Report — Systematic Day-Trading Strategy Investigation

**Team roles simulated:** quantitative research, systematic trading, market microstructure, statistics, backtesting engineering, risk management, algo development.
**Data:** SPY 1-minute OHLCV, 2000-01-03 → 2026-04-09 (6,583 sessions, 4.62M bars after dedup), US/Eastern bar-start timestamps, validated against official closing prints (max observed deviation on normal days ≤ $0.08, attributable to 4:00 auction vs last continuous trade).
**Verdict up front (executive summary):**

> The tournament winner — volatility-gated late-day index momentum ("SPHINX-LHM") — was frozen after training (2003-2014, +6.9 bps/trade net, t = 2.86) and validation (2015-2020, +1.7 bps net, t = 0.48), supported by a 2008-2020 walk-forward (+3.3 bps net, t = 2.58, PF 1.31, Sharpe 1.12). **It then FAILED its single locked out-of-sample test (2021-01 → 2026-04: −0.18 bps/trade, t = −0.09, PF 0.985).** Per the pre-registered protocol, the strategy is **NOT approved for live capital**. The implementation is complete, deterministic and fully tested, and is authorized for **paper trading only**, as forward paper results are now the only uncontaminated out-of-sample data available. No candidate in the tournament produced a robust, statistically significant post-cost edge in the most recent five years on SPY. That is the honest result of a skeptical process, and it is reported as such rather than laundered by another round of in-sample iteration.

Nothing in this report claims guaranteed profitability. Every number below is net of modeled costs unless labeled gross.

---

## 1. Research methodology

1. **Pre-registered data splits, fixed before any strategy was evaluated:**
   - Burn-in (indicator warm-up only): 2000–2002
   - TRAIN (in-sample): 2003-01-02 → 2014-12-31 (3,000 valid sessions)
   - VALIDATION: 2015-01-02 → 2020-12-31 (1,478 valid sessions)
   - FINAL TEST (locked): 2021-01-04 → 2026-04-09 — **touched exactly once**, after the full spec was frozen (`config/strategy.json`, `docs/02_STRATEGY_SPEC.md`).
2. **One shared engine** (`src/sphinx/`) for research and production: identical fill rules, cost model and metrics, eliminating research/implementation drift (verified by `tests/test_fidelity.py`).
3. **Conservative execution model** on 1-minute bars: stops assumed to fill before targets when both are touchable in the same bar; gap-throughs fill at the bar open; stop fills carry an extra adverse $0.01/share.
4. **Cost model (base):** $0.0035 commission + $0.005 half-spread + $0.005 slippage = **$0.0135/share/side** ($0.027 round trip); stress tests at 2× and 3× the market-cost component. SPY has quoted 1¢ spreads essentially all day, so this is deliberately on the punitive side for the 15:30–16:00 window (and the MOC auction exit in practice pays no spread).
5. **Statistics:** per-trade expectancy in basis points of entry price (scale-free across 26 years), per-trade t-statistics, profit factor, daily-return Sharpe, compounded max drawdown, Monte-Carlo trade resampling (2,000 paths) for drawdown/streak distributions.
6. **Anti-overfit protocol:** full-grid parameter maps (reject spikes, require plateaus), yearly stability tables, expanding-window walk-forward with parameters chosen only from past data, and a single-shot locked test with results reported regardless of outcome.

### Evaluation-count ledger (multiple-testing honesty)
- TRAIN: unlimited exploration (documented grids: 9 C1 + 18 C2 + 8 C4 + 12 C6 + 20 C5 + 9 vol-threshold configs).
- VALIDATION: 2 protocol passes (pass 1: 9 pre-committed C5 configs + cost stress; pass 2: the pre-specified single-parameter vol filter sweep for confirmation).
- FINAL TEST: exactly 1 pass, after freeze. No rule or parameter was modified afterward.

---

## 2. The 20 critical questions

**Q1 — What market should be traded?**
Candidates compared: US index ETFs (SPY/QQQ), index futures (ES/NQ/MES), large-cap single names, small caps, FX majors, crypto. Decision matrix (liquidity, spread, slippage, data quality/availability, automation, opportunity frequency, scalability):
- **SPY** won as the *research* vehicle: tightest spread relative to volatility of any equity instrument (1¢ on ~$500), enormous depth, 26 years of verifiable 1-minute data available to this project, no survivorship issues, clean session structure. Production can map 1:1 to **ES/MES futures** (better cost/tax/leverage profile, no PDT constraint; ES half-tick ≈ 0.6 bps vs SPY ≈ 0.1 bp — cost mapping documented in the spec).
- Small caps rejected (spread/borrow/data), FX rejected (no centralized tape, session ambiguity, weaker documented intraday anomalies net of spread), single names rejected for v1 (idiosyncratic halt/news risk; the cross-sectional relative-volume ORB of Zarattini-Barbon-Aziz 2024 requires full-universe intraday data we could not source at research grade).

**Q2 — Is the edge momentum, mean reversion, breakout, or something else?**
All families were tested head-to-head on identical data, costs and engine (Section 3). Result: opening-range breakouts and VWAP-band mean reversion are **negative after costs on SPY across their entire parameter grids**; overnight-gap fading is positive but statistically weak (t ≤ 1.24); the only family with a persistent, mechanism-backed, statistically significant training edge was **late-day continuation of the day's move (intraday time-series momentum)** — and even it decayed materially after ~2014.

**Q3 — What is the actual source of the edge?**
For the surviving candidate: (a) **hedging demand** — option market-makers' gamma hedging and leveraged-ETF daily rebalancing are mechanically executed near the close *in the direction of the day's move* (Baltussen, Da, Lammers, Martens 2021); (b) **infrequent rebalancing/late-informed flow** (Gao, Han, Li, Zhou, JFE 2018); both scale with volatility, matching the observed regime dependence. For rejected families: ORB's premise (opening imbalance persistence) demonstrably does not clear costs on a macro ETF — consistent with the independent replication of the QQQ ORB paper showing break-even at ~2.2¢/share slippage; gap-fade's mechanism (overnight liquidity premium) exists but is too weak per event after costs.

**Q4 — Does the edge survive costs?** Tested at 1×/2×/3× market costs.
TRAIN: +6.9 bps (1×) → +4.4 (2×) → +1.9 (3×) for the frozen config (per-trade cost ≈ 0.9 bps at $400 SPY; at 2003 price levels ≈ 2.7 bps).
TEST: −0.2 bps at 1× — the strategy fails **before** costs are even stressed. Reported honestly.

**Q5 — Does the strategy work out of sample?** Partially, then no.
Walk-forward 2008-2020 (parameters always chosen from past-only data): +3.31 bps, t = 2.58. VALIDATION (2015-2020, frozen rules): +1.7 bps, t = 0.48 (weak). LOCKED TEST (2021-2026): −0.18 bps, t = −0.09 → **fail**. This is the central finding.

**Q6 — Is the strategy overfit?** The design minimized it: 4 substantive parameters (predictor agreement, magnitude floor, vol gate, entry/exit times fixed by mechanism), monotone parameter response surfaces (no isolated optima — see grids in `research/outputs/`), walk-forward reselection stability (the same predictor was chosen 13/13 years). The final-test failure pattern (mechanism regime change, Section 6) looks like **non-stationarity, not classic overfitting**: the walk-forward held up through 2020 and the collapse is concentrated in 2024-2025.

**Q7 — What regimes help/hurt?** Uniform across TRAIN and VAL: high prior-20d realized volatility and below-200SMA markets carry essentially all of the edge (TRAIN: high-vol tercile +9.7 bps vs low-vol +0.8; below-SMA +14.4 vs above −0.3. VAL: +2.8/−0.2 and +6.4/−1.1). This motivated the single pre-specified regime filter (rv20 ≥ 15% annualized), whose threshold response was monotone on TRAIN (no cherry-picked spike). In TEST the pattern **inverted** in 2025 (high-vol trades −4.6 bps) — evidence of a structural change near the close, not merely noise.

**Q8 — Best time of day?** Tested entries 15:00 vs 15:30 and (for other families) open-anchored windows. The 15:30→16:00 window dominated for the momentum family (mechanism-consistent); morning windows carried all the negative expectancy for breakout families. The system trades only 15:30:00→16:00 and is otherwise flat.

**Q9 — Minimum signal quality?** Each conditioning variable had to earn its place on TRAIN with a monotone effect: direction agreement of r_early and r_od (+1.6 bps vs single predictor), magnitude floor ≥ 0.10×ATR% (+1.1 bps), vol gate (+3.2 bps at ≥0.15). Variables tested and **rejected** for no measurable value or worse: profit targets, tight stops (they truncate the effect: stop@0.5×ATR cut expectancy from 2.6 to 1.5 bps on TRAIN), trend-side-only filters (subsumed by vol gate), 15:00 entry.

**Q10/Q11/Q12/Q13 — Entries/stops/exits/R:R.** Fully objective; see the frozen spec. Notable evidence: for this effect the optimal exit is the terminal auction (MOC), a *time* exit — fixed R-multiple targets strictly reduced expectancy (the distribution is a drift, not a barrier phenomenon). The only stop is a 2.0×ATR14 disaster stop, a safety control whose measured cost is ≈1.0 bps/trade on TRAIN (mostly 2008 gap minutes) and whose trigger rate is 0.2%.

**Q14 — How much data is enough?** Totals: 3,000 TRAIN sessions → 645 trades; VAL 294; walk-forward OOS 1,346; TEST 277. 95% CI on TEST expectancy: −0.18 ± 3.82 bps — wide, but centered at zero; the TRAIN–TEST expectancy gap (6.9 → −0.2) exceeds what sampling noise alone comfortably explains given the regime decomposition.

**Q15 — Bad-condition behavior.** Monte-Carlo (trade resampling, sized): TRAIN dd_p50 −6.3%, dd_p95 −10.4%, dd_p99 −12.3%, max losing streak p95 = 12; realized sized max drawdowns: TRAIN −6.3%, VAL −7.2%, TEST −5.5%. Worst single trades ≈ −1.6R of the daily risk budget (0.5%), i.e., ≈ −0.8% equity days. Survival was designed in (vol-scaled sizing, leverage cap 2×, daily/rolling lockouts).

**Q16 — News/events dependence.** The strategy holds through the close on high-vol days (FOMC afternoons included). Event-day PnL is part of the mechanism (hedging flows are largest then), so no discretionary event filter was added; the objective vol gate plus the 20% gap data-sanity bound are the only event-adjacent rules. This is documented as a conscious, testable choice.

**Q17 — Realistic execution?** Two marketable orders per day in the single most liquid half-hour of the world's most liquid equity, plus an MOC auction exit; sub-second latency is irrelevant at 1-minute decision granularity; fill probability ≈ 1 at the modeled prices; partial fills are a non-issue at retail-institutional size (impact analysis says <$5M notional/trade is negligible vs ~$300M/minute SPY turnover in that window).

**Q18 — Does complexity help?** SIMPLE (agreement only) vs ENHANCED (+magnitude floor, +vol gate): the two filters improved TRAIN t-stat from 3.2 → 2.9 (fewer trades, larger edge) and VAL expectancy from +0.4 → +1.7 bps. Everything else tested was removed. Final rule count: 5 gates, 1 entry, 2 exits.

**Q19 — Parameter stability?** rv20 threshold: expectancy monotone from 3.7→17.9 bps as threshold rises 0→0.30 on TRAIN and 0.2→15.1 bps on VAL — a stable tradeoff surface, mid-plateau chosen (0.15), not the argmax. Magnitude floor 0→0.25: monotone. Entry 15:00 vs 15:30: both positive. No isolated magic parameter exists.

**Q20 — Final objective function.** Composite: locked-test expectancy>0 (weight: gating), walk-forward t-stat, PF, Sharpe, maxDD, parameter plateau quality, cost-stress survival, trade count, executability; penalties for complexity and fragility. The winner led every in-sample and walk-forward component — and was still **failed** on the gating criterion when the locked test came back flat. The objective function was applied as designed.

---

## 3. Candidate tournament (all net of base costs, identical engine)

TRAIN 2003-2014, 3,000 sessions. Full scorecards in `research/outputs/scorecards_train.csv`; grids in `grid_train_*.csv`.

| Candidate | Rules (summary) | Trades | Win% | Expectancy | t | PF | Sharpe | Verdict |
|---|---|---|---|---|---|---|---|---|
| C1 ORB-5m immediate (Zarattini/Aziz style) | 1st 5-min candle direction, enter 09:35, stop = opposite OR extreme, EOD | 2,912 | 16.2% | **−0.37 bps** | −0.39 | 0.97 | −0.38 | Rejected: negative after costs; whole grid (OR 5/15/30 × target none/5R/10R) negative |
| C2 ORB breakout (stop-entry beyond range) | Break of 5/15/30-min range, stop = far side, EOD | 2,997 | 21.7% | **−1.25 to −2.35 bps** | ≤ −1.2 | 0.91–0.93 | <0 | Rejected: negative across all 18 grid cells |
| C4 VWAP-band mean reversion | Fade ≥a×ATR deviation from session VWAP, exit at VWAP/stop/15:55 | 807 | 48.1% | **−1.4 to −2.5 bps** | <0 | 0.90–0.94 | <0 | Rejected: negative across grid (only a 38-trade cell positive = noise) |
| C6 Overnight gap fade | Fade 0.3–2.0×ATR gaps toward prior close, stop 1×gap, EOD | 1,146 | 51.2% | +3.00 bps | 1.24 | 1.10 | 0.35 | Rejected: insufficient statistical confidence, unstable neighborhood |
| C5 Intraday momentum, unconditional | sign(r 09:30–10:00) = sign(r to 15:30) → trade 15:30→close | 2,152 | 52.3% | +2.59 bps | 3.21 | 1.28 | 1.10 | Promoted, then **rejected after VAL collapse** (2015-20: +0.37 bps, t=0.34) |
| **C5-gated (winner) “SPHINX-LHM”** | + magnitude ≥0.10×ATR%, + rv20 ≥ 0.15 | 645 | 56.4% | **+6.86 bps** | 2.86 | 1.49 | 1.57 | Frozen → **failed locked test** |

Key cross-checks against public research: our C1 result on SPY is consistent with the independent replication of the QQQ ORB paper (gross edge ~$0.07/share living inside a ~2.2¢ slippage break-even; SPY’s open-drive continuation is weaker than QQQ’s); our C5 result reproduces Gao-Han-Li-Zhou (1993-2013 strong; decays post-publication) and the Baltussen et al. vol-dependence.

### Walk-forward (expanding window, yearly re-selection from past data only, 2008-2020)
Selected parameters were stable (predictor “both” 13/13 years; magnitude floor drifted 0.10→0.25; vol gate chosen in crisis-adjacent years). Concatenated OOS: **1,346 trades, +3.31 bps, t = 2.58, PF 1.31, Sharpe 1.12, maxDD −7.2%** (`research/outputs/walkforward_picks.csv`).

---

## 4. Why the winner was selected

1. Only family positive after costs on TRAIN with t > 2.5 and a plateau (not a point) in parameter space.
2. Only family with a documented, peer-reviewed causal mechanism (JFE 2018; Baltussen et al. 2021) whose conditioning variable (volatility) matched our independent regime decomposition *before* we looked at VAL.
3. Survived 2× cost stress on TRAIN and a genuine 13-year walk-forward.
4. Best executability profile of all candidates (2 marketable orders/day in the deepest liquidity window + auction exit).
5. VAL was weak (+1.7 bps, t = 0.48) — this was documented at freeze time as the main risk, with the locked test as arbiter. The arbiter said no.

## 5. Locked final test — reported as it fell

Frozen production path, 2021-01-04 → 2026-04-09 (1,322 sessions):

| Metric | Value |
|---|---|
| Trades | 277 (53.5/yr; participation 21%) |
| Win rate | 52.0% |
| Avg win / avg loss | +23.0 / −25.3 bps |
| **Expectancy** | **−0.18 bps (t = −0.09)** |
| Profit factor | 0.985 |
| Sized equity multiple | 1.015 (≈ 0.09%/yr) |
| Max DD (sized) | −5.5% |
| Cost stress 2×/3× | −0.64 / −1.10 bps |
| By year | 2021 +2.1, 2022 +1.0, 2023 +8.0, 2024 −2.4, **2025 −10.7**, 2026 +1.3 bps |
| No-trade census | 811 low-vol, 147 no-agreement, 83 move-too-small, 2 half-day, 2 data-fail |

## 6. Failure analysis

- **Where it died:** 2025 (−533 bps summed over 50 trades, win rate 38%), i.e., precisely the high-volatility episodes the filter selects for. 2021-2023 were mildly positive (+508 bps summed).
- **Most plausible cause — mechanism inversion, not noise:** the rise of 0DTE index options (>50% of SPX option volume since 2023) restructured dealer gamma near the close; when dealers are net **long** gamma they hedge *against* the day's move, producing end-of-day **reversal** instead of continuation (cf. Baltussen-Da-Soebhag, "End-of-Day Reversal"). Our TEST regime table shows exactly this signature: high-vol trades flipped from the best bucket (TRAIN +14.0 bps) to the worst (TEST −4.6 bps).
- **What it is not:** a data artifact (2025 sessions validate cleanly; per-trade losses are smooth drifts, not bad prints), or a cost artifact (fails gross too in 2025), or classic overfit (walk-forward was honest and stable through 2020).
- **Consecutive-loss / tail behavior in TEST** stayed within Monte-Carlo bounds (max streak 10 vs p95 = 10; maxDD −5.5% vs p99 −3.5% sized — the DD exceedance is itself evidence of distribution shift).

## 7. Decision and next steps (pre-committed logic applied)

1. **DO NOT DEPLOY to live capital.** The locked test is a fail under the pre-registered gating criterion.
2. The frozen strategy may run in **paper mode only** (`scripts/paper_trade.py`), because forward data is the only remaining uncontaminated out-of-sample set. Re-evaluation gate: ≥ 150 paper trades AND per-trade t > 2 before any live-capital discussion.
3. 2021-2026 is a **burned dataset**: any revised strategy tested against it is in-sample by construction. Honest future research paths: (a) the sign-flip hypothesis (end-of-day *reversal* conditional on dealer-gamma proxies) — requires options positioning data, and 2021+ can only serve as its training set with forward validation; (b) the cross-sectional relative-volume ORB (Zarattini-Barbon-Aziz 2024) — requires full-universe stock-level intraday data; (c) ES/NQ futures replication of C5 with exchange-grade data.
4. All infrastructure delivered here (deterministic engine, fidelity-tested, risk-gated) is strategy-agnostic and reusable for those paths.

## 8. References

- Gao, Han, Li, Zhou (2018), *Market Intraday Momentum*, Journal of Financial Economics 129(2).
- Baltussen, Da, Lammers, Martens (2021), *Hedging demand and market intraday momentum*, JFE.
- Baltussen, Da, Soebhag (2024), *End-of-Day Reversal*, working paper.
- Zarattini, Aziz (2023/2025), *Can Day Trading Really Be Profitable?* SSRN 4416622 — plus the independent public replication showing ~2.2¢/share slippage break-even on QQQ.
- Zarattini, Barbon, Aziz (2024), *A Profitable Day Trading Strategy for the U.S. Equity Market* (relative-volume-filtered ORB).
- Independent ORB backtests on S&P futures/ETFs (QuantifiedStrategies et al.) reporting post-cost decay of unfiltered ORB.
