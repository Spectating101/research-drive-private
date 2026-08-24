#!/usr/bin/env bash
# Tier 3 end-to-end: wait for article prefetch (optional) -> entity overlay -> fused panel.
set -euo pipefail
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
cd "$ROOT"

RUN_ID="${RUN_ID:-ticker_$(date -u +%Y%m%d)}"
LOG_DIR="${LOG_DIR:-logs/gdelt_entity_expansion}"
WAIT_PULL_PID="${WAIT_PULL_PID:-}"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/tier3_${RUN_ID}_${STAMP}.log"

exec > >(tee -a "$LOG") 2>&1

echo "tier3_pipeline run_id=$RUN_ID started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ -n "$WAIT_PULL_PID" ]]; then
  echo "waiting for pull pid=$WAIT_PULL_PID"
  while kill -0 "$WAIT_PULL_PID" 2>/dev/null; do
    sleep 60
  done
  echo "pull pid finished"
fi

echo "=== entity overlay (all available article windows) ==="
PHASE=entity RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh --force-entity-overlay

echo "=== fused entity-market panel ==="
PHASE=fused RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh

echo "=== tier3 long + residual panels ==="
PHASE=tier3_extras RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh

echo "=== QA report ==="
.venv/bin/python scripts/qa_ticker_entity_tier3.py --run-dir "data_lake/research_panels/ticker_news_market/${RUN_ID}"

python3 - <<PY
import json
from pathlib import Path
run_id = "${RUN_ID}"
summary = Path("data_lake/research_panels/ticker_news_market") / run_id / "summary.json"
if summary.exists():
    data = json.loads(summary.read_text())
    ent = data.get("phases", {}).get("entity", {})
    fused = data.get("phases", {}).get("fused", {})
    print("entity_weekly_rows", ent.get("weekly_rows"))
    print("fused_panel_rows", fused.get("panel_rows"))
    print("fused_week_range", fused.get("week_min"), fused.get("week_max"))
PY

echo "done run_id=$RUN_ID log=$LOG"
echo "update config/research_query_registry.json default_run_id to $RUN_ID when validated"
