# SPHINX-LHM v1.0.0 — Complete Strategy Specification (FROZEN)

Frozen: 2026-08-17, after TRAIN selection + VAL confirmation + walk-forward, **before** the single locked test.
Status after locked test: **NOT APPROVED FOR LIVE CAPITAL — PAPER TRADING ONLY** (see `docs/01_RESEARCH_REPORT.md` §5–7).
Machine-readable parameters: `config/strategy.json`. Nothing in this document may be changed without a new research cycle and a new, uncontaminated validation set.

Time convention: minutes since midnight, US/Eastern (09:30 = 570, 15:30 = 930, 16:00 = 960). All prices in USD.

---

## A. Strategy identity

| Field | Value |
|---|---|
| Name | SPHINX-LHM (Late-day Hedging-demand Momentum) |
| Core hypothesis | On elevated-volatility days, option market-maker gamma hedging and leveraged-ETF rebalancing execute near the close in the direction of the day's move, creating last-half-hour continuation (Gao et al. 2018; Baltussen et al. 2021). |
| Market | US large-cap equity index |
| Instrument | SPY (production alternative: MES/ES with the documented cost mapping) |
| Timeframe | 1-minute bars for calculation; one decision per day |
| Session | RTH 09:30–16:00 ET only; never holds overnight |
| Direction | Long and short, symmetric |
| Frequency | ≈ 50–55 trades/year (participation ≈ 20% of sessions) |

## B. Data requirements

- DATA-01: 1-minute OHLCV bars, RTH, **bar-start** timestamps, US/Eastern, consolidated tape.
- DATA-02: ≥ 200 prior sessions of daily closes before the first tradable day (for SMA200 warm-up; the strategy itself needs prev_close, ATR14, RV20).
- DATA-03: session calendar with early-close flags (early closes are detected as last bar before 14:00 when no calendar is available).
- DATA-04: clock synchronized to NTP within ±1 s; bars accepted only if staleness ≤ 120 s (live).
- DATA-05: no bid/ask feed required (cost model covers spread); volume required only for data sanity.

## C. Market filters (all must pass; else NO_TRADE)

| Rule | Definition |
|---|---|
| FILT-01 | Session data valid: ≥ 370 one-minute RTH bars expected for a full day (≥ 190 for half day) *counted at evaluation time as: all bars 09:30–15:29 present with ≤ 5 missing*; prev_close, ATR14, RV20 all available; \|overnight gap\| < 20%. Any failure ⇒ NO_TRADE (DATA_VALIDATION_FAILURE). |
| FILT-02 | Not an early-close session. |
| FILT-03 | RV20 ≥ 0.15, where RV20 = stdev of the prior 20 close-to-close simple returns × √252 (strictly prior sessions). |

## D. Setup detection (calculations CALC-01..05, rules SETUP-01..02)

- CALC-01 `prev_close` = last RTH 1-min close of the previous valid session.
- CALC-02 `atr14` = mean over the prior 14 sessions of TR_d = max(H_d, C_{d-1}) − min(L_d, C_{d-1}) (strictly prior).
- CALC-03 `rv20` as in FILT-03.
- CALC-04 `r_early` = close of the last 1-min bar with start-time < 10:00, divided by prev_close, minus 1.
- CALC-05 `r_od` = close of the last 1-min bar with start-time < 15:30, divided by prev_close, minus 1.
- SETUP-01: sign(r_early) = sign(r_od) ≠ 0.
- SETUP-02: min(|r_early|, |r_od|) ≥ 0.10 × (atr14 / prev_close).
- Setup evaluation happens exactly once per session, at 15:30:00. There is no earlier arming, no re-evaluation, and no expiry beyond the session itself. Invalidation = any FILT/SETUP condition false at 15:30:00.

## E. Entry

| Rule | Definition |
|---|---|
| ENTRY-01 | Direction = sign(r_early). Submit at 15:30:00 a **marketable limit** at decision price ± 5 bps (buy: +5 bps cap; sell: −5 bps cap), day-TIF. Decision price = CALC-05 reference close. |
| ENTRY-02 (timeout) | If not filled by 15:31:00 ⇒ cancel. The missed entry is **never chased**; session becomes SESSION_LOCKED. |
| ENTRY-03 (dup guard) | Exactly one entry order per (strategy, session, signal); duplicates rejected by the order manager. |

## F. Stop loss (safety control, not alpha)

- STOP-01: disaster stop at entry_reference ∓ 2.0 × atr14 (long: below; short: above), submitted immediately after the entry fill, OCO with the MOC exit. Measured trigger rate 0.2% of trades; measured cost of carrying this control ≈ 1.0 bps/trade (TRAIN). It exists to bound intra-window catastrophe (halt/flash event), corresponds to thesis invalidation ("the day's move has violently reversed"), and MUST NOT be tightened, widened or trailed.
- Max theoretical loss per trade if the stop gaps: bounded by sizing (Section H) — at the 2× leverage cap a 2×ATR adverse move ≈ 2 × risk budget ≈ 1.0–1.6% of equity; Monte-Carlo p99 sized drawdown −12.3% (TRAIN), −3.5% (TEST distribution).

## G. Profit exit

