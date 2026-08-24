#!/usr/bin/env bash
# Install YZU cluster API + background worker as persistent user systemd services.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"

RENDER="${SCRIPT_DIR}/lib/render_systemd_unit.sh"
UNIT_DIR="${HOME}/.config/systemd/user"
mkdir -p "${UNIT_DIR}"

echo "Installing YZU cluster units to ${UNIT_DIR}"
echo "  SR_DIR=${SR_DIR}"
echo "  SR_PYTHON=${SR_PYTHON}"

for unit in yzu-cluster-api yzu-cluster-worker; do
  "${RENDER}" "${SR_DIR}/systemd/${unit}.service" "${UNIT_DIR}/${unit}.service"
  systemctl --user enable --now "${unit}.service" 2>/dev/null || systemctl --user enable "${unit}.service"
  echo "  enabled ${unit}.service"
done

if [[ "${1:-}" == "--prod" ]]; then
  echo "building production UI (npm run build)…"
  (cd "${SR_DIR}" && npm run build)
fi

systemctl --user daemon-reload
systemctl --user restart yzu-cluster-api.service yzu-cluster-worker.service 2>/dev/null || true

echo ""
echo "YZU cluster systemd ready."
echo "  API:    curl -s http://127.0.0.1:8765/health"
echo "  status: curl -s http://127.0.0.1:8765/yzu/status | head"
echo "  logs:   journalctl --user -u yzu-cluster-api -u yzu-cluster-worker -f"
echo "  stop:   systemctl --user stop yzu-cluster-api yzu-cluster-worker"
