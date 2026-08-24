#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"

RENDER="${SCRIPT_DIR}/lib/render_systemd_unit.sh"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "${UNIT_DIR}"

chmod +x "${SR_DIR}/scripts/ops/desk_io_guard.sh"
chmod +x "${SR_DIR}/scripts/ops/disk_health_check.sh"

for unit in desk-io-guard; do
  "${RENDER}" "${SR_DIR}/systemd/${unit}.service" "${UNIT_DIR}/${unit}.service"
  "${RENDER}" "${SR_DIR}/systemd/${unit}.timer" "${UNIT_DIR}/${unit}.timer"
done

systemctl --user daemon-reload
systemctl --user enable --now desk-io-guard.timer
systemctl --user start desk-io-guard.service || true

echo "Installed desk-io-guard.timer (every 3 min)"
echo "Manual health: bash scripts/ops/disk_health_check.sh"
systemctl --user list-timers --all | rg desk-io-guard || true
