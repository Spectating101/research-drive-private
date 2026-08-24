#!/usr/bin/env bash
# Approve desk-safe pending jobs (DataCite, probe, short queue tasks).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/platform_env.sh
source "${SCRIPT_DIR}/../lib/platform_env.sh"
cd "${SR_DIR}"
APPLY=0
if [[ "${1:-}" == "--apply" ]]; then
  APPLY=1
fi
ARGS=(--approve-safe --dry-run)
if (( APPLY )); then
  ARGS=(--approve-safe)
fi
"${SR_DIR}/.venv/bin/python" scripts/yzu_cluster/triage_pending_jobs.py "${ARGS[@]}"
if (( APPLY )); then
  echo "Triggering worker tick for queued jobs…"
  "${SR_DIR}/.venv/bin/python" -c "from scripts.research_data_mcp.bootstrap import create_stack; s=create_stack(); [s.jobs.tick() for _ in range(3)]"
fi
