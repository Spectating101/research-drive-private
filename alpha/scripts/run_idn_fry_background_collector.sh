#!/usr/bin/env bash
# Incremental fry data collector — safe to run on a timer.
# Prioritizes: attention (cheap) → broker backfill (slow) → structural gaps → merge/report.
#
# Env overrides:
#   IDN_FRY_BG_BROKER_MAX_CALLS=15   RapidAPI broker-summary calls per run (default 15)
#   IDN_FRY_BG_BROKER_DELAY=3.5
#   IDN_FRY_BG_STRUCTURAL_MAX_CALLS=0  skip structural live calls when 0 (default)
#   IDN_FRY_BG_SKIP_BROKER=1         set to skip broker lane entirely
#   IDN_FRY_BG_TECHNICAL_MAX_CALLS=10   symbol technical snapshots per run
#   IDN_FRY_BG_TECHNICAL_TRIGGER_MAX=8   recent trigger episode technical rows
#   IDN_FRY_BG_ENABLE_REDDIT=0       Reddit needs OAuth; off by default
#
# Manual:
#   bash scripts/run_idn_fry_background_collector.sh
#   IDN_FRY_BG_BROKER_MAX_CALLS=50 bash scripts/run_idn_fry_background_collector.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"

LOCK_FILE="${SR_DIR}/.locks/idn_fry_background_collector.lock"
LOG_DIR="${SR_DIR}/logs"
LOG_FILE="${LOG_DIR}/idn_fry_background_collector.log"
STATUS_FILE="${SR_DIR}/data_lake/research_panels/idn_fry_episode/fry_background_collector_status.json"

BROKER_MAX="${IDN_FRY_BG_BROKER_MAX_CALLS:-15}"
BROKER_DELAY="${IDN_FRY_BG_BROKER_DELAY:-3.5}"
STRUCT_MAX="${IDN_FRY_BG_STRUCTURAL_MAX_CALLS:-0}"
SKIP_BROKER="${IDN_FRY_BG_SKIP_BROKER:-0}"
REFRESH_REPORT="${IDN_FRY_BG_REFRESH_REPORT:-1}"
TECH_MAX="${IDN_FRY_BG_TECHNICAL_MAX_CALLS:-10}"
TECH_TRIG_MAX="${IDN_FRY_BG_TECHNICAL_TRIGGER_MAX:-8}"
ENABLE_REDDIT="${IDN_FRY_BG_ENABLE_REDDIT:-0}"

mkdir -p "${LOG_DIR}" "$(dirname "${LOCK_FILE}")" "$(dirname "${STATUS_FILE}")"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "$(date -Is) skip: another fry background collector is running" | tee -a "${LOG_FILE}"
  exit 0
fi

log() {
  echo "$(date -Is) $*" | tee -a "${LOG_FILE}"
}

log "start broker_max=${BROKER_MAX} struct_max=${STRUCT_MAX} tech_max=${TECH_MAX} skip_broker=${SKIP_BROKER}"
t0=$(date +%s)
exit_code=0

run_lane() {
  local label="$1"
  shift
  log "lane ${label}: $*"
  if ! "${SR_PYTHON}" "$@" >>"${LOG_FILE}" 2>&1; then
    log "lane ${label}: FAILED (continuing)"
    exit_code=1
  fi
}

# 1) Attention — one trending call + panel rebuild (cheap, run every tick)
run_lane attention "${SR_DIR}/scripts/run_idn_fry_data_collection.py" --lane attention

# 2b) Re-parse structural enrichments from emiten disk cache (index flags, insider)
run_lane enrich "${SR_DIR}/scripts/run_idn_fry_data_collection.py" --lane enrich

# 2c) Technical snapshots (live API — current state for watchlist + recent triggers)
if [[ "${TECH_MAX}" -gt 0 ]]; then
  run_lane technical "${SR_DIR}/scripts/run_idn_fry_data_collection.py" --lane technical --missing-only --max-live-calls "${TECH_MAX}"
else
  log "lane technical: skipped"
fi
if [[ "${TECH_TRIG_MAX}" -gt 0 ]]; then
  run_lane technical_triggers "${SR_DIR}/scripts/run_idn_fry_data_collection.py" --lane technical_triggers --max-live-calls "${TECH_TRIG_MAX}"
else
  log "lane technical_triggers: skipped"
fi

# 3) Structural — only when gaps exist and budget > 0
if [[ "${STRUCT_MAX}" -gt 0 ]]; then
  run_lane structural "${SR_DIR}/scripts/run_idn_fry_data_collection.py" \
    --lane structural --missing-only --max-live-calls "${STRUCT_MAX}"
else
  log "lane structural: skipped (STRUCT_MAX=0, panel complete)"
fi

# 3) Broker queue refresh + paced backfill (main backlog driver)
run_lane broker_queue "${SR_DIR}/scripts/run_idn_fry_data_collection.py" --lane broker --skip-broker
if [[ "${SKIP_BROKER}" != "1" && "${BROKER_MAX}" -gt 0 ]]; then
  run_lane broker_backfill "${SR_DIR}/scripts/run_idn_broker_backfill.py" \
    --source fry --max-calls "${BROKER_MAX}" --delay "${BROKER_DELAY}"
else
  log "lane broker_backfill: skipped"
fi

# 4) Reddit — opt-in only
if [[ "${ENABLE_REDDIT}" == "1" ]]; then
  run_lane reddit "${SR_DIR}/scripts/run_idn_fry_data_collection.py" --lane reddit --reddit
else
  log "lane reddit: skipped (set IDN_FRY_BG_ENABLE_REDDIT=1 + OAuth to enable)"
fi

# 5) Merge structural into triggers + manifest
run_lane merge "${SR_DIR}/scripts/run_idn_fry_data_collection.py" --lane merge

# 6) Refresh on-disk empirics report (no live API)
if [[ "${REFRESH_REPORT}" == "1" ]]; then
  run_lane report "${SR_DIR}/scripts/run_idn_fry_available_analysis.py"
fi

elapsed=$(( $(date +%s) - t0 ))
cache_count=0
if [[ -d "${SR_DIR}/data_lake/markets/idx_broker_summary/cache" ]]; then
  cache_count=$(find "${SR_DIR}/data_lake/markets/idx_broker_summary/cache" -maxdepth 1 -name '*.json' | wc -l)
fi

"${SR_PYTHON}" - <<PY
import json
from datetime import UTC, datetime
from pathlib import Path

status = {
    "finished_at_utc": datetime.now(UTC).isoformat(),
    "elapsed_sec": ${elapsed},
    "exit_code": ${exit_code},
    "broker_max_calls": ${BROKER_MAX},
    "structural_max_calls": ${STRUCT_MAX},
    "broker_cache_files": ${cache_count},
    "log_file": "${LOG_FILE}",
}
Path("${STATUS_FILE}").write_text(json.dumps(status, indent=2), encoding="utf-8")
print(json.dumps(status, indent=2))
PY

log "done elapsed=${elapsed}s exit=${exit_code} broker_cache=${cache_count}"
exit "${exit_code}"
