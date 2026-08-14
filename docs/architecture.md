# Deliverable 4 — Software Architecture

## Design principles

1. **One strategy path:** backtest and paper replay use the same state machine, risk manager, and broker simulator.
2. **Completed bars only:** causal resampling and delayed pivot confirmation make availability explicit.
3. **Evidence labels:** source-derived, inferred, and experimental rules remain identifiable in signals and specifications.
4. **Risk before frequency:** score never controls size; hard constraints can return zero contracts or disable entries.
5. **Auditable:** every transition, rejection, fill, kill, config fingerprint, and result can enter a hash-chained JSONL log.
6. **Paper only:** there is no live broker implementation and configuration validation refuses `paper_only=false`.
7. **Dependency-light:** runtime uses Python 3.11 standard library so research behavior is inspectable and portable.

## Package map

```text
Sphinx/
├── config/
│   ├── baseline.json               # frozen-by-value runtime knobs
│   └── strategy.schema.json        # JSON Schema
├── spec/
│   └── strategy_spec.json          # evidence-labelled machine specification
├── data/
│   └── README.md                    # data contract/provenance requirements
├── docs/
│   ├── research_report.md
│   ├── strategy_specification.md
│   ├── pseudocode.md
│   ├── architecture.md
│   ├── research_results.md
│   └── validation_protocol.md
├── src/sphinx_bot/
│   ├── models.py                   # immutable shared contracts/enums
│   ├── config.py                   # strict loader, semantic checks, fingerprint
│   ├── cli.py                      # operator commands
│   ├── data/
│   │   ├── csv_feed.py             # ingestion, OHLC/order validation, hash
│   │   ├── importers.py            # public download, external normalization/manifests
│   │   ├── resample.py             # causal completed HTF aggregation
│   │   └── split.py                # 60/20/20 lock and walk-forward folds
│   ├── strategy/
│   │   ├── market_structure.py     # ATR, four pivot modes, BOS/MSS, regimes
│   │   ├── liquidity.py            # map, sweep, consume, scope, ranking
│   │   ├── areas_of_interest.py    # FVG, IFVG, mitigation, dealing range
│   │   ├── context.py              # optional synchronized NQ/ES SMT proxy
│   │   └── state_machine.py        # core 50% model and checklist signals
│   ├── risk/
│   │   └── manager.py              # sizing, limits, cooldown, kill latches
│   ├── execution/
│   │   ├── simulator.py            # conservative OHLC paper broker
│   │   └── paper_trader.py         # persistent autonomous CSV replay
│   ├── research/
│   │   ├── backtest.py             # event orchestrator
│   │   ├── metrics.py              # returns, expectancy, DD, groups
│   │   ├── stress.py               # optimistic/base/pessimistic fills
│   │   ├── monte_carlo.py          # order/miss/slippage/cost randomization
│   │   ├── experiments.py          # append-only hypothesis ledger
│   │   ├── synthetic.py            # engineering fixture, never evidence
│   │   └── deep.py                 # locked NQ/MNQ research suite
│   ├── web/
│   │   ├── server.py               # paper dashboard + read-only JSON API
│   │   └── static/                 # responsive Signal Desk and Pine copy
│   └── monitoring/
│       ├── audit.py                # SHA-256 chained JSONL
│       └── report.py               # explanatory daily paper reports
└── tests/
    ├── unit/
    └── integration/
```

## Runtime event flow

```text
CSV completed-bar feed
        │
        ├── data validation ── invalid → abort / INVALID_DATA
        │
        ▼
BacktestEngine / PaperTrader
        │
        ├── existing PaperBroker position → conservative exits/fills
        ├── RiskManager → marked equity and kill checks
        │
        ▼
ScrivStateMachine
        ├── MarketStructureEngine
        ├── LiquidityEngine
        ├── AOI engines (2m and causal HTFs)
        ├── optional SMT detector
        └── state transition + complete SetupPlan checklist
        │
        ▼
RiskManager.check_open
        ├── deny → auditable reason + cooldown/kill
        └── approve → quantity from stop/cost budget
                         │
                         ▼
                    PaperBroker
                         │
                         ├── Fill/Position/Trade
                         └── Audit + metrics + reports
```