- EXIT-01: **Market-on-Close** order for the full position, submitted at entry fill (target the 16:00:00 closing auction). Backtest proxy: last RTH 1-min close.
- No profit target (tested: targets strictly reduced expectancy). No partials. No trailing. No breakeven moves. If the MOC order is rejected, fall back to a marketable order at 15:59:00 (EXEC safety, same economic intent).

## H. Position sizing (SIZE-01)

```
atr_frac      = atr14 / prev_close
notional_frac = min( leverage_cap,  risk_budget_frac / (risk_proxy_atr_mult × atr_frac) )
shares        = floor( equity × notional_frac / entry_price )
```
risk_budget_frac = 0.005 (0.5% of equity per trade), risk_proxy_atr_mult = 0.30 (conservative 30-minute adverse-move proxy), leverage_cap = 2.0. Sizing never uses signal "confidence". Equity = end-of-prior-day account equity.

## I. No-trade conditions (must remain flat)

1. Any FILT-01/02/03 failure (data invalid, half day, low vol).
2. SETUP-01 or SETUP-02 false.
3. RiskState locked: daily loss > 1.5% (RISK-01); rolling-20-trade loss > 6% ⇒ hard lock pending human review (RISK-02); ≥ 3 consecutive data failures (RISK-04).
4. Entry not filled by 15:31:00 (ENTRY-02).
5. Position/data state indeterminate (POSITION_MISMATCH or stale data ⇒ no NEW positions; existing position still managed by STOP-01/EXIT-01).
6. Instrument halted at 15:30:00.

## J. Failure modes

| Event | Behavior |
|---|---|
| Consecutive losses | No behavioral change until RISK-02 threshold (−6% over 20 trades) ⇒ hard lock, paper mode, human review. Expected streaks: p95 = 12 losers (MC). |
| Data feed fails pre-15:30 | FILT-01 fails ⇒ flat day, DATA_FAILURE alert. |
| Data fails in-position | Position managed only by resting STOP-01 + EXIT-01 (both already at the exchange); no new decisions. |
| Entry rejected/unfilled | ENTRY-02: cancel, locked, alert EXECUTION_FAILURE. |
| Slippage > 5 bps vs decision price | ABNORMAL_SLIPPAGE alert; trade continues under normal exits; if 3 occurrences in 20 trades ⇒ human review of cost model. |
| Volatility abnormal (circuit breaker / LULD) | If halted at 15:30 ⇒ no entry. If halted in-position ⇒ orders remain; MOC participates in reopening/closing auction per exchange rules. |
| Broker/connectivity loss in-position | STOP-01 and EXIT-01 are resting server-side orders — the position self-liquidates by 16:00 without the strategy process. |

## K. Parameters and allowed ranges (sensitivity-mapped)

| Parameter | Frozen | Tested neighborhood (all viable on TRAIN) |
|---|---|---|
| early_mark_time | 10:00 | fixed by construct (literature: first half-hour) |
| signal/entry time | 15:30 | 15:00 also positive (+3.7 bps TRAIN) |
| min_move_frac_atr | 0.10 | 0.05–0.25 monotone plateau |
| rv20_min | 0.15 | 0.10–0.25 monotone plateau |
| disaster_stop_atr_mult | 2.0 | 1.5–3.0 (safety-only; larger = cheaper carry, worse tail) |
| risk_budget_frac | 0.005 | 0.0025–0.01 (linear risk scaling) |
| risk_proxy_atr_mult | 0.30 | 0.25–0.40 |
| leverage_cap | 2.0 | 1.0–4.0 (4.0 matches the ORB papers; 2.0 chosen for survival) |
| entry timeout | 60 s | 30–120 s |
| max_entry_slippage_bps | 5 | 3–10 |

## L. Pseudocode (complete decision path)

```
each session d:
    state = WAITING_FOR_SETUP
    refs  = {prev_close, atr14, rv20} from prior sessions        # CALC-01..03
    if not data_valid(d) or is_half_day(d):        NO_TRADE      # FILT-01/02
    if rv20 < 0.15:                                NO_TRADE      # FILT-03
    at 15:30:00:
        r1  = last_close_before(10:00) / prev_close - 1          # CALC-04
        rod = last_close_before(15:30) / prev_close - 1          # CALC-05
        if sign(r1) != sign(rod) or sign(r1) == 0: NO_TRADE      # SETUP-01
        if min(|r1|,|rod|) < 0.10*atr14/prev_close: NO_TRADE     # SETUP-02
        if not risk.can_trade():                   NO_TRADE      # RISK-*
        dir   = sign(r1)
        px    = last_close_before(15:30)
        qty   = floor(equity * min(2.0, 0.005/(0.30*atr14/prev_close)) / px)   # SIZE-01
        send marketable_limit(dir, qty, cap=px*(1+dir*5bps))     # ENTRY-01
        if unfilled by 15:31:00: cancel; LOCKED                  # ENTRY-02
        on fill: send OCO { stop at px_fill -dir*2.0*atr14,      # STOP-01
                            MOC for 16:00 auction }              # EXIT-01
    after exit: log full audit trail; update risk state
```

## M. Cost assumptions (modeled)

$0.0035/share commission + $0.005 half-spread + $0.005 slippage per side; stop fills +$0.01 adverse; stress 2×/3× on the market-cost component. ES/MES mapping: half-tick 0.125 index pts ≈ 0.19 bps + ~$0.62/contract commission ≈ 0.05 bps — futures execution is cheaper than the modeled ETF costs at every tested size.
