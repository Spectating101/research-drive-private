#!/usr/bin/env bash
# React reference desk (src/main.jsx) — Vite dev on :5178, API proxied to :8765.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"
cd "${SR_DIR}"

API_PORT="${YZU_API_PORT:-8765}"
if ! curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
  echo "API not on :${API_PORT} — start scripts/run_yzu_cluster_prod.sh first" >&2
  exit 1
fi

if [[ ! -d node_modules ]]; then
  npm install
fi

echo "React reference desk → http://127.0.0.1:5178/  (API via /api → :${API_PORT})"
exec npm run dev
