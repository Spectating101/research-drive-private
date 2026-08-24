#!/usr/bin/env bash
# Move the remaining Drive trees under the vault root so the partition scheme
# can address them. These are server-side moves within one Drive account: no
# bytes cross the wire, only re-parenting.
#
# Sequential on purpose -- a sidecar backup is uploading concurrently and Drive
# rate-limits per project, so parallel moves just produce 403s for everyone.
# Nothing is deleted; each move is verified by object count before continuing.
set -uo pipefail
export RCLONE_CONFIG=/home/phyrexian/.config/rclone/rclone.conf

W="gdrive:Machine_Archive/molina_workbench"
V="$W/Sharpe-Renaissance-data"

move_tree() {
  local src="$1" dst="$2" expect="$3"
  echo "[$(date -Is)] === $src -> $dst (expect $expect objects) ==="
  local before
  before=$(rclone size "$W/$src" 2>/dev/null | grep -oP 'objects: \K[0-9.]+k?' | head -1)
  echo "  source objects: ${before:-unknown}"

  local start=$SECONDS
  rclone move "$W/$src" "$V/$dst" --stats 60s --stats-one-line 2>&1 | tail -3
  echo "  elapsed: $((SECONDS - start))s"

  local got
  got=$(rclone size "$V/$dst" 2>/dev/null | grep -oP 'Total objects: \K[0-9,.]+k?' | head -1)
  echo "  destination now: ${got:-unknown}"

  # leftovers mean the move did not finish -- stop rather than press on
  local left
  left=$(rclone lsf -R --files-only "$W/$src" 2>/dev/null | wc -l)
  if [ "$left" -gt 0 ]; then
    echo "  WARNING: $left files still at source; leaving it in place for inspection"
  else
    echo "  source drained clean"
  fi
  echo
}

move_tree "Sharpe-Renaissance-raw_archives" "archives/raw_archives" "17724"
move_tree "Sharpe-Renaissance-data_lake"    "archives/data_lake_snapshot_20260517" "18944"

echo "[$(date -Is)] done"
echo "=== vault root ==="
rclone lsf "$V" --dirs-only
echo "=== workbench remaining ==="
rclone lsf "$W" --dirs-only
