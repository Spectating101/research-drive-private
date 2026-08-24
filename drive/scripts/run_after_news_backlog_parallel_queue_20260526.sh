#!/usr/bin/env bash
set -euo pipefail

# Wait for the current GDELT jobs to finish, then run independent public data
# lanes concurrently. This excludes Refinitiv/LSEG/WRDS and all credentialed
# sources.

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

poll_seconds="${POLL_SECONDS:-300}"
require_success="${REQUIRE_SUCCESS:-1}"
wait_units_default="sharpe-data-backlog-20260526-janresume.service sharpe-news-prefetch-20260526-febparallel.service"
wait_units="${WAIT_UNITS:-${wait_units_default}}"
run_id="${RUN_ID:-post_gdelt_parallel_20260526}"
remote_root="${REMOTE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data}"
status_dir="data_lake/data_collection_queue"
log_dir="logs/data_collection_queue"
watch_log="${log_dir}/${run_id}_watch.log"
status_jsonl="${status_dir}/${run_id}_status.jsonl"
lock_file=".locks/${run_id}.lock"

mkdir -p "${status_dir}" "${log_dir}" "$(dirname "${lock_file}")"

ts() {
  date -u +%Y-%m-%dT%H:%M:%SZ
}

json_status() {
  local status="$1"
  local task="$2"
  local detail="${3:-}"
  python3 - "$status" "$task" "$detail" <<'PY' >>"${status_jsonl}"
import json
import sys
from datetime import datetime, timezone

status, task, detail = sys.argv[1:4]
print(json.dumps({
    "ts": datetime.now(timezone.utc).isoformat(),
    "run_id": "post_gdelt_parallel_20260526",
    "task": task,
    "status": status,
    "detail": detail,
}, separators=(",", ":")))
PY
}

log() {
  echo "$*" | tee -a "${watch_log}"
}

unit_property() {
  local unit="$1"
  local prop="$2"
  systemctl --user show "${unit}" -p "${prop}" --value 2>/dev/null || true
}

unit_exists() {
  local unit="$1"
  systemctl --user status "${unit}" >/dev/null 2>&1
}

active_units() {
  local unit state
  for unit in ${wait_units}; do
    state="$(unit_property "${unit}" ActiveState)"
    if [[ "${state}" == "active" || "${state}" == "activating" || "${state}" == "reloading" ]]; then
      echo "${unit}"
    fi
  done
}

failed_units() {
  local unit state
  for unit in ${wait_units}; do
    if ! unit_exists "${unit}"; then
      continue
    fi
    state="$(unit_property "${unit}" ActiveState)"
    if [[ "${state}" == "failed" ]]; then
      echo "${unit}"
    fi
  done
}

run_logged() {
  local task="$1"
  shift
  local task_log="${log_dir}/${run_id}_${task}.log"
  json_status started "${task}" "$*"
  log "task_started_at=$(ts) task=${task}"
  if "$@" >>"${task_log}" 2>&1; then
    json_status ok "${task}" "${task_log}"
    log "task_finished_at=$(ts) task=${task} status=ok"
    return 0
  fi
  local rc=$?
  json_status failed "${task}" "rc=${rc} log=${task_log}"
  log "task_finished_at=$(ts) task=${task} status=failed rc=${rc}"
  return "${rc}"
}

market_lane() {
  run_logged public_macro_asia_market_sidecar \
    bash -lc 'SKIP_REDDIT_SYNC=1 MIN_FREE_GB=60 bash scripts/run_public_data_sidecar_20260525.sh'
}

reddit_lane() {
  run_logged reddit_social_attention_ingest \
    python3 scripts/reddit_ingest_daily.py \
      --fetch-modes new hot top:day top:week \
      --limit 100 \
      --max-pages 4 \
      --sleep-secs 1.2 \
      --stop-after-known 40 \
      --comments-lookback-hours 48 \
      --comments-max-posts 80 \
      --comments-min-refetch-hours 24 \
      --lookback-days 45 \
      --min-upvotes 3
  run_logged reddit_social_attention_health python3 scripts/reddit_data_health.py
  run_logged reddit_social_attention_drive_copy bash scripts/sync_reddit_sentiment_drive.sh
}

panel_lane() {
  run_logged asia_news_market_panel_build \
    python3 scripts/build_asia_news_market_panel.py \
      --market-run latest \
      --run-id "${run_id}"
  run_logged asia_news_market_panel_diagnostics \
    python3 scripts/analyze_asia_news_market_panel.py \
      --panel-dir "data_lake/research_panels/asia_news_market/${run_id}" \
      --out-dir "data_lake/research_panels/asia_news_market/${run_id}/diagnostics"
  run_logged asia_news_market_panel_drive_copy \
    rclone copy "data_lake/research_panels/asia_news_market/${run_id}" \
      "${remote_root}/research_panels/asia_news_market/${run_id}" \
      --transfers 4 --checkers 8 --stats-one-line
  run_logged queue_logs_drive_copy \
    rclone copy "${log_dir}" \
      "${remote_root}/manifests/data_collection_queue/logs" \
      --transfers 4 --checkers 8 --stats-one-line
}

main() {
  log "watch_started_at=$(ts)"
  log "wait_units=${wait_units}"
  log "require_success=${require_success}"

  while true; do
    mapfile -t active < <(active_units)
    mapfile -t failed < <(failed_units)

    if (( ${#failed[@]} > 0 && require_success == 1 )); then
      log "watch_aborted_at=$(ts) reason=failed_units units=${failed[*]}"
      json_status failed watcher "failed_units=${failed[*]}"
      exit 2
    fi

    if (( ${#active[@]} == 0 )); then
      break
    fi

    log "waiting_at=$(ts) active_units=${active[*]}"
    sleep "${poll_seconds}"
  done

  log "news_backlog_clear_at=$(ts)"
  json_status started parallel_queue "market_lane+reddit_lane"

  market_lane &
  market_pid=$!
  reddit_lane &
  reddit_pid=$!

  market_rc=0
  reddit_rc=0
  wait "${market_pid}" || market_rc=$?
  wait "${reddit_pid}" || reddit_rc=$?
  log "parallel_lanes_finished_at=$(ts) market_rc=${market_rc} reddit_rc=${reddit_rc}"

  panel_rc=0
  panel_lane || panel_rc=$?

  final_rc=0
  if (( market_rc != 0 || reddit_rc != 0 || panel_rc != 0 )); then
    final_rc=1
  fi
  json_status finished parallel_queue "market_rc=${market_rc} reddit_rc=${reddit_rc} panel_rc=${panel_rc}"
  log "queue_finished_at=$(ts) returncode=${final_rc}"
  return "${final_rc}"
}

(
  flock -n 9 || {
    log "parallel queue already running: ${lock_file}"
    exit 0
  }
  main
) 9>"${lock_file}"
