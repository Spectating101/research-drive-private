#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/../lib/platform_env.sh"
cd "${SR_DIR}"
exec "${SR_PYTHON}" -m scripts.yzu_cluster.cli "${@:-components}"
