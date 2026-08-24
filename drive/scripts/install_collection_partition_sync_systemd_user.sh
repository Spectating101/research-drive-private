#!/usr/bin/env bash
# Install collection-partition-sync systemd user timer (safe to re-run).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"

RENDER="${SCRIPT_DIR}/lib/render_systemd_unit.sh"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "${UNIT_DIR}" "${SR_DIR}/logs"

"${RENDER}" "${SR_DIR}/systemd/collection-partition-sync.service" "${UNIT_DIR}/collection-partition-sync.service"
"${RENDER}" "${SR_DIR}/systemd/collection-partition-sync.timer" "${UNIT_DIR}/collection-partition-sync.timer"

systemctl --user daemon-reload

SCHEDULED=0
if [[ -f "${SR_DIR}/config/partition_sync.json" ]]; then
  SCHEDULED="$("${SR_PYTHON}" -c "import json;print(int(json.load(open('${SR_DIR}/config/partition_sync.json')).get('scheduled',0)))")"
fi
if [[ "${SCHEDULED}" == "1" ]]; then
  systemctl --user enable --now collection-partition-sync.timer
  echo "  enabled collection-partition-sync.timer"
else
  systemctl --user disable --now collection-partition-sync.timer 2>/dev/null || true
  echo "  partition sync timer disabled (drive-first backfill_only)"
fi

echo "Installed collection-partition-sync units (manual: bash scripts/ops/run_partition_sync.sh)"
