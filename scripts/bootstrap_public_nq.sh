#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DESTINATION="${1:-artifacts}"
mkdir -p "$DESTINATION"

sphinx download-research-data \
  --dataset kaggle-nq-2022-2025 \
  --destination "$DESTINATION/external-data"

SOURCE="$(find "$DESTINATION/external-data" -type f -name 'Dataset_NQ_1min_2022_2025.csv' -print -quit)"
test -n "$SOURCE"

sphinx normalize-data \
  --source "$SOURCE" \
  --output "$DESTINATION/data/nq_2m.csv" \
  --symbol NQ \
  --source-timezone America/New_York \
  --source-interval-seconds 60 \
  --provenance-note "Public CC0 research starter; rollover construction unverified"

sphinx deep-backtest \
  --nq-data "$DESTINATION/data/nq_2m.csv" \
  --bootstrap-simulations 2000 \
  --output "$DESTINATION/deep_research.json"

echo "Research report: $DESTINATION/deep_research.json"
echo "The final 20% holdout remains locked."
