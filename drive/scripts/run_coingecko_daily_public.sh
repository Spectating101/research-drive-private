#!/usr/bin/env bash
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
cd "$ROOT"

mkdir -p logs

exec env PYTHONUNBUFFERED=1 /usr/bin/python3 scripts/coingecko_panel_update.py \
  --mode daily \
  --use-public-api
