#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <coin-id-file> <db-path>" >&2
  exit 2
fi

COIN_ID_FILE="$1"
DB_PATH="$2"

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
cd "$ROOT"

set -a
source .env.local
set +a

exec env PYTHONUNBUFFERED=1 python3 scripts/coingecko_bulk_collect.py \
  --db-path "$DB_PATH" \
  --coin-id-file "$COIN_ID_FILE" \
  --coins-limit 0 \
  --exchange-limit 0 \
  --history-from 2009-01-01T00:00:00+00:00 \
  --history-to now \
  --history-chunk-days 365 \
  --skip-categories \
  --skip-coins-list \
  --skip-markets \
  --skip-coin-details \
  --skip-exchanges \
  --min-interval-seconds 0.15 \
  --max-retries 8 \
  --retry-backoff-seconds 2.0 \
  --skip-existing-history
