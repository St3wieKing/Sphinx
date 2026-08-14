#!/usr/bin/env bash
# Rebuild the gitignored artifacts/ research data and reports from the
# operator's GitHub data repo. Use this after any environment reset or
# workspace loss. Nothing is committed from this script; the data repo
# (not the Sphinx repo) remains the source of truth for the raw CSV.
#
#   bash scripts/rebuild_local_artifacts.sh [DATA_REPO]
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DATA_REPO="${1:-https://github.com/St3wieKing/sphinx-market-data.git}"
ARCHIVE_SHA256="${ARCHIVE_SHA256:-8d3f157a422636e5b8dda51cc3a3d9209c50cb53f9b279d3e14b627ce59370dc}"
BOOTSTRAP_SIMULATIONS="${BOOTSTRAP_SIMULATIONS:-5000}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "[1/6] cloning data repo"
git clone --depth 1 "$DATA_REPO" "$TMP/mdata" >/dev/null 2>&1

echo "[2/6] verifying archive hash"
ACTUAL="$(sha256sum "$TMP/mdata/archive.zip" | cut -d' ' -f1)"
if [[ "$ACTUAL" != "$ARCHIVE_SHA256" ]]; then
  echo "hash mismatch: expected $ARCHIVE_SHA256 got $ACTUAL" >&2
  exit 1
fi

echo "[3/6] extracting and normalizing NQ"
mkdir -p artifacts/incoming artifacts/data
cp "$TMP/mdata/archive.zip" artifacts/incoming/
python3 - <<'PY'
import zipfile
zipfile.ZipFile("artifacts/incoming/archive.zip").extractall("artifacts/incoming")
PY
PYTHONPATH=src python -m sphinx_bot normalize-data \
  --source artifacts/incoming/Dataset_NQ_1min_2022_2025.csv \
  --output artifacts/data/nq_2m.csv \
  --symbol NQ \
  --source-timezone America/New_York \
  --source-interval-seconds 60 \
  --provenance-note "Kaggle CC0 public NQ 1-min dataset; rebuilt by scripts/rebuild_local_artifacts.sh"

echo "[4/6] creating MNQ modeled series (NOT independent MNQ evidence)"
python3 - <<'PY'
import csv, hashlib, json
from datetime import datetime, UTC
src, dst = "artifacts/data/nq_2m.csv", "artifacts/data/mnq_2m_modeled_from_nq.csv"
with open(src, newline="") as fin, open(dst, "w", newline="") as fout:
    reader = csv.DictReader(fin)
    writer = csv.DictWriter(fout, fieldnames=reader.fieldnames)
    writer.writeheader()
    for row in reader:
        row["symbol"] = "MNQ"
        writer.writerow(row)
def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
manifest = {
    "generated_at": datetime.now(UTC).isoformat(),
    "symbol": "MNQ",
    "kind": "MODELED_FROM_NQ_PRICE_SERIES",
    "warning": "MNQ price path is identical to the NQ series; only execution economics differ. "
               "Results are NOT independent evidence for MNQ.",
    "source": src, "source_sha256": sha256(src),
    "target": dst, "target_sha256": sha256(dst),
}
with open("artifacts/data/mnq_2m_modeled_from_nq.manifest.json", "w") as f:
    json.dump(manifest, f, indent=2)
PY

echo "[5/6] running deep research suites (NQ and MNQ in parallel, holdout stays locked)"
PYTHONPATH=src python -m sphinx_bot deep-backtest \
  --nq-data artifacts/data/nq_2m.csv \
  --bootstrap-simulations "$BOOTSTRAP_SIMULATIONS" \
  --output artifacts/deep_research_nq.json &
NQ_PID=$!
PYTHONPATH=src python -m sphinx_bot deep-backtest \
  --mnq-data artifacts/data/mnq_2m_modeled_from_nq.csv \
  --bootstrap-simulations "$BOOTSTRAP_SIMULATIONS" \
  --output artifacts/deep_research_mnq.json &
MNQ_PID=$!
wait "$NQ_PID" "$MNQ_PID"

echo "[6/6] merging paired report"
PYTHONPATH=src python - <<'PY'
import json
from sphinx_bot.research.deep import paired_instrument_summary
nq = json.load(open("artifacts/deep_research_nq.json"))
mnq = json.load(open("artifacts/deep_research_mnq.json"))
reports = {"NQ": nq["reports"]["NQ"], "MNQ": mnq["reports"]["MNQ"]}
json.dump({
    "status": "RESEARCH_ONLY_NO_PROFITABILITY_CLAIM",
    "reports": reports,
    "paired_summary": paired_instrument_summary(reports),
    "holdout_opened": False,
}, open("artifacts/deep_research.json", "w"), indent=2)
print("merged -> artifacts/deep_research.json (holdout_opened: False)")
PY

echo "done. dashboard: PYTHONPATH=src python -m sphinx_bot dashboard --host 0.0.0.0 --port 8000 \\"
echo "  --nq-data artifacts/data/nq_2m.csv --mnq-data artifacts/data/mnq_2m_modeled_from_nq.csv \\"
echo "  --deep-report artifacts/deep_research.json"
