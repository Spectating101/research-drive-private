#!/usr/bin/env bash
# Mirror local/cache partitions → GDrive (pull cluster rsync, then rclone copy+verify).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/../lib/platform_env.sh"

LOCK_NAME="${PARTITION_SYNC_LOCK:-collection_partition_sync.lock}"
LOCK_FILE="${XDG_RUNTIME_DIR:-/tmp}/${LOCK_NAME}"
LOG_DIR="${SR_DIR}/logs"
mkdir -p "${LOG_DIR}"
LOG_FILE="${LOG_DIR}/partition_sync.log"

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "[skip] partition sync lock held (${LOCK_FILE})"
  exit 0
fi

echo "[partition-sync] $(date -Is) start args=$*"
"${SR_PYTHON}" "${SR_DIR}/scripts/ops/sync_collection_partitions_to_gdrive.py" \
  --all \
  --update-partition-status \
  "$@" \
  2>&1 | tee -a "${LOG_FILE}"
rc=${PIPESTATUS[0]}
echo "[partition-sync] $(date -Is) exit=${rc}"
exit "${rc}"