## Module contracts

### Data

`Bar` requires an aware timestamp and valid OHLC. `read_bars` rejects malformed lines and non-increasing rows. `inspect_data` reports duplicate/order/interval/gap counts plus a deterministic SHA-256 content hash. It never fills gaps.

`CausalResampler.update` returns the previous aggregate only after a new bucket starts. It intentionally has no end-of-file `flush`, because file termination would not prove a live candle completed.

### Strategy

`MarketStructureEngine.update(bar)` returns a point-in-time `StructureSnapshot` and pivots first available on that bar. Pivot has separate `occurred_at` and `confirmed_at`.

`LiquidityEngine` owns level lifecycle and metadata. It updates already-known levels before adding pivots confirmed by the same bar, preventing retroactive touches.

`AreaOfInterestEngine` creates a three-candle FVG only on close of candle three. Inversion requires a later closing invalidation. Context zones are optional.

`ScrivStateMachine.on_bar` is the sole signal producer. A `SetupPlan` includes prices, checklist, failed conditions, evidence labels, score, target source, and regime. State transitions are explicit; there is no indicator vote that can bypass location and sequence.

### Risk

`RiskManager` maintains **closed equity** plus marked-equity checks. `position_size` computes loss per contract from stop distance and modeled costs, then floors to broker increments/caps. It does not accept a confidence input.

Daily loss unlocks only on the next configured session. Stale data, spread, repeated rejection, and account/drawdown failures are latched. Critical resets require an explicit operator method; maximum drawdown cannot be reset without a changed/reviewed risk configuration.

### Execution

`PaperBroker` supports one position, integer contracts, a real partial only when integer quantity allows, adverse spread/slippage each side, per-side fees, gap stops, and conservative same-bar sequencing. Gross chart P&L, execution cost, fees, and net P&L remain separate.

This OHLC simulator does not pretend to model queue position or depth. If order-book partial fills become material, replace it with a tick/order-book simulator behind the same `SetupPlan`/`Trade` contracts.

### Research

`BacktestEngine` is event-driven. The CLI defaults to development, forbids “all,” and requires both `strategy_frozen=true` and `--allow-holdout` for the holdout.

`stress.py` changes execution assumptions, not strategy logic. `monte_carlo.py` permutes observed trades, drops trades, and worsens costs/fills reproducibly. It cannot repair a weak or small historical sample.

`ExperimentLedger` requires an ID, hypothesis, reason, exact parameter delta, and config fingerprint. It refuses holdout results not marked as post-freeze.

### Monitoring

`AuditLogger` chains each canonical record to the prior SHA-256 hash. `verify-audit` detects alteration/reordering. This is tamper-evident, not a substitute for off-host immutable storage. Production paper operations should ship logs externally.

Daily Markdown reports cross-reference signal rationale and show gross/cost/net, MAE/MFE, and outcome. Alerts are written separately.

## Failure boundaries

- **CSV parser:** aborts before trading on schema/OHLC/order failure.
- **Strategy:** invalid timestamp moves state to disabled and logs reason.
- **Risk:** denied size never reaches broker.
- **Broker:** invalid/repeated orders count toward rejection kill.
- **Persistence:** a write failure should terminate paper operation; silent logging failure is unacceptable. (The current replay command is synchronous, so the exception propagates.)
- **No network adapter:** live feed staleness by wall clock is not claimed. The shipped feed detects timestamp gaps during replay.

## Extension interfaces

A real-time paper feed can yield the same `Bar` objects to the engine. A news filter should supply a point-in-time event calendar and add an explicit checklist result. Tick/order-book simulation can replace `PaperBroker`. None of those extensions should change the source evidence labels or unlock live funds automatically.
