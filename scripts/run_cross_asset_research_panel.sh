#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
exec .venv/bin/python scripts/build_cross_asset_research_panel.py --run-id "$RUN_ID" "$@"
