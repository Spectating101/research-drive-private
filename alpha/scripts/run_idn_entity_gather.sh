#!/usr/bin/env bash
# Gather missing IDX entity article months sequentially (disk-safe), then rebuild fused panel.
set -euo pipefail
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
cd "$ROOT"

RUN_ID="${RUN_ID:-ticker_$(date -u +%Y%m%d)}"
LOG_DIR="${LOG_DIR:-logs/idn_entity_coverage}"
LIMIT="${LIMIT:-0}"
SKIP_REBUILD="${SKIP_REBUILD:-0}"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/gather_${STAMP}.log"
exec > >(tee -a "$LOG") 2>&1

echo "idn_entity_gather run_id=$RUN_ID limit=$LIMIT"

.venv/bin/python scripts/audit_idn_entity_coverage.py
.venv/bin/python scripts/idn_entity_coverage_queue.py

QUEUE="backtests/outputs/platform/idn_entity_coverage/overlay_queue.json"
mapfile -t keys < <(python3 -c "
import json
q=json.load(open('$QUEUE'))
keys=q.get('priority_window_keys',[])
limit=int('$LIMIT')
if limit>0:
    keys=keys[:limit]
print('\n'.join(keys))
")

echo "windows to process: ${#keys[@]}"
ok=0
fail=0
for key in "${keys[@]}"; do
  echo ""
  echo "======== window $key ($((ok + fail + 1))/${#keys[@]}) ========"
  if bash scripts/idn_entity_window_worker.sh "$key" "$RUN_ID"; then
    ok=$((ok + 1))
  else
    fail=$((fail + 1))
    echo "FAILED window $key (continuing)"
  fi
  # refresh queue stats
  .venv/bin/python scripts/idn_entity_coverage_queue.py || true
done

echo "windows ok=$ok fail=$fail"

if [[ "$SKIP_REBUILD" != "1" ]]; then
  echo "=== re-aggregate all overlays ==="
  PHASE=entity RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh --overlay-aggregate-only
  echo "=== fused panel ==="
  PHASE=fused RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh
  echo "=== tier3 extras ==="
  PHASE=tier3_extras RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh
  .venv/bin/python scripts/qa_ticker_entity_tier3.py --run-dir "data_lake/research_panels/ticker_news_market/${RUN_ID}" || true
fi

.venv/bin/python scripts/audit_idn_entity_coverage.py
echo "done run_id=$RUN_ID log=$LOG"
