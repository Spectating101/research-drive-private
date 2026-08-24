#!/usr/bin/env bash
set -euo pipefail

# Long-running copy-only data backlog for the 5TB Drive archive.
# This is intentionally conservative:
# - no rclone sync
# - no paid credentials
# - monthly GDELT windows so failure loses at most one chunk
# - old GDELT raw zips are not retained for long history; filtered/scored data is retained

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

started_tag="${RUN_TAG:-$(date -u +%Y%m%dT%H%M%SZ)}"
log_dir="logs/data_backlog"
mkdir -p "${log_dir}"
log_file="${log_dir}/always_on_backlog_${started_tag}.log"

remote_root="${REMOTE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data}"
backfill_start="${BACKFILL_START:-2024-01-01}"
backfill_end="${BACKFILL_END:-2026-06-01}"
min_free_gb="${MIN_FREE_GB:-70}"
max_enrich_urls="${MAX_ENRICH_URLS:-300}"
fetch_sleep="${FETCH_SLEEP:-0.2}"
fetch_workers="${FETCH_WORKERS:-1}"
skip_controls="${SKIP_CONTROLS:-0}"
month_modulo="${MONTH_MODULO:-1}"
month_remainder="${MONTH_REMAINDER:-0}"
max_safe_fetch_workers="${MAX_SAFE_FETCH_WORKERS:-2}"
fetch_min_available_gb="${FETCH_MIN_AVAILABLE_GB:-12}"
score_min_available_gb="${SCORE_MIN_AVAILABLE_GB:-16}"
max_swap_used_gb="${MAX_SWAP_USED_GB:-1}"
max_safe_swap_used_gb="${MAX_SAFE_SWAP_USED_GB:-12}"

if (( fetch_workers > max_safe_fetch_workers )); then
  echo "fetch_workers_clamped_from=${fetch_workers} to=${max_safe_fetch_workers}"
  fetch_workers="${max_safe_fetch_workers}"
fi
if (( max_swap_used_gb > max_safe_swap_used_gb )); then
  echo "max_swap_used_gb_clamped_from=${max_swap_used_gb} to=${max_safe_swap_used_gb}"
  max_swap_used_gb="${max_safe_swap_used_gb}"
fi

echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "log_file=${log_file}"
echo "remote_root=${remote_root}"
echo "backfill_start=${backfill_start}"
echo "backfill_end=${backfill_end}"
echo "min_free_gb=${min_free_gb}"
echo "max_enrich_urls=${max_enrich_urls}"
echo "fetch_sleep=${fetch_sleep}"
echo "fetch_workers=${fetch_workers}"
echo "max_safe_fetch_workers=${max_safe_fetch_workers}"
echo "fetch_min_available_gb=${fetch_min_available_gb}"
echo "score_min_available_gb=${score_min_available_gb}"
echo "max_swap_used_gb=${max_swap_used_gb}"
echo "max_safe_swap_used_gb=${max_safe_swap_used_gb}"
echo "skip_controls=${skip_controls}"
echo "month_modulo=${month_modulo}"
echo "month_remainder=${month_remainder}"

if ! command -v rclone >/dev/null 2>&1; then
  echo "rclone not found" >&2
  exit 1
fi

wait_for_current_news_copy() {
  while pgrep -f '[r]clone copy data_lake/news_shock_taxonomy/raw' >/dev/null 2>&1; do
    echo "waiting_for_existing_news_raw_copy=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    sleep 60
  done
}

require_disk() {
  local free_kb
  free_kb="$(df --output=avail -k / | tail -n 1 | tr -d ' ')"
  local free_gb=$((free_kb / 1024 / 1024))
  echo "local_free_gb=${free_gb}"
  if (( free_gb < min_free_gb )); then
    echo "stopping: local free space below ${min_free_gb} GB" >&2
    exit 75
  fi
}

copy_markets_and_controls() {
  echo "refresh_public_macro_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 scripts/download_public_macro_market_baseline.py
  rclone copy data_lake/public_macro_market_baseline \
    "${remote_root}/official_macro_asia/public_macro_market_baseline" \
    --transfers 4 --checkers 8 --stats-one-line

  echo "refresh_twse_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 scripts/fetch_twse_openapi_taiwan_market_layer.py --copy-drive

  echo "refresh_asia_yfinance_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 scripts/fetch_accessible_market_universes.py \
    --config config/markets/asia_yfinance_universes.json \
    --out-root data_lake/markets/yfinance_asia \
    --period 10y \
    --interval 1d \
    --batch-size 50 \
    --sleep 0.3 \
    --write-parquet
  rclone copy data_lake/markets/yfinance_asia \
    "${remote_root}/market_data/yfinance_asia" \
    --transfers 4 --checkers 8 --stats-one-line

  echo "refresh_asia_holdings_universe_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 scripts/fetch_asia_sourced_universes.py --validate
  rclone copy data_lake/markets/sourced_universes \
    "${remote_root}/market_data/sourced_universes" \
    --transfers 4 --checkers 8 --stats-one-line

  echo "refresh_entity_mapping_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  python3 scripts/build_asia_entity_mapping_layer.py --copy-drive
}

run_gdelt_window() {
  local start_date="$1"
  local end_date="$2"
  local label
  label="$(echo "${start_date}_${end_date}" | tr -d '-' | tr ':' '_' | tr 'T' '_' | tr -d '+')"
  local run_id="asia_gkg_window_${label}_${started_tag}"

  require_disk
  echo "gdelt_window_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) run_id=${run_id} start=${start_date} end=${end_date}"
  KEEP_RAW=0 \
  MASTER_REFRESH_SECONDS=86400 \
  TIMEOUT_SECONDS=300 \
  RETRIES=4 \
  FETCH_SLEEP="${fetch_sleep}" \
  FETCH_WORKERS="${fetch_workers}" \
  MAX_SAFE_FETCH_WORKERS="${max_safe_fetch_workers}" \
  FETCH_MIN_AVAILABLE_GB="${fetch_min_available_gb}" \
  SCORE_MIN_AVAILABLE_GB="${score_min_available_gb}" \
  MAX_SWAP_USED_GB="${max_swap_used_gb}" \
  MAX_ENRICH_URLS="${max_enrich_urls}" \
    scripts/run_news_shock_gkg_window_pipeline.sh "${run_id}" "${start_date}" "${end_date}"

  echo "gdelt_window_archive_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) run_id=${run_id}"
  RUN_ID="${run_id}" INCLUDE_RAW=0 scripts/sync_news_shock_taxonomy_drive.sh
  echo "gdelt_window_done_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) run_id=${run_id}"
}

month_windows() {
  python3 - "$backfill_start" "$backfill_end" <<'PY'
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

wait_for_current_news_copy
require_disk
if [[ "${skip_controls}" == "1" ]]; then
  echo "copy_markets_and_controls_skipped_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
else
  copy_markets_and_controls
fi

while read -r start_date end_date; do
  [[ -z "${start_date}" || -z "${end_date}" ]] && continue
  run_gdelt_window "${start_date}" "${end_date}"
done < <(month_windows)

if [[ "${skip_controls}" == "1" ]]; then
  echo "final_copy_markets_and_controls_skipped_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
else
  copy_markets_and_controls
fi

echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
