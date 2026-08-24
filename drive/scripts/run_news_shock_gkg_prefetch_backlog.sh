#!/usr/bin/env bash
set -euo pipefail

# Fetch/filter future GDELT GKG monthly windows without scoring or Drive copy.
# The full pipeline can later reuse these normalized files by run_id and skip
# directly to the controlled scoring/upload stages.

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"

prefetch_start="${PREFETCH_START:-2024-08-01}"
prefetch_end="${PREFETCH_END:-2026-06-01}"
run_tag="${RUN_TAG:?RUN_TAG is required, e.g. 20260524T181035Z}"
month_modulo="${MONTH_MODULO:-1}"
month_remainder="${MONTH_REMAINDER:-0}"
timeout_seconds="${TIMEOUT_SECONDS:-300}"
retries="${RETRIES:-4}"
fetch_sleep="${FETCH_SLEEP:-0.2}"
fetch_workers="${FETCH_WORKERS:-1}"
master_refresh_seconds="${MASTER_REFRESH_SECONDS:-86400}"
fetch_min_available_gb="${FETCH_MIN_AVAILABLE_GB:-12}"
min_safe_fetch_available_gb="${MIN_SAFE_FETCH_AVAILABLE_GB:-12}"
max_safe_fetch_workers="${MAX_SAFE_FETCH_WORKERS:-2}"
max_swap_used_gb="${MAX_SWAP_USED_GB:-1}"
max_safe_swap_used_gb="${MAX_SAFE_SWAP_USED_GB:-12}"
resource_wait_seconds="${RESOURCE_WAIT_SECONDS:-120}"
heavy_lock_file="${HEAVY_LOCK_FILE:-.locks/news_shock_heavy.lock}"

if (( fetch_workers > max_safe_fetch_workers )); then
  echo "fetch_workers_clamped_from=${fetch_workers} to=${max_safe_fetch_workers}"
  fetch_workers="${max_safe_fetch_workers}"
fi
if (( fetch_min_available_gb < min_safe_fetch_available_gb )); then
  echo "fetch_min_available_gb_clamped_from=${fetch_min_available_gb} to=${min_safe_fetch_available_gb}"
  fetch_min_available_gb="${min_safe_fetch_available_gb}"
fi
if (( max_swap_used_gb > max_safe_swap_used_gb )); then
  echo "max_swap_used_gb_clamped_from=${max_swap_used_gb} to=${max_safe_swap_used_gb}"
  max_swap_used_gb="${max_safe_swap_used_gb}"
fi

echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "prefetch_start=${prefetch_start}"
echo "prefetch_end=${prefetch_end}"
echo "run_tag=${run_tag}"
echo "month_modulo=${month_modulo}"
echo "month_remainder=${month_remainder}"
echo "fetch_workers=${fetch_workers}"
echo "fetch_min_available_gb=${fetch_min_available_gb}"
echo "max_safe_fetch_workers=${max_safe_fetch_workers}"
echo "max_swap_used_gb=${max_swap_used_gb}"
echo "max_safe_swap_used_gb=${max_safe_swap_used_gb}"
echo "heavy_lock_file=${heavy_lock_file}"

mem_available_gb() {
  awk '/MemAvailable:/ {printf "%d", $2 / 1024 / 1024}' /proc/meminfo
}

swap_used_gb() {
  awk '
    /SwapTotal:/ {total=$2}
    /SwapFree:/ {free=$2}
    END {printf "%d", (total - free) / 1024 / 1024}
  ' /proc/meminfo
}

wait_for_resource_headroom() {
  while true; do
    local available_gb swap_gb
    available_gb="$(mem_available_gb)"
    swap_gb="$(swap_used_gb)"
    echo "resource_check stage=prefetch available_gb=${available_gb} required_available_gb=${fetch_min_available_gb} swap_used_gb=${swap_gb} max_swap_used_gb=${max_swap_used_gb}"
    if (( available_gb >= fetch_min_available_gb && swap_gb <= max_swap_used_gb )); then
      return 0
    fi
    echo "resource_waiting_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) stage=prefetch"
    sleep "${resource_wait_seconds}"
  done
}

month_windows() {
  python3 - "$prefetch_start" "$prefetch_end" <<'PY'
from __future__ import annotations

import os
import sys
from datetime import date


def parse(value: str) -> date:
    y, m, d = map(int, value.split("-"))
    return date(y, m, d)


def add_month(value: date) -> date:
    y, m = value.year, value.month
    if m == 12:
        return date(y + 1, 1, 1)
    return date(y, m + 1, 1)


start = parse(sys.argv[1])
end = parse(sys.argv[2])
month_modulo = max(1, int(os.environ.get("MONTH_MODULO", "1")))
month_remainder = int(os.environ.get("MONTH_REMAINDER", "0"))
cursor = date(start.year, start.month, 1)
month_index = 0
while cursor < end:
    nxt = min(add_month(cursor), end)
    if month_index % month_modulo == month_remainder:
        print(cursor.isoformat(), nxt.isoformat())
    cursor = nxt
    month_index += 1
PY
}

while read -r start_date end_date; do
  [[ -z "${start_date}" || -z "${end_date}" ]] && continue
  label="$(echo "${start_date}_${end_date}" | tr -d '-' | tr ':' '_' | tr 'T' '_' | tr -d '+')"
  run_id="asia_gkg_window_${label}_${run_tag}"
  normalized_file="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}/asia_gkg_filtered.csv.gz"

  if [[ -s "${normalized_file}" ]] && gzip -t "${normalized_file}"; then
    echo "prefetch_skipped_existing=${normalized_file}"
    continue
  fi

  echo "prefetch_window_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) run_id=${run_id} start=${start_date} end=${end_date}"
  mkdir -p "$(dirname "${heavy_lock_file}")"
  (
    flock 8
    echo "heavy_lock_acquired_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) stage=prefetch"
    if [[ -s "${normalized_file}" ]] && gzip -t "${normalized_file}"; then
      echo "prefetch_skipped_existing_after_lock=${normalized_file}"
      exit 0
    fi
    wait_for_resource_headroom
    python3 scripts/news_shock_taxonomy/fetch_gdelt_gkg_asia_bulk.py \
      --run-id "${run_id}" \
      --start-date "${start_date}" \
      --end-date "${end_date}" \
      --timeout "${timeout_seconds}" \
      --retries "${retries}" \
      --sleep "${fetch_sleep}" \
      --workers "${fetch_workers}" \
      --master-refresh-seconds "${master_refresh_seconds}" \
      --no-keep-raw
    echo "heavy_lock_released_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) stage=prefetch"
  ) 8>"${heavy_lock_file}"
  gzip -t "${normalized_file}"
  echo "prefetch_window_done_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) run_id=${run_id}"
done < <(month_windows)

echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
