#!/usr/bin/env bash
# Render a systemd unit template with repo paths.
# Usage: render_systemd_unit.sh input.service output.service

set -euo pipefail

_SR_LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${_SR_LIB}/platform_env.sh"

in="${1:?input unit path}"
out="${2:?output unit path}"

mkdir -p "$(dirname "${out}")"
sed \
  -e "s|@REPO_ROOT@|${REPO_ROOT}|g" \
  -e "s|@SR_DIR@|${SR_DIR}|g" \
  -e "s|@KERNEL_DIR@|${KERNEL_DIR}|g" \
  -e "s|@ALPHA_DIR@|${ALPHA_DIR}|g" \
  -e "s|@DRIVE_DIR@|${DRIVE_DIR}|g" \
  -e "s|@VENV_PYTHON@|${SR_PYTHON}|g" \
  "${in}" > "${out}"
