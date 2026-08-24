#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
PHASE="${PHASE:-all}"
exec .venv/bin/python scripts/build_ticker_research_panels.py --phase "$PHASE" --run-id "$RUN_ID" "$@"
