#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"
cd "${SR_DIR}"
exec "${SR_PYTHON}" -m scripts.research_query_engine.server \
  --host "${RQE_HOST:-127.0.0.1}" \
  --port "${RQE_PORT:-8765}" \
  --registry "${RQE_REGISTRY:-config/research_query_registry.json}" \
  --serve-ui
