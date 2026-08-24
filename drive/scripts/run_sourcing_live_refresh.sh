#!/usr/bin/env bash
# Refresh Zenodo + Taiwan gov live scrape exemplars and rebuild scrape FTS.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
.venv/bin/python scripts/research_data_mcp/sourcing_live_refresh.py --repo "$ROOT" "$@"
