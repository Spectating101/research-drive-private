#!/usr/bin/env bash
# Golden procure path — requires API :8765 + worker.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SR_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "$SR_ROOT"
export PYTHONPATH="${SR_ROOT}:${SR_ROOT}/kernel:${SR_ROOT}/drive${PYTHONPATH:+:$PYTHONPATH}"
exec "${SR_ROOT}/.venv/bin/python" "${SCRIPT_DIR}/desk_golden_procure_path.py" "$@"
