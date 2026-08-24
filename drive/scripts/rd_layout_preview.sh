#!/usr/bin/env bash
# CLI layout wireframes — stdlib Python, no browser. See docs/design/LAYOUT_SPEC.md
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"
exec "${SR_PYTHON}" "${SR_DIR}/scripts/rd_layout_preview.py" "${@:-library}"
