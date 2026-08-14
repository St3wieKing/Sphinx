# Sphinx Signal Desk Website

The website is a dependency-free paper/research dashboard served by the same Python package.

```bash
sphinx dashboard --host 0.0.0.0 --port 8000
```

Without data arguments it loads a visibly labelled deterministic synthetic engineering replay. Synthetic P&L is not market evidence.

With normalized private data:

```bash
sphinx dashboard \
  --host 0.0.0.0 \
  --port 8000 \
  --nq-data artifacts/data/nq_2m.csv \
  --mnq-data artifacts/data/mnq_2m.csv \
  --deep-report artifacts/deep_research.json
```

## Views

### Signal desk

- NQ/MNQ contract switch;
- data provenance mode and as-of timestamp;
- fresh `LONG`, `SHORT`, or `WAIT` state;
- entry, invalidation/stop, TP1, TP2, R:R, setup score, and regime;
- completed setup chart and levels;
- full passed-condition checklist;
- replay metrics after modeled costs and paper equity;
- clickable historical signal ledger.

`LONG` or `SHORT` means a signal occurred within two final completed bars in the loaded replay. `WAIT` means no fresh trigger. It is not a recommendation.

### Research

Displays the holdout lock, evidence sequence, NQ/MNQ non-independence warning, and loaded deep-report summary. Without a real report it explicitly states that profitability is undetermined.

### TradingView

Displays, copies, and downloads the Pine v6 indicator with installation and alert instructions.

## API

```text
GET /api/health
GET /api/overview
GET /api/instrument/NQ
GET /api/instrument/MNQ
GET /api/pine
```

There is no order endpoint. The server reads completed CSV bars at startup and does not claim a live exchange feed. Restart with an updated file for a new replay snapshot. A production paper feed should be implemented behind the existing `Bar` contract and retain stale-data/kill-switch checks.

## TradingView paper webhook intake

Start with a locally generated token and append-only hash-chained alert log:

```bash
scripts/start_paper_signal_desk.sh
```

The token is generated under `artifacts/secrets/` with restrictive permissions and is never committed. Configure the TradingView webhook URL on your HTTPS deployment as:

```text
https://YOUR_HOST/api/webhook/tradingview?token=YOUR_LOCAL_TOKEN
```

The Pine indicator's dynamic JSON payload is accepted only when:

- the token matches;
- side is `LONG` or `SHORT`;
- ticker identifies NQ or MNQ;
- entry, stop, TP1, and TP2 are finite positive numbers;
- directional price ordering is valid.

Accepted events return HTTP 202, receive an audit hash, and are stored with status `RECEIVED_NOT_ROUTED`. The endpoint cannot place or forward an order. Query receive-only status at `GET /api/webhooks`.
