#!/usr/bin/env bash
set -euo pipefail
# Install paced fry background collector timer (safe to re-run).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"
RENDER="${SCRIPT_DIR}/lib/render_systemd_unit.sh"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "${UNIT_DIR}" "${SR_DIR}/logs" "${SR_DIR}/.locks"

chmod +x "${SR_DIR}/scripts/run_idn_fry_background_collector.sh"

for unit in idn-fry-data-collector; do
  "${RENDER}" "${SR_DIR}/systemd/${unit}.service" "${UNIT_DIR}/${unit}.service"
  "${RENDER}" "${SR_DIR}/systemd/${unit}.timer" "${UNIT_DIR}/${unit}.timer"
done

systemctl --user daemon-reload
systemctl --user enable --now idn-fry-data-collector.timer

echo "Installed idn-fry-data-collector.timer (3x/day, 15 broker calls/run by default)"
echo "  Status:  systemctl --user status idn-fry-data-collector.timer"
echo "  Logs:    tail -f ${SR_DIR}/logs/idn_fry_background_collector.log"
echo "  Tune:    edit ~/.config/systemd/user/idn-fry-data-collector.service Environment= lines"
systemctl --user status idn-fry-data-collector.timer --no-pager || true
