#!/usr/bin/env bash
set -euo pipefail

# Slow, Drive-first historical GDELT GKG Asia backfill.
#
# The lane split lets two systemd units share the calendar range while a shared
# heavy lock keeps expensive fetch/score sections serialized. This is
# intentionally conservative: finish safely over days/weeks instead of risking
# memory pressure on the desktop.

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

backfill_start="${BACKFILL_START:-2018-01-01}"
backfill_end="${BACKFILL_END:-2024-01-01}"
run_tag="${RUN_TAG:-20260526Tbackfill2018_2023Z}"
month_modulo="${MONTH_MODULO:-2}"
month_remainder="${MONTH_REMAINDER:-0}"
max_months_per_run="${MAX_MONTHS_PER_RUN:-0}"
remote_root="${REMOTE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/news/gdelt-asia/gdelt_gkg_asia_backfill_2018_2023}"
local_retention="${LOCAL_RETENTION:-compact}"
score_offload_nodes="${SCORE_OFFLOAD_NODES:-}"
status_dir="${STATUS_DIR:-logs/news_shock_taxonomy/gkg_backfill_2018_2023}"
status_state_dir="${STATUS_STATE_DIR:-data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023}"
disk_min_free_gb="${DISK_MIN_FREE_GB:-60}"
resource_wait_seconds="${RESOURCE_WAIT_SECONDS:-600}"

mkdir -p "${status_dir}" "${status_state_dir}" ".locks"

export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

write_status() {
  local run_id="$1"
  local status="$2"
  local detail="${3:-}"
  python3 - "$status_dir/status_lane_${month_remainder}_of_${month_modulo}.jsonl" "$run_id" "$status" "$detail" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
row = {
    "ts": datetime.now(UTC).isoformat(),
    "run_id": sys.argv[2],
    "status": sys.argv[3],
    "detail": sys.argv[4],
}
with path.open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(row, separators=(",", ":")) + "\n")
PY
}

disk_free_gb() {
  df -BG . | awk 'NR==2 {gsub("G", "", $4); print int($4)}'
}

wait_for_disk_headroom() {
  while true; do
    local free_gb
    free_gb="$(disk_free_gb)"
    log "disk_check free_gb=${free_gb} required_free_gb=${disk_min_free_gb}"
    if (( free_gb >= disk_min_free_gb )); then
      return 0
    fi
    log "disk_waiting"
    sleep "${resource_wait_seconds}"
  done
}

