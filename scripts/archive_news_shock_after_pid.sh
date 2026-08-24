#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 PIPELINE_PID RUN_ID" >&2
  exit 2
fi

pipeline_pid="$1"
run_id="$2"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

echo "watch_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "pipeline_pid=${pipeline_pid}"
echo "run_id=${run_id}"

while ps -p "${pipeline_pid}" >/dev/null 2>&1; do
  sleep 60
done

echo "pipeline_exited_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

gzip -t "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}/asia_gkg_filtered.csv.gz"
gzip -t "data_lake/news_shock_taxonomy/processed/${run_id}/asia_gkg_scored.csv.gz"
gzip -t "data_lake/news_shock_taxonomy/processed/${run_id}/url_enrichment_enrich_high_priority.csv.gz"

scripts/sync_news_shock_taxonomy_drive.sh

echo "drive_copy_done_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
