#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"

RENDER="${SCRIPT_DIR}/lib/render_systemd_unit.sh"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "${UNIT_DIR}"

for unit in news-shock-gdelt-expanded-fleet-monitor; do
  "${RENDER}" "${SR_DIR}/systemd/${unit}.service" "${UNIT_DIR}/${unit}.service"
  "${RENDER}" "${SR_DIR}/systemd/${unit}.timer" "${UNIT_DIR}/${unit}.timer"
done

chmod +x "${SR_DIR}/scripts/monitor_gdelt_expanded_fleet_health.sh"

systemctl --user daemon-reload
systemctl --user enable --now news-shock-gdelt-expanded-fleet-monitor.timer
systemctl --user start news-shock-gdelt-expanded-fleet-monitor.service || true

echo "Installed news-shock-gdelt-expanded-fleet-monitor.timer"
echo "Alert file: docs/status/generated/gdelt_expanded_fleet_alert.json"
echo "Log: logs/news_shock_taxonomy/expanded_work_steal/fleet_health_monitor.log"
systemctl --user list-timers --all | rg expanded-fleet || true
