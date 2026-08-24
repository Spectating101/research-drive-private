#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 HELPER_NAME local|windows [WINDOWS_HOSTNAME_OR_IP]" >&2
  echo "example: $0 helper_optiplex local" >&2
  echo "example: $0 helper_DESKTOP-VEFGGDH windows DESKTOP-VEFGGDH" >&2
  exit 2
fi

helper_name="$1"
worker_kind="$2"
worker_node="${3:-}"

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

queue_start="${QUEUE_START:-2018-01-01}"
queue_end="${QUEUE_END:-2024-01-01}"
run_tag="${RUN_TAG:-20260526Tbackfill2018_2023Z}"
status_state_dir="${STATUS_STATE_DIR:-data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023}"
lock_dir="${LOCK_DIR:-data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023_locks}"
poll_seconds="${POLL_SECONDS:-120}"
stale_lock_seconds="${STALE_LOCK_SECONDS:-21600}"

mkdir -p "${status_state_dir}" "${lock_dir}" logs/news_shock_gkg_queues

log() {
  printf '%s helper=%s kind=%s node=%s %s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "${helper_name}" \
    "${worker_kind}" \
    "${worker_node:-optiplex}" \
    "$*"
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
idx = 0
while cursor < end:
    nxt = min(add_month(cursor), end)
    label = f"{cursor.isoformat()}_{nxt.isoformat()}".replace("-", "")
    run_id = f"asia_gkg_window_{label}_{run_tag}"
    print(idx, cursor.isoformat(), nxt.isoformat(), run_id)
    cursor = nxt
    idx += 1
PY
}

artifact_complete() {
  local run_id="$1"
  local normalized_file="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}/asia_gkg_filtered.csv.gz"
  local scored_file="data_lake/news_shock_taxonomy/processed/${run_id}/asia_gkg_scored.csv.gz"
  local daily_panel_file="data_lake/news_shock_taxonomy/processed/${run_id}/daily_country_shock_panel.csv"
  local url_queue_file="data_lake/news_shock_taxonomy/processed/${run_id}/url_enrichment_queue.csv.gz"

  [[ -s "${normalized_file}" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]]
}

run_is_active() {
  local run_id="$1"
  ps -eo pid=,cmd= \
    | grep -F "${run_id}" \
    | grep -E "fetch_gdelt_gkg_asia_bulk|score_gdelt_gkg_asia|run_news_shock_gkg_windows_fetch_score_worker|run_news_shock_gkg_local_fetch_score_worker|run_gdelt_fetch_score" \
    | grep -v "run_news_shock_gkg_work_steal_queue" \
    >/dev/null
}

lock_is_stale() {
  local claim_dir="$1"
  [[ -d "${claim_dir}" ]] || return 1
  local now
  local mtime
  now="$(date +%s)"
  mtime="$(stat -c %Y "${claim_dir}" 2>/dev/null || echo "${now}")"
  (( now - mtime > stale_lock_seconds ))
}

try_claim() {
  local run_id="$1"
  local claim_dir="${lock_dir}/${run_id}.lock"

  if lock_is_stale "${claim_dir}"; then
    rmdir "${claim_dir}" 2>/dev/null || true
  fi

  if mkdir "${claim_dir}" 2>/dev/null; then
    {
      echo "helper=${helper_name}"
      echo "worker_kind=${worker_kind}"
      echo "worker_node=${worker_node:-optiplex}"
      echo "pid=$$"
      echo "claimed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "${claim_dir}/claim.txt"
    return 0
  fi
  return 1
}

release_claim() {
  local run_id="$1"
  local claim_dir="${lock_dir}/${run_id}.lock"
  rm -f "${claim_dir}/claim.txt" 2>/dev/null || true
  rmdir "${claim_dir}" 2>/dev/null || true
}

run_worker_once() {
  local run_id="$1"
  local start_date="$2"
  local end_date="$3"

  if [[ "${worker_kind}" == "local" ]]; then
    env \
      FETCH_WORKERS="${LOCAL_FETCH_WORKERS:-1}" \
      FETCH_TIMEOUT="${FETCH_TIMEOUT:-180}" \
      FETCH_RETRIES="${FETCH_RETRIES:-3}" \
      FETCH_SLEEP="${FETCH_SLEEP:-0.3}" \
      SCORE_CHUNK_SIZE="${SCORE_CHUNK_SIZE:-50000}" \
      SCORE_SAMPLE_SIZE="${SCORE_SAMPLE_SIZE:-200}" \
      OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}" \
      OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}" \
      MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}" \
      scripts/run_news_shock_gkg_local_fetch_score_worker.sh "${run_id}" "${start_date}" "${end_date}"
  elif [[ "${worker_kind}" == "windows" ]]; then
    [[ -n "${worker_node}" ]] || {
      echo "windows helper requires WINDOWS_HOSTNAME_OR_IP" >&2
      return 2
    }
    env \
      RETURN_MODE="${RETURN_MODE:-direct}" \
      FETCH_WORKERS="${WINDOWS_FETCH_WORKERS:-2}" \
      FETCH_TIMEOUT="${FETCH_TIMEOUT:-180}" \
      FETCH_RETRIES="${FETCH_RETRIES:-3}" \
      FETCH_SLEEP="${FETCH_SLEEP:-0.3}" \
      SCORE_CHUNK_SIZE="${SCORE_CHUNK_SIZE:-50000}" \
      SCORE_SAMPLE_SIZE="${SCORE_SAMPLE_SIZE:-200}" \
      BLAS_THREADS="${BLAS_THREADS:-2}" \
      scripts/run_news_shock_gkg_windows_fetch_score_worker.sh "${run_id}" "${start_date}" "${end_date}" "${worker_node}"
  else
    echo "unknown worker kind: ${worker_kind}" >&2
    return 2
  fi
}

find_and_run_one() {
  local saw_pending=0

  while read -r month_index start_date end_date run_id; do
    [[ -n "${run_id:-}" ]] || continue
    local marker="${status_state_dir}/${run_id}.ok.json"

    if [[ -s "${marker}" ]] || artifact_complete "${run_id}"; then
      continue
    fi

    saw_pending=1

    if run_is_active "${run_id}"; then
      log "skip_active month_index=${month_index} run_id=${run_id}"
      continue
    fi

    if ! try_claim "${run_id}"; then
      log "skip_locked month_index=${month_index} run_id=${run_id}"
      continue
    fi

    log "claimed month_index=${month_index} run_id=${run_id} start=${start_date} end=${end_date}"
    if run_worker_once "${run_id}" "${start_date}" "${end_date}"; then
      if artifact_complete "${run_id}"; then
        log "complete run_id=${run_id}"
      else
        log "finished_but_artifacts_missing run_id=${run_id}"
      fi
    else
      log "failed run_id=${run_id}"
    fi
    release_claim "${run_id}"
    return 0
  done < <(month_windows)

  if (( saw_pending == 0 )); then
    log "queue_finished_no_pending"
    return 2
  fi

  return 1
}

log "queue_started start=${queue_start} end=${queue_end} run_tag=${run_tag}"

while true; do
  set +e
  find_and_run_one
  status=$?
  set -e

  if (( status == 0 )); then
    continue
  fi

  if (( status == 2 )); then
    break
  fi
  log "no_claimable_work sleep=${poll_seconds}"
  sleep "${poll_seconds}"
done
