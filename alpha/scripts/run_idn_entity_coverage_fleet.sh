#!/usr/bin/env bash
# IDX entity coverage fleet — rebuild from existing overlays + fill missing months.
set -euo pipefail
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
cd "$ROOT"

RUN_ID="${RUN_ID:-ticker_$(date -u +%Y%m%d)}"
LOG_DIR="${LOG_DIR:-logs/idn_entity_coverage}"
PARALLEL="${PARALLEL:-1}"
LIMIT="${LIMIT:-0}"
mkdir -p "$LOG_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG="$LOG_DIR/fleet_${STAMP}.log"
exec > >(tee -a "$LOG") 2>&1

echo "idn_entity_coverage_fleet run_id=$RUN_ID"

echo "=== audit ==="
.venv/bin/python scripts/audit_idn_entity_coverage.py
.venv/bin/python scripts/idn_entity_coverage_queue.py

QUEUE="backtests/outputs/platform/idn_entity_coverage/overlay_queue.json"
if [[ -f "$QUEUE" ]]; then
  missing="$(python3 -c "import json;print(json.load(open('$QUEUE'))['missing_total'])")"
  echo "overlay queue missing_months=$missing"
fi

echo "=== probe cluster ==="
if [[ -x /home/phyrexian/cluster-lab-logs/cluster-run.sh ]]; then
  /home/phyrexian/cluster-lab-logs/cluster-run.sh "hostname" || true
else
  echo "cluster-run.sh not found; local lanes only"
fi

echo "=== aggregate existing overlays -> entity weekly ==="
PHASE=entity RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh --overlay-aggregate-only

echo "=== fused entity-market panel ==="
PHASE=fused RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh

echo "=== tier3 extras ==="
PHASE=tier3_extras RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh

echo "=== QA ==="
.venv/bin/python scripts/qa_ticker_entity_tier3.py --run-dir "data_lake/research_panels/ticker_news_market/${RUN_ID}" || true

echo "=== build missing overlays (local lanes=$PARALLEL) ==="
if [[ -f "$QUEUE" ]]; then
  mapfile -t keys < <(python3 -c "
import json
q=json.load(open('$QUEUE'))
keys=q.get('priority_window_keys',[])
limit=int('$LIMIT')
if limit>0: keys=keys[:limit]
print('\n'.join(keys))
")
  if [[ ${#keys[@]} -eq 0 ]]; then
    echo "no missing overlay keys"
  else
    echo "processing ${#keys[@]} missing windows"
    running=0
    for key in "${keys[@]}"; do
      start="${key%%_*}"
      end="${key#*_}"
      while (( running >= PARALLEL )); do
        wait -n 2>/dev/null || wait
        running=$((running - 1))
      done
      (
        echo "-- window $key"
        .venv/bin/python scripts/news_shock_taxonomy/expand_gdelt_entity_article_coverage.py --start "$start" --end "$end" --limit 1 || true
        PHASE=entity RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh --force-entity-overlay --max-windows 1
      ) &
      running=$((running + 1))
    done
    wait || true
    echo "re-aggregate after overlay builds"
    PHASE=entity RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh --overlay-aggregate-only
    PHASE=fused RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh
  fi
fi

echo "=== post audit ==="
.venv/bin/python scripts/audit_idn_entity_coverage.py

echo "done run_id=$RUN_ID log=$LOG"
echo "if validated, point registry default_run_id to $RUN_ID for entity datasets"
