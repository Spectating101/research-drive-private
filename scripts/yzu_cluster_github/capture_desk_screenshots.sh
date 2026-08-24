#!/usr/bin/env bash
# Capture Research Drive screenshots for ChatGPT visual review.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "${SCRIPT_DIR}/../../drive/src/v2/main.jsx" ]]; then
  ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
  MJS="${SCRIPT_DIR}/capture_desk_screenshots.mjs"
elif [[ -f "${SCRIPT_DIR}/../drive/src/v2/main.jsx" ]]; then
  ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
  MJS="${SCRIPT_DIR}/capture_desk_screenshots.mjs"
else
  echo "Could not locate drive/src — run from yzu-cluster or Sharpe-Renaissance" >&2
  exit 1
fi
cd "$ROOT"

DESK_URL="${YZU_DESK_URL:-http://127.0.0.1:5179}"
API_URL="${YZU_API_URL:-http://127.0.0.1:8765}"

if ! curl -sf --max-time 3 "${DESK_URL}/" >/dev/null 2>&1; then
  echo "Desk not reachable at ${DESK_URL}" >&2
  echo "Start the full desk from Sharpe-Renaissance:" >&2
  echo "  bash scripts/run_yzu_cluster.sh" >&2
  echo "Or UI only (demo fallback): npm run dev" >&2
  exit 1
fi

if [[ "${YZU_REQUIRE_LIVE:-}" == "1" ]]; then
  if ! curl -sf --max-time 15 "${API_URL}/health?live=1" | grep -qE '"status"[[:space:]]*:[[:space:]]*"ok"'; then
    echo "YZU_REQUIRE_LIVE=1 but API not healthy at ${API_URL}" >&2
    echo "Start: bash scripts/run_yzu_cluster.sh  (from Sharpe-Renaissance monorepo)" >&2
    exit 1
  fi
  echo "live gate: API ok at ${API_URL}"
fi

if [[ ! -d node_modules/@playwright ]]; then
  npm install
  npx playwright install chromium
fi

YZU_DESK_URL="$DESK_URL" YZU_REQUIRE_LIVE="${YZU_REQUIRE_LIVE:-}" node "$MJS"
