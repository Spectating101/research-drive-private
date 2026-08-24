#!/usr/bin/env bash
set -euo pipefail

run_id="${1:-asia_gkg_7d_pilot_$(date -u +%Y%m%dT%H%M%SZ)}"
hours="${HOURS:-168}"
timeout_seconds="${TIMEOUT_SECONDS:-90}"
retries="${RETRIES:-3}"
fetch_sleep="${FETCH_SLEEP:-0.2}"
max_enrich_urls="${MAX_ENRICH_URLS:-500}"

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

echo "run_id=${run_id}"
echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 scripts/news_shock_taxonomy/fetch_gdelt_gkg_asia_bulk.py \
  --run-id "${run_id}" \
  --hours "${hours}" \
  --timeout "${timeout_seconds}" \
  --retries "${retries}" \
  --sleep "${fetch_sleep}"

python3 scripts/news_shock_taxonomy/score_gdelt_gkg_asia.py \
  --input "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}/asia_gkg_filtered.csv.gz" \
  --run-id "${run_id}"

python3 scripts/news_shock_taxonomy/enrich_gdelt_gkg_urls_local.py \
  --queue "data_lake/news_shock_taxonomy/processed/${run_id}/url_enrichment_queue.csv.gz" \
  --decisions enrich_high_priority \
  --max-urls "${max_enrich_urls}" \
  --timeout 15 \
  --max-bytes 600000 \
  --sleep 0.2 \
  --per-domain-delay 1.0

echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
