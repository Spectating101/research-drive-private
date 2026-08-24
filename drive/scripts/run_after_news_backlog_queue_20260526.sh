#!/usr/bin/env bash
set -euo pipefail

# Wait for the current GDELT backfill services to finish, then run the
# credential-free public data queue. Refinitiv/WRDS-style sources are excluded
# by the queue config.

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

queue_config="${QUEUE_CONFIG:-config/post_gdelt_data_collection_queue_20260526.json}"
poll_seconds="${POLL_SECONDS:-300}"
require_success="${REQUIRE_SUCCESS:-1}"
status_dir="data_lake/data_collection_queue"
log_dir="logs/data_collection_queue"
watch_log="${log_dir}/post_gdelt_queue_watch_20260526.log"
wait_units_default="sharpe-data-backlog-20260526-janresume.service sharpe-news-prefetch-20260526-febparallel.service"
wait_units="${WAIT_UNITS:-${wait_units_default}}"

mkdir -p "${status_dir}" "${log_dir}"

ts() {
  date -u +%Y-%m-%dT%H:%M:%SZ
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

log "watch_started_at=$(ts)"
log "queue_config=${queue_config}"
log "wait_units=${wait_units}"
log "require_success=${require_success}"

while true; do
  mapfile -t active < <(active_units)
  mapfile -t failed < <(failed_units)

  if (( ${#failed[@]} > 0 && require_success == 1 )); then
    log "watch_aborted_at=$(ts) reason=failed_units units=${failed[*]}"
    exit 2
  fi

  if (( ${#active[@]} == 0 )); then
    break
  fi

  log "waiting_at=$(ts) active_units=${active[*]}"
  sleep "${poll_seconds}"
done

log "news_backlog_clear_at=$(ts)"
python3 scripts/run_data_collection_queue.py \
  --queue "${queue_config}" \
  --continue-on-error
queue_rc=$?
log "queue_finished_at=$(ts) returncode=${queue_rc}"
exit "${queue_rc}"
