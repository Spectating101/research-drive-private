#!/usr/bin/env bash
# Install core research + alpha systemd user units (safe to re-run).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"

RENDER="${SCRIPT_DIR}/lib/render_systemd_unit.sh"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "${UNIT_DIR}"

install_pair() {
  local name="$1"
  "${RENDER}" "${SR_DIR}/systemd/${name}.service" "${UNIT_DIR}/${name}.service"
  if [[ -f "${SR_DIR}/systemd/${name}.timer" ]]; then
    "${RENDER}" "${SR_DIR}/systemd/${name}.timer" "${UNIT_DIR}/${name}.timer"
    systemctl --user enable --now "${name}.timer" 2>/dev/null || true
    echo "  enabled ${name}.timer"
  else
    systemctl --user enable "${name}.service" 2>/dev/null || true
    echo "  enabled ${name}.service"
  fi
}

echo "Installing to ${UNIT_DIR}"
echo "  SR_DIR=${SR_DIR}"
echo "  SR_PYTHON=${SR_PYTHON}"

for unit in alpha-live alpha-scorecard research-engine-audit investment-enforcement idn-social-sentiment-daily idn-empirical-research-weekly idn-fry-data-collector yzu-cluster-api yzu-cluster-worker; do
  if [[ -f "${SR_DIR}/systemd/${unit}.service" ]]; then
    install_pair "${unit}"
  fi
done

systemctl --user daemon-reload
echo "Done. Check: systemctl --user list-timers | rg 'alpha|research-engine|investment-enforcement|idn-'"
