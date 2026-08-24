#!/usr/bin/env bash
# One-time / repeat setup: venv, editable install, env file, systemd alpha spine, health check.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"

SKIP_TESTS="${SKIP_TESTS:-0}"
SKIP_SYSTEMD="${SKIP_SYSTEMD:-0}"

echo "==> Sharpe-Renaissance platform setup"
echo "    SR_DIR=${SR_DIR}"

if [[ ! -d "${SR_DIR}/.venv" ]]; then
  echo "==> Creating venv"
  python3 -m venv "${SR_DIR}/.venv"
fi

echo "==> Installing package (editable)"
if ! "${SR_PYTHON}" -m pip install -q -e "${SR_DIR}" 2>/dev/null; then
  if "${SR_PYTHON}" -c "import src.research.fingerprint" 2>/dev/null; then
    echo "WARN: pip install failed (often disk); imports OK via PYTHONPATH/venv — continuing"
  else
    echo "ERROR: pip install failed and src.research is not importable"
    exit 1
  fi
fi

if [[ ! -f "${SR_DIR}/.env" && -f "${SR_DIR}/.env.example" ]]; then
  cp "${SR_DIR}/.env.example" "${SR_DIR}/.env"
  echo "==> Created ${SR_DIR}/.env from .env.example"
fi

if [[ "${SKIP_TESTS}" != "1" ]]; then
  echo "==> Running tests"
  if ! "${SR_PYTHON}" -m pytest "${SR_DIR}/tests/" -q --tb=line; then
    echo "WARN: some tests failed — platform may still run; fix before promoting signals"
  fi
fi

if [[ "${SKIP_SYSTEMD}" != "1" ]]; then
  echo "==> Installing alpha systemd user units"
  bash "${SR_DIR}/scripts/install_platform_systemd_user.sh"
fi

echo "==> Running research engine audit"
"${SR_PYTHON}" "${SR_DIR}/scripts/investment_research_engine_audit.py" || true

echo ""
"${SR_PYTHON}" "${SR_DIR}/scripts/platform_status.py"
echo ""
echo "Done. Daily alpha: systemctl --user status alpha-live.timer"
