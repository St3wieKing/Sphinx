#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TOKEN_FILE="${SPHINX_TOKEN_FILE:-artifacts/secrets/tradingview_webhook_token}"
mkdir -p "$(dirname "$TOKEN_FILE")" artifacts/webhooks
if [[ ! -s "$TOKEN_FILE" ]]; then
  umask 077
  python - <<'PY' > "$TOKEN_FILE"
import secrets
print(secrets.token_urlsafe(32))
PY
fi
chmod 600 "$TOKEN_FILE"
export SPHINX_WEBHOOK_TOKEN="$(cat "$TOKEN_FILE")"

args=(dashboard --host "${SPHINX_HOST:-0.0.0.0}" --port "${SPHINX_PORT:-8000}")
[[ -n "${SPHINX_NQ_DATA:-}" ]] && args+=(--nq-data "$SPHINX_NQ_DATA")
[[ -n "${SPHINX_MNQ_DATA:-}" ]] && args+=(--mnq-data "$SPHINX_MNQ_DATA")
[[ -n "${SPHINX_DEEP_REPORT:-}" ]] && args+=(--deep-report "$SPHINX_DEEP_REPORT")
args+=(--webhook-log "${SPHINX_WEBHOOK_LOG:-artifacts/webhooks/tradingview-alerts.jsonl}")

echo "Sphinx paper signal intake is starting."
echo "Webhook token is stored locally at: $TOKEN_FILE"
echo "No orders will be routed."
exec sphinx "${args[@]}"
