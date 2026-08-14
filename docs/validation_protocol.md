# Deliverable 5 — Backtest and Validation Protocol

## Dataset qualification

Use individual NQ contracts with exchange-session timestamps whenever possible. If a continuous series is used, preserve a manifest containing vendor, raw contract files, rollover rule, adjustment method, timezone, holidays/early closes, and SHA-256 hashes. Do not mix adjusted signal prices with unadjusted execution/tick values.

Minimum recommended coverage is several years of 2-minute or finer data spanning trending, ranging, high-volatility, and low-volatility periods. The current configured minimum of 100 bars/partition is only a software guard and is **not** a statistical sufficiency claim.

## Data freeze and split

1. Normalize once into the documented CSV contract.
2. Hash normalized data.
3. Split strictly in time: 60% development, 20% validation, 20% holdout.
4. Use development for implementation and bounded parameter-region studies.
5. Use validation only for predeclared experiment decisions.
6. Set `strategy_frozen=true` only after code, parameters, costs, metrics, and exclusions are fixed.
7. Open holdout once with both config freeze and `--allow-holdout`.
8. Do not tune after holdout. If changed, acquire a new untouched period.

The CLI intentionally has no `all` partition.

## Leakage checklist

- [ ] Bars are completed at event time.
- [ ] Pivot `confirmed_at`, not `occurred_at`, controls availability.
- [ ] HTF aggregates appear only after bucket completion.
- [ ] Consolidation and ATR end at `t-1` for a breakout at `t`.
- [ ] Evolving midpoint is known before its trigger bar.
- [ ] Close confirmation fills no earlier than the next bar.
- [ ] ES and NQ bars are synchronized without forward-fill across missing data.
- [ ] Session/DST conversion uses IANA timezone data.
- [ ] Rollover decisions are point-in-time and fixed before testing.
- [ ] News calendars, if added, use release schedules available at trade time.
- [ ] Holdout remains inaccessible during optimization.

## Fill scenarios

### Optimistic (diagnostic upper bound)

- 0.5 tick spread;
- no slippage;
- base fees;
- same conservative OHLC sequencing.

### Base

- 1 tick spread;
- 1 tick slippage each fill;
- configured commissions and exchange fee;
- stop-first, no favorable entry-bar exit.

### Pessimistic

- at least 2 ticks spread;
- at least 2 ticks slippage each fill;
- 1.5× commission and 1.25× fee;
- at least one execution-bar delay;
- same adverse intrabar sequencing.

Reject the economic hypothesis if only optimistic fills work.

## Walk-forward and sensitivity

Use expanding development windows and fixed validation windows. For each parameter, predeclare a small meaningful grid. Report the whole surface and neighboring values. Compare trade overlap, sample size, expectancy, profit factor, maximum drawdown, and regime concentration. Do not select an isolated maximum.

## Statistical cautions

- Report confidence intervals/bootstrap distributions rather than a bare point estimate.
- Treat copied multi-account trades as one signal.
- Correct expectations for trying many variants; the experiment ledger is the minimum audit trail.
- Sharpe/Sortino on sparse intraday trade equity can be misleading; this implementation labels them daily and returns null when insufficient.
- Annualized return is withheld for samples under 30 days.
- Bar-level drawdown includes marked open positions, but OHLC cannot reconstruct exact intrabar equity path.

## Stress protocol

After validation, randomize:

- trade order;
- 10% missed trades (then sensitivity around it);
- 0–2 extra ticks per side;
- at least 25% greater historical costs;
- delayed entry scenario;
- risk settings 0.10%, 0.25%, 0.50% using a method documented before comparison.

Report probability of terminal loss, configured ruin-drawdown exceedance, drawdown percentiles, and losing streaks. Monte Carlo resamples history; it is not a forecast and does not generate unseen regimes.

## Commands

```bash
# Install in an isolated environment
python -m venv .venv
. .venv/bin/activate
python -m pip install -e .

sphinx validate-config --config config/baseline.json
sphinx inspect-data --data /path/to/nq_2m.csv

# Defaults to development
sphinx backtest --data /path/to/nq_2m.csv --partition development \
  --output artifacts/development.json

sphinx stress --data /path/to/nq_2m.csv --partition validation \
  --output artifacts/validation_stress.json

sphinx monte-carlo --data /path/to/nq_2m.csv --partition validation \
  --simulations 5000 --output artifacts/validation_mc.json

# Fails until research.strategy_frozen=true and explicit consent is present
sphinx backtest --data /path/to/nq_2m.csv --partition holdout --allow-holdout \
  --output artifacts/final_holdout.json
```
