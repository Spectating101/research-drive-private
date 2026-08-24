#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 WORKER_INDEX WORKER_COUNT local|windows [WINDOWS_HOSTNAME_OR_IP]" >&2
  echo "example: $0 0 4 local" >&2
  echo "example: $0 1 4 windows DESKTOP-VEFGGDH" >&2
  exit 2
fi

worker_index="$1"
worker_count="$2"
worker_kind="$3"
worker_node="${4:-}"

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

queue_start="${QUEUE_START:-2018-01-01}"
queue_end="${QUEUE_END:-2024-01-01}"
run_tag="${RUN_TAG:-20260526Tbackfill2018_2023Z}"
status_state_dir="${STATUS_STATE_DIR:-data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023}"
poll_seconds="${POLL_SECONDS:-300}"
retry_seconds="${RETRY_SECONDS:-600}"

mkdir -p "${status_state_dir}" logs/news_shock_taxonomy/gkg_partition_queues

log() {
  printf '%s worker=%s/%s kind=%s node=%s %s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "${worker_index}" \
    "${worker_count}" \
    "${worker_kind}" \
    "${worker_node:-optiplex}" \
    "$*"
}

month_windows() {
  python3 - "$queue_start" "$queue_end" "$worker_index" "$worker_count" "$run_tag" <<'PY'
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
worker_index = int(sys.argv[3])
worker_count = int(sys.argv[4])
run_tag = sys.argv[5]

cursor = date(start.year, start.month, 1)
idx = 0
while cursor < end:
    nxt = min(add_month(cursor), end)
    if idx % worker_count == worker_index:
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

  [[ -s "${normalized_file}" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] || return 1
  gzip -t "${normalized_file}" >/dev/null 2>&1 || return 1
  gzip -t "${scored_file}" >/dev/null 2>&1 || return 1
  gzip -t "${url_queue_file}" >/dev/null 2>&1 || return 1
}

run_is_active() {
  local run_id="$1"
  ps -eo pid=,cmd= \
    | grep -F "${run_id}" \
    | grep -E "fetch_gdelt_gkg_asia_bulk|score_gdelt_gkg_asia|run_news_shock_gkg_windows_fetch_score_worker|run_news_shock_gkg_local_fetch_score_worker|run_gdelt_fetch_score" \
    | grep -v "run_news_shock_gkg_worker_partition_queue" \
    >/dev/null
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
      echo "windows worker requires WINDOWS_HOSTNAME_OR_IP" >&2
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

log "queue_started start=${queue_start} end=${queue_end} run_tag=${run_tag}"

while read -r month_index start_date end_date run_id; do
  [[ -n "${run_id:-}" ]] || continue
  marker="${status_state_dir}/${run_id}.ok.json"

  if [[ -s "${marker}" ]]; then
    log "skip_ok run_id=${run_id}"
    continue
  fi

  log "month_claimed month_index=${month_index} run_id=${run_id} start=${start_date} end=${end_date}"
  while true; do
    if [[ -s "${marker}" ]]; then
      log "month_done_by_uploader run_id=${run_id}"
      break
    fi

    if artifact_complete "${run_id}"; then
      log "artifacts_ready run_id=${run_id}"
      break
    fi

    if run_is_active "${run_id}"; then
      log "active_elsewhere_wait run_id=${run_id} sleep=${poll_seconds}"
      sleep "${poll_seconds}"
      continue
    fi

    log "worker_run_start run_id=${run_id}"
    if run_worker_once "${run_id}" "${start_date}" "${end_date}"; then
      if artifact_complete "${run_id}"; then
        log "worker_run_complete run_id=${run_id}"
        break
      fi
      log "worker_run_finished_but_artifacts_missing run_id=${run_id} sleep=${retry_seconds}"
    else
      log "worker_run_failed run_id=${run_id} sleep=${retry_seconds}"
    fi
    sleep "${retry_seconds}"
  done
done < <(month_windows)

log "queue_finished"
