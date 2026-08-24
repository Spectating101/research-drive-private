#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 RUN_ID START_DATE END_DATE" >&2
  echo "example: $0 local_probe_20200801_20200802 2020-08-01 2020-08-02" >&2
  exit 2
fi

run_id="$1"
start_date="$2"
end_date="$3"

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

fetch_workers="${FETCH_WORKERS:-2}"
fetch_timeout="${FETCH_TIMEOUT:-180}"
fetch_retries="${FETCH_RETRIES:-3}"
fetch_sleep="${FETCH_SLEEP:-0.3}"
fetch_max_files="${FETCH_MAX_FILES:-0}"
score_chunk_size="${SCORE_CHUNK_SIZE:-50000}"
score_sample_size="${SCORE_SAMPLE_SIZE:-100}"
force="${FORCE:-0}"

export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"

norm_dir="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}"
proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"
normalized_file="${norm_dir}/asia_gkg_filtered.csv.gz"
scored_file="${proc_dir}/asia_gkg_scored.csv.gz"
daily_panel_file="${proc_dir}/daily_country_shock_panel.csv"
url_queue_file="${proc_dir}/url_enrichment_queue.csv.gz"

if [[ "${force}" != "1" && -s "${normalized_file}" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] && gzip -t "${normalized_file}" && gzip -t "${scored_file}" && gzip -t "${url_queue_file}"; then
  echo "local_fetch_score_outputs_already_exist=${run_id}"
  exit 0
fi

fetch_args=(
  --run-id "${run_id}"
  --start-date "${start_date}"
  --end-date "${end_date}"
  --timeout "${fetch_timeout}"
  --retries "${fetch_retries}"
  --sleep "${fetch_sleep}"
  --workers "${fetch_workers}"
  --master-refresh-seconds 86400
  --no-keep-raw
)

if (( fetch_max_files > 0 )); then
  fetch_args+=(--max-files "${fetch_max_files}")
fi

echo "local_worker_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "run_id=${run_id}"
echo "start_date=${start_date}"
echo "end_date=${end_date}"
echo "fetch_workers=${fetch_workers}"
echo "fetch_max_files=${fetch_max_files}"

python3 scripts/news_shock_taxonomy/fetch_gdelt_gkg_asia_bulk.py "${fetch_args[@]}"

python3 scripts/news_shock_taxonomy/score_gdelt_gkg_asia.py \
  --input "${normalized_file}" \
  --run-id "${run_id}" \
  --chunk-size "${score_chunk_size}" \
  --sample-size "${score_sample_size}"

gzip -t "${normalized_file}"
gzip -t "${scored_file}"
gzip -t "${url_queue_file}"
[[ -s "${daily_panel_file}" ]]

echo "local_worker_finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "normalized_dir=${norm_dir}"
echo "processed_dir=${proc_dir}"
