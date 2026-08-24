#!/usr/bin/env bash
set -euo pipefail

# Copy-only rescue for Google Drive trashed Sharpe-Renaissance backup files.
# This intentionally does not delete, purge, or untrash in-place. It copies
# trashed objects into a visible rescue folder so the backups remain accessible.

source_root="${SOURCE_ROOT:-gdrive:Machine_Archive/molina_workbench}"
rescue_root="${RESCUE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-trash-rescue-20260521}"

echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "source_root=${source_root}"
echo "rescue_root=${rescue_root}"

copy_trashed_tree() {
  local name="$1"
  echo "copy_start=${name} $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  rclone copy \
    --drive-trashed-only \
    "${source_root}/${name}" \
    "${rescue_root}/${name}" \
    --transfers 4 \
    --checkers 8 \
    --stats 30s \
    --stats-one-line
  echo "copy_done=${name} $(date -u +%Y-%m-%dT%H:%M:%SZ)"
}

copy_trashed_tree "Sharpe-Renaissance-deliverables"
copy_trashed_tree "Sharpe-Renaissance-data_lake"
copy_trashed_tree "Sharpe-Renaissance-raw_archives"

echo "visible_rescue_size_start $(date -u +%Y-%m-%dT%H:%M:%SZ)"
rclone size "${rescue_root}"
echo "visible_rescue_size_done $(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
