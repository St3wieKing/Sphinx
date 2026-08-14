# Deliverable 3 — Complete Decision Pseudocode

```text
LOAD strict JSON configuration
ASSERT paper_only = true
LOAD timezone-aware, completed 2-minute OHLC bars
ASSERT timestamps strictly increase and OHLC invariants hold
SPLIT chronologically into 60% development / 20% validation / 20% holdout
LOCK holdout unless strategy is frozen and operator explicitly consents

INITIALIZE:
    state = IDLE
    causal ATR and market-structure engines
    liquidity map
    2m, 5m, 15m, 1h, 4h AOI engines
    causal HTF resamplers
    optional synchronized NQ/ES SMT engine
    paper broker with no position
    risk manager with closed equity and latched kill switches
    hash-chained audit log

FOR each completed execution bar t in strictly increasing time:

    DETERMINE configured-session membership in America/New_York

    IF a new session begins:
        reset trade count, daily equity anchor, loss streak, daily cooldown
        clear daily-loss kill only
        preserve critical/manual-review kills

    IF previous bar was in-session AND t is outside session AND position exists:
        force simulated close at previous completed in-session close
        apply adverse execution and fees
        record trade and risk outcome

    CHECK active-session data freshness
    IF stale:
        latch STALE_DATA

    IF an existing position is open and t is in-session:
        update MAE/MFE
        IF stop and any target are both spanned:
            execute stop first
        ELSE IF stop is spanned:
            fill stop (worse open if gapped) with adverse execution
        ELSE:
            IF integer partial exists AND target one is spanned:
                execute partial with costs
                move remainder stop to chart entry
                IF t also spans new break-even stop:
                    conservatively stop remainder
            IF target two is spanned and position remains:
                execute remainder with costs
        IF trade closed:
            update closed equity, peak, daily P&L, loss streak, cooldown
            append complete hash-chained trade record
            state = COOLDOWN

    IF a delayed close-rejection order is due:
        IF outside session OR risk check fails:
            cancel/reject and log every failed condition
        ELSE:
            recalculate risk at t open
            size from equity, stop distance, tick value, spread, slippage, fees
            open at t open plus adverse execution
            permit same-bar stop but no same-bar favorable exit

    BEFORE updating strategy with t:
        save ATR[t-1] and all bars through t-1

    UPDATE on completed t only:
        ATR and causal pivot detector
        classify HH/HL/LH/LL/equal levels
        detect close-based BOS/MSS proxy
        update existing liquidity levels
        add newly confirmed pivots only after current touches are processed
        update 2m FVG/IFVG zones
        feed t to each causal HTF resampler
        IF a prior HTF bucket becomes complete:
            expose it and update that timeframe's AOIs
        IF synchronized ES[t] exists:
            update optional SMT proxy

    IF outside session:
        state = IDLE unless position/critical disable is active
        CONTINUE

    IF any kill switch active:
        state = DISABLED
        cancel pending entry
        optionally flatten paper position
        log alert and CONTINUE

    IF warmup incomplete:
        log no-trade reason and CONTINUE

    SWITCH state:

        IDLE / SESSION_INITIALIZATION:
            initialize confirmed levels
            state = WAITING_FOR_LOCATION

        COOLDOWN:
            decrement setup cooldown bars
            preserve risk-manager time cooldown
            when elapsed: state = WAITING_FOR_LOCATION

        WAITING_FOR_LOCATION:
            range = high/low of exactly N bars ending t-1
            consolidation_valid = range_width <= ATR[t-1] × threshold
            bullish_break =
                close[t] > range_high + tick_buffer
                AND body[t] >= ATR[t-1] × displacement_threshold
            bearish_break = inverse

            IF exactly one directional break:
                direction = break direction
                origin = range_low for long, range_high for short
                extreme = high[t] for long, low[t] for short
                save breakout timestamp/body/ATR
                state = TRACKING_IMPULSE
                log transition and all inputs

        TRACKING_IMPULSE:
            increment elapsed bars
            IF elapsed > maximum:
                log expiration
                state = WAITING_FOR_LOCATION
                CONTINUE

            IF long closes below origin OR short closes above origin:
                log invalidation
                state = WAITING_FOR_LOCATION
                CONTINUE

            known_midpoint = (origin + extreme_known_before_t) / 2
            touch = t crosses known_midpoint within tolerance

            IF confirmation_mode = close_rejection:
                confirmation = touch AND directional body closes beyond midpoint
            ELSE:
                confirmation = touch

            IF confirmation:
                entry = known_midpoint
                    OR close[t] for close_rejection mode

                fixed_stop = entry ∓ 40 ticks
                pivotal_stop = origin ∓ one-tick buffer
                stop = pivotal if positive distance <= 40 ticks else fixed

                target_one = prior extreme
                candidate_liquidity = nearest active confirmed same-side level
                                      beyond target_one
                target_two = candidate price if available
                             else origin ± 1.66 × impulse width

                BUILD checklist:
                    session active
                    source sequence passed
                    price ordering valid
                    minimum R:R passed
                    optional HTF AOI passed if enabled
                    optional SMT passed if enabled
                    no kill/cooldown/trade-count/exposure failure
                    spread acceptable
                    risk supports >= one contract

                BUILD auditable signal with:
                    ID, direction, source labels, score,
                    passed and failed conditions,
                    entry, stop, targets, expected R:R, regime

                IF any condition fails:
                    log rejection
                    state = COOLDOWN
                ELSE IF close-rejection/delay configured:
                    queue for a future bar; state = ENTRY_READY
                ELSE:
                    size without score weighting
                    execute trigger-market with adverse spread/slippage
                    state = POSITION_OPEN
                    check same-bar stop only

            ELSE IF t extends in direction:
                update extreme only now, after t closes
                calculate new midpoint for t+1
                log extension

        ENTRY_READY:
            wait for due bar or cancellation; never backfill at observed price

        POSITION_OPEN:
            broker logic above is the only management path

        DISABLED:
            no new entries until permitted reset/review

    MARK open position to market using adverse hypothetical exit
    CHECK 1% daily limit and 5% peak-equity drawdown
    ON threshold breach:
        latch kill, cancel pending, disable entries, preserve logs, alert

AT end of data:
    cancel pending order
    force-close any simulated position at final bar close with costs
    compute gross and net metrics, trade/hour/direction/regime breakdowns
    write config fingerprint, decisions, fills, trades, equity, kills, metrics

RESEARCH LOOP:
    write one hypothesis and parameter delta to experiment ledger
    run development only
    if sample and neighboring parameters are stable, run validation
    reject development-only improvements or fragile/small-sample results
    freeze complete config before opening final holdout
    run final holdout once with explicit consent
    run optimistic/base/pessimistic execution and Monte Carlo stresses
    accept or reject; never silently mutate the frozen model
```
