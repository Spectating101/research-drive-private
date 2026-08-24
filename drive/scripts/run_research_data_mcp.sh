#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"
cd "${SR_DIR}"

for env_file in \
  "${SR_DIR}/.env.local" \
  "${SR_DIR}/../.env.local" \
  "${HOME}/.env.local"; do
  if [[ -f "${env_file}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${env_file}"
    set +a
    break
  fi
done

if ! "${SR_PYTHON}" -c "import mcp" 2>/dev/null; then
  echo "research-data MCP: missing Python package 'mcp' for ${SR_PYTHON}" >&2
  echo "  fix: ${SR_DIR}/.venv/bin/pip install 'mcp>=1.26.0'" >&2
  exit 1
fi

exec "${SR_PYTHON}" -m scripts.research_data_mcp.server --transport "${RESEARCH_MCP_TRANSPORT:-stdio}"
