#!/usr/bin/env bash
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
DRIVE_ROOT="${SHARPE_REDDIT_DRIVE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/social/reddit}"

cd "${SR_DIR}"

mkdir -p data_lake/sentiment
python3 scripts/reddit_data_health.py >/dev/null

if command -v rclone >/dev/null 2>&1; then
  if [[ -d data_lake/sentiment/reddit ]]; then
    rclone copy data_lake/sentiment/reddit "${DRIVE_ROOT}/raw/reddit" --stats-one-line
  fi
  for path in \
    data_lake/sentiment/reddit_ingest.sqlite \
    data_lake/sentiment/reddit_daily_signals.parquet \
    data_lake/sentiment/reddit_daily_signals.csv \
    data_lake/sentiment/reddit_health.json \
    data_lake/sentiment/reddit_health.md
  do
    if [[ -f "${path}" ]]; then
      rclone copyto "${path}" "${DRIVE_ROOT}/$(basename "${path}")" --stats-one-line
    fi
  done
else
  echo "rclone not found; skipping Drive sync" >&2
fi