score_offload_node_for_start() {
  local start_date="$1"
  [[ -n "${score_offload_nodes}" ]] || return 0

  local nodes=()
  local node
  IFS=',' read -r -a nodes <<< "${score_offload_nodes}"
  [[ "${#nodes[@]}" -gt 0 ]] || return 0

  local base_year base_month year month
  base_year="${backfill_start%%-*}"
  base_month="${backfill_start#*-}"
  base_month="${base_month%%-*}"
  year="${start_date%%-*}"
  month="${start_date#*-}"
  month="${month%%-*}"

  local month_index node_index
  month_index=$(( (10#${year} - 10#${base_year}) * 12 + 10#${month} - 10#${base_month} ))
  node_index=$(( month_index % ${#nodes[@]} ))
  node="${nodes[${node_index}]}"
  printf '%s' "${node}"
}

month_windows() {
  python3 - "$backfill_start" "$backfill_end" "$month_modulo" "$month_remainder" <<'PY'
from __future__ import annotations

import sys
from datetime import date


def parse(value: str) -> date:
    y, m, d = map(int, value.split("-"))
    return date(y, m, d)


def add_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


start = parse(sys.argv[1])
end = parse(sys.argv[2])
month_modulo = max(1, int(sys.argv[3]))
month_remainder = int(sys.argv[4])
cursor = date(start.year, start.month, 1)
idx = 0
while cursor < end:
    nxt = min(add_month(cursor), end)
    if idx % month_modulo == month_remainder:
        print(cursor.isoformat(), nxt.isoformat())
    cursor = nxt
    idx += 1
PY
}

compact_local_copy() {
  local run_id="$1"
  local norm_dir="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}"
  local proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"

  [[ "${local_retention}" == "compact" ]] || return 0

  # Remove only large staging artifacts produced by this backfill after Drive
  # copy/check has succeeded. Keep daily panels, summaries, and samples local.
  rm -f \
    "${norm_dir}/asia_gkg_filtered.csv.gz" \
    "${proc_dir}/asia_gkg_scored.csv.gz" \
    "${proc_dir}/url_enrichment_queue.csv.gz" \
    "${proc_dir}/url_enrichment_enrich_high_priority.csv.gz" \
    "${proc_dir}/url_enrichment_enrich_high_priority.jsonl.gz"
  rmdir "${norm_dir}" 2>/dev/null || true
}

sync_and_verify_month() {
  local run_id="$1"
  local norm_dir="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}"
  local proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"
  local remote_norm="${remote_root}/normalized/gdelt_gkg_asia_bulk/${run_id}"
  local remote_proc="${remote_root}/processed/${run_id}"

  rclone copy "${norm_dir}" "${remote_norm}" --transfers 2 --checkers 4 --stats-one-line
  rclone copy "${proc_dir}" "${remote_proc}" --transfers 2 --checkers 4 --stats-one-line
  rclone check "${norm_dir}" "${remote_norm}" --one-way --size-only --combined -
  rclone check "${proc_dir}" "${remote_proc}" --one-way --size-only --combined -
}

mark_ok() {
  local run_id="$1"
  local start_date="$2"
  local end_date="$3"
  local marker="${status_state_dir}/${run_id}.ok.json"
  python3 - "$marker" "$run_id" "$start_date" "$end_date" "$remote_root" "$local_retention" <<'PY'
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

path = Path(sys.argv[1])
path.parent.mkdir(parents=True, exist_ok=True)
payload = {
    "ts": datetime.now(UTC).isoformat(),
    "run_id": sys.argv[2],
    "start_date": sys.argv[3],
    "end_date": sys.argv[4],
    "remote_root": sys.argv[5],
    "local_retention": sys.argv[6],
    "status": "drive_verified",
}
path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
PY
}

require_tools() {
  command -v rclone >/dev/null
  command -v python3 >/dev/null
  [[ -x scripts/run_news_shock_gkg_window_pipeline.sh ]]
}

require_tools

log "backfill_lane_started start=${backfill_start} end=${backfill_end} run_tag=${run_tag} lane=${month_remainder}/${month_modulo} local_retention=${local_retention}"

months_done=0
while read -r start_date end_date; do
  [[ -z "${start_date}" || -z "${end_date}" ]] && continue
  label="$(echo "${start_date}_${end_date}" | tr -d '-' | tr ':' '_' | tr 'T' '_' | tr -d '+')"
  run_id="asia_gkg_window_${label}_${run_tag}"
  marker="${status_state_dir}/${run_id}.ok.json"
  daily_panel="data_lake/news_shock_taxonomy/processed/${run_id}/daily_country_shock_panel.csv"

  if [[ -s "${marker}" && -s "${daily_panel}" ]]; then
    log "skip_verified run_id=${run_id}"
    continue
  fi

  if (( max_months_per_run > 0 && months_done >= max_months_per_run )); then
    log "max_months_per_run_reached count=${months_done}"
    break
  fi

  write_status "${run_id}" "started" "${start_date}_${end_date}"
  log "month_started run_id=${run_id} start=${start_date} end=${end_date}"
  wait_for_disk_headroom
  score_offload_node="$(score_offload_node_for_start "${start_date}")"
  if [[ -n "${score_offload_node}" ]]; then
    log "score_offload_assigned run_id=${run_id} node=${score_offload_node}"
  fi

  KEEP_RAW=0 \
  REUSE_EXISTING=1 \
  TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-300}" \
  RETRIES="${RETRIES:-4}" \
  FETCH_SLEEP="${FETCH_SLEEP:-0.3}" \
  FETCH_WORKERS="${FETCH_WORKERS:-2}" \
  MAX_SAFE_FETCH_WORKERS="${MAX_SAFE_FETCH_WORKERS:-2}" \
  MAX_ENRICH_URLS="${MAX_ENRICH_URLS:-25}" \
  MASTER_REFRESH_SECONDS="${MASTER_REFRESH_SECONDS:-86400}" \
  SCORE_MIN_AVAILABLE_GB="${SCORE_MIN_AVAILABLE_GB:-14}" \
  FETCH_MIN_AVAILABLE_GB="${FETCH_MIN_AVAILABLE_GB:-12}" \
  ENRICH_MIN_AVAILABLE_GB="${ENRICH_MIN_AVAILABLE_GB:-12}" \
  MIN_SAFE_SCORE_AVAILABLE_GB="${MIN_SAFE_SCORE_AVAILABLE_GB:-14}" \
  MIN_SAFE_FETCH_AVAILABLE_GB="${MIN_SAFE_FETCH_AVAILABLE_GB:-12}" \
  MAX_SWAP_USED_GB="${MAX_SWAP_USED_GB:-24}" \
  MAX_SAFE_SWAP_USED_GB="${MAX_SAFE_SWAP_USED_GB:-24}" \
  RESOURCE_WAIT_SECONDS="${resource_wait_seconds}" \
  HEAVY_LOCK_FILE="${HEAVY_LOCK_FILE:-.locks/news_shock_backfill_2018_2023_heavy.lock}" \
  SCORE_LOCK_FILE="${SCORE_LOCK_FILE:-.locks/news_shock_backfill_2018_2023_score.lock}" \
  SCORE_OFFLOAD_NODE="${score_offload_node}" \
  scripts/run_news_shock_gkg_window_pipeline.sh "${run_id}" "${start_date}" "${end_date}"

  gzip -t "data_lake/news_shock_taxonomy/processed/${run_id}/url_enrichment_enrich_high_priority.csv.gz"
  [[ -s "${daily_panel}" ]]
  sync_and_verify_month "${run_id}"
  mark_ok "${run_id}" "${start_date}" "${end_date}"
  compact_local_copy "${run_id}"

  months_done=$((months_done + 1))
  write_status "${run_id}" "ok" "drive_verified"
  log "month_finished run_id=${run_id}"
done < <(month_windows)

log "backfill_lane_finished months_done=${months_done}"
