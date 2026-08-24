#!/usr/bin/env bash
# Copy Refinitiv value-harvest runs to GDrive vault (no delete on remote).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

REMOTE_ROOT="${REFINITIV_GDRIVE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/refinitiv_backfill}"

RUNS=(
  "2026-07-06-complete"
  "2026-07-06-value-v2"
  "2026-07-06-scale"
  "2026-07-06-fundamentals"
  "rescued_desktop_20251215"
)

echo "Remote root: ${REMOTE_ROOT}"

for run in "${RUNS[@]}"; do
  src="data_lake/refinitiv_backfill/${run}"
  if [[ ! -d "${src}" ]]; then
    echo "skip missing ${src}"
    continue
  fi
  echo "==> copy ${run}"
  rclone copy "${src}" "${REMOTE_ROOT}/${run}" --transfers 4 --checkers 8 --stats-one-line
done

# Manifest index for professors/agents
INDEX="data_lake/refinitiv_backfill/INDEX.json"
if [[ -f "${INDEX}" ]]; then
  rclone copyto "${INDEX}" "${REMOTE_ROOT}/INDEX.json" --stats-one-line
fi

echo "done"
