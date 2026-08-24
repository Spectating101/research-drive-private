#!/usr/bin/env bash
set -euo pipefail

# Low-priority sidecar for non-GDELT public datasets. This keeps the lighter
# macro, market, disclosure, entity, and social layers fresh while heavy GDELT
# backfills run. All remote writes are copy-only.

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

remote_root="${REMOTE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data}"
lock_file="${LOCK_FILE:-.locks/public_data_sidecar_20260525.lock}"
min_free_gb="${MIN_FREE_GB:-30}"
skip_yfinance="${SKIP_YFINANCE:-0}"
skip_reddit_sync="${SKIP_REDDIT_SYNC:-0}"

mkdir -p "$(dirname "${lock_file}")" logs/data_backlog

require_disk() {
  local free_kb free_gb
  free_kb="$(df --output=avail -k / | tail -n 1 | tr -d ' ')"
  free_gb=$((free_kb / 1024 / 1024))
  echo "local_free_gb=${free_gb}"
  if (( free_gb < min_free_gb )); then
    echo "stopping: local free space below ${min_free_gb} GB" >&2
    exit 75
  fi
}

run_step() {
  local name="$1"
  shift
  require_disk
  echo "step_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) name=${name}"
  "$@"
  echo "step_finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) name=${name}"
}

main() {
  echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "remote_root=${remote_root}"
  echo "skip_yfinance=${skip_yfinance}"
  echo "skip_reddit_sync=${skip_reddit_sync}"

  run_step public_macro python3 scripts/download_public_macro_market_baseline.py
  run_step public_macro_drive rclone copy data_lake/public_macro_market_baseline \
    "${remote_root}/official_macro_asia/public_macro_market_baseline" \
    --transfers 4 --checkers 8 --stats-one-line

  run_step twse_openapi python3 scripts/fetch_twse_openapi_taiwan_market_layer.py --copy-drive

  if [[ "${skip_yfinance}" != "1" ]]; then
    run_step asia_yfinance python3 scripts/fetch_accessible_market_universes.py \
      --config config/markets/asia_yfinance_universes.json \
      --out-root data_lake/markets/yfinance_asia \
      --period 10y \
      --interval 1d \
      --batch-size 50 \
      --sleep 0.3 \
      --write-parquet
    run_step asia_yfinance_drive rclone copy data_lake/markets/yfinance_asia \
      "${remote_root}/market_data/yfinance_asia" \
      --transfers 4 --checkers 8 --stats-one-line
  fi

  run_step asia_sourced_universes python3 scripts/fetch_asia_sourced_universes.py --validate
  run_step asia_sourced_universes_drive rclone copy data_lake/markets/sourced_universes \
    "${remote_root}/market_data/sourced_universes" \
    --transfers 4 --checkers 8 --stats-one-line

  run_step asia_entity_mapping python3 scripts/build_asia_entity_mapping_layer.py --copy-drive

  if [[ "${skip_reddit_sync}" != "1" ]]; then
    run_step reddit_drive_sync bash scripts/sync_reddit_sentiment_drive.sh
  fi

  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

(
  flock -n 9 || {
    echo "public data sidecar already running: ${lock_file}" >&2
    exit 0
  }
  main
) 9>"${lock_file}"
