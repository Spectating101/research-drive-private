#!/usr/bin/env bash
set -euo pipefail

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
  --db-path data_lake/coingecko_archive/coingecko_professor_eth_2020.sqlite3 \
  --coin-id-file "Coin_Beg_Date (Ethereum).txt" \
  --coin-id-column coingecko_id \
  --coins-limit 0 \
  --exchange-limit 0 \
  --history-from 2020-01-01T00:00:00+00:00 \
  --history-to now \
  --history-chunk-days 365 \
  --skip-categories \
  --skip-coins-list \
  --skip-markets \
  --skip-exchanges \
  --min-interval-seconds 0.15 \
  --max-retries 8 \
  --retry-backoff-seconds 2.0 \
  --skip-existing-details \
  --skip-existing-history
