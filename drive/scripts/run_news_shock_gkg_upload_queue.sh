#!/usr/bin/env bash
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

queue_start="${QUEUE_START:-2018-01-01}"
queue_end="${QUEUE_END:-2024-01-01}"
run_tag="${RUN_TAG:-20260526Tbackfill2018_2023Z}"
status_state_dir="${STATUS_STATE_DIR:-data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023}"
remote_root="${REMOTE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/news/gdelt-asia/gdelt_gkg_asia_backfill_2018_2023}"
local_retention="${LOCAL_RETENTION:-compact}"
poll_seconds="${POLL_SECONDS:-300}"
max_enrich_urls="${MAX_ENRICH_URLS:-25}"
upload_lock_file="${UPLOAD_LOCK_FILE:-.locks/news_shock_gkg_upload_queue.lock}"

mkdir -p "${status_state_dir}" "$(dirname "${upload_lock_file}")" logs/news_shock_taxonomy/gkg_partition_queues

log() {
  printf '%s uploader %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

month_windows() {
  python3 - "$queue_start" "$queue_end" "$run_tag" <<'PY'
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
run_tag = sys.argv[3]

cursor = date(start.year, start.month, 1)
while cursor < end:
    nxt = min(add_month(cursor), end)
    label = f"{cursor.isoformat()}_{nxt.isoformat()}".replace("-", "")
    run_id = f"asia_gkg_window_{label}_{run_tag}"
    print(cursor.isoformat(), nxt.isoformat(), run_id)
    cursor = nxt
PY
}

artifact_complete() {
  local run_id="$1"
  local normalized_file="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}/asia_gkg_filtered.csv.gz"
  local scored_file="data_lake/news_shock_taxonomy/processed/${run_id}/asia_gkg_scored.csv.gz"
  local daily_panel_file="data_lake/news_shock_taxonomy/processed/${run_id}/daily_country_shock_panel.csv"
  local url_queue_file="data_lake/news_shock_taxonomy/processed/${run_id}/url_enrichment_queue.csv.gz"

  [[ -s "${normalized_file}" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] || return 1
  gzip -t "${normalized_file}" >/dev/null 2>&1 || return 1
  gzip -t "${scored_file}" >/dev/null 2>&1 || return 1
  gzip -t "${url_queue_file}" >/dev/null 2>&1 || return 1
}

ensure_enriched() {
  local run_id="$1"
  local url_queue_file="data_lake/news_shock_taxonomy/processed/${run_id}/url_enrichment_queue.csv.gz"
  local url_enriched_file="data_lake/news_shock_taxonomy/processed/${run_id}/url_enrichment_enrich_high_priority.csv.gz"

  if [[ -s "${url_enriched_file}" ]] && gzip -t "${url_enriched_file}" >/dev/null 2>&1; then
    log "enrichment_skip_existing run_id=${run_id}"
    return 0
  fi

  log "enrichment_start run_id=${run_id} max_urls=${max_enrich_urls}"
  python3 scripts/news_shock_taxonomy/enrich_gdelt_gkg_urls_local.py \
    --queue "${url_queue_file}" \
    --decisions enrich_high_priority \
    --max-urls "${max_enrich_urls}" \
    --timeout 15 \
    --max-bytes 600000 \
    --sleep 0.2 \
    --per-domain-delay 1.0
  gzip -t "${url_enriched_file}"
  log "enrichment_done run_id=${run_id}"
}

sync_and_verify_month() {
  local run_id="$1"
  local norm_dir="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}"
  local proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"
  local remote_norm="${remote_root}/normalized/gdelt_gkg_asia_bulk/${run_id}"
  local remote_proc="${remote_root}/processed/${run_id}"

  log "upload_norm_start run_id=${run_id}"
  rclone copy "${norm_dir}" "${remote_norm}" --transfers 2 --checkers 4 --stats-one-line
  log "upload_proc_start run_id=${run_id}"
  rclone copy "${proc_dir}" "${remote_proc}" --transfers 2 --checkers 4 --stats-one-line
  log "check_norm_start run_id=${run_id}"
  rclone check "${norm_dir}" "${remote_norm}" --one-way --size-only --combined -
  log "check_proc_start run_id=${run_id}"
  rclone check "${proc_dir}" "${remote_proc}" --one-way --size-only --combined -
  log "upload_check_done run_id=${run_id}"
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

compact_local_copy() {
  local run_id="$1"
  local norm_dir="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}"
  local proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"

  [[ "${local_retention}" == "compact" ]] || return 0

  rm -f \
    "${norm_dir}/asia_gkg_filtered.csv.gz" \
    "${proc_dir}/asia_gkg_scored.csv.gz" \
    "${proc_dir}/url_enrichment_queue.csv.gz" \
    "${proc_dir}/url_enrichment_enrich_high_priority.csv.gz" \
    "${proc_dir}/url_enrichment_enrich_high_priority.jsonl.gz"
  rmdir "${norm_dir}" 2>/dev/null || true
}

require_tools() {
  command -v rclone >/dev/null
  command -v python3 >/dev/null
}

require_tools

log "queue_started start=${queue_start} end=${queue_end} run_tag=${run_tag}"

exec 9>"${upload_lock_file}"
flock 9

while true; do
  pending=0
  uploaded_this_pass=0

  while read -r start_date end_date run_id; do
    [[ -n "${run_id:-}" ]] || continue
    marker="${status_state_dir}/${run_id}.ok.json"

    if [[ -s "${marker}" ]]; then
      continue
    fi

    pending=1
    if ! artifact_complete "${run_id}"; then
      continue
    fi

    log "month_ready run_id=${run_id}"
    ensure_enriched "${run_id}"
    sync_and_verify_month "${run_id}"
    mark_ok "${run_id}" "${start_date}" "${end_date}"
    compact_local_copy "${run_id}"
    uploaded_this_pass=1
    log "month_marked_ok run_id=${run_id}"
  done < <(month_windows)

  if (( pending == 0 )); then
    log "queue_finished_all_ok"
    break
  fi

  log "queue_sleep pending=1 uploaded_this_pass=${uploaded_this_pass} sleep=${poll_seconds}"
  sleep "${poll_seconds}"
done
