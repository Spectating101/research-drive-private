#!/usr/bin/env bash
# Prepare spectator engine on a cluster node: node deps + staging dirs.
set -euo pipefail

SR_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MOLINA_REPO="${MOLINA_REPO:-$(cd "$SR_ROOT/.." && pwd)}"
STAGING="$SR_ROOT/data_lake/spectator_engine"

echo "Sharpe-Renaissance: $SR_ROOT"
echo "Molina-Optiplex:    $MOLINA_REPO"
echo "Staging:            $STAGING"

mkdir -p "$STAGING/src/data" "$MOLINA_REPO/src/data"

if ! command -v node >/dev/null 2>&1; then
  echo "WARN: node not on PATH — install Node 18+ before scraper_run jobs"
  exit 1
fi

if [[ ! -d "$MOLINA_REPO/node_modules/sqlite3" ]]; then
  echo "Installing Molina node_modules (sqlite, puppeteer stack)..."
  (cd "$MOLINA_REPO" && npm install --no-audit --no-fund)
fi

chmod +x "$SR_ROOT/scripts/yzu_cluster/workers/scraper_dispatch.sh"
echo "Spectator engine ready on $(hostname -s)"
