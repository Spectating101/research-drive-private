#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 RUN_ID START_DATE END_DATE" >&2
  echo "example: $0 asia_gkg_2025_01 2025-01-01 2025-02-01" >&2
  exit 2
fi

run_id="$1"
start_date="$2"
end_date="$3"
timeout_seconds="${TIMEOUT_SECONDS:-120}"
retries="${RETRIES:-4}"
fetch_sleep="${FETCH_SLEEP:-0.15}"
fetch_workers="${FETCH_WORKERS:-2}"
max_enrich_urls="${MAX_ENRICH_URLS:-300}"
keep_raw="${KEEP_RAW:-0}"
master_refresh_seconds="${MASTER_REFRESH_SECONDS:-86400}"
reuse_existing="${REUSE_EXISTING:-1}"
score_lock_file="${SCORE_LOCK_FILE:-.locks/news_shock_score.lock}"
score_offload_node="${SCORE_OFFLOAD_NODE:-}"
score_min_available_gb="${SCORE_MIN_AVAILABLE_GB:-16}"
fetch_min_available_gb="${FETCH_MIN_AVAILABLE_GB:-12}"
enrich_min_available_gb="${ENRICH_MIN_AVAILABLE_GB:-10}"
min_safe_score_available_gb="${MIN_SAFE_SCORE_AVAILABLE_GB:-16}"
min_safe_fetch_available_gb="${MIN_SAFE_FETCH_AVAILABLE_GB:-12}"
max_safe_fetch_workers="${MAX_SAFE_FETCH_WORKERS:-2}"
max_swap_used_gb="${MAX_SWAP_USED_GB:-1}"
max_safe_swap_used_gb="${MAX_SAFE_SWAP_USED_GB:-12}"
resource_wait_seconds="${RESOURCE_WAIT_SECONDS:-120}"
heavy_lock_file="${HEAVY_LOCK_FILE:-.locks/news_shock_heavy.lock}"

if (( fetch_workers > max_safe_fetch_workers )); then
  echo "fetch_workers_clamped_from=${fetch_workers} to=${max_safe_fetch_workers}"
  fetch_workers="${max_safe_fetch_workers}"
fi
if (( score_min_available_gb < min_safe_score_available_gb )); then
  echo "score_min_available_gb_clamped_from=${score_min_available_gb} to=${min_safe_score_available_gb}"
  score_min_available_gb="${min_safe_score_available_gb}"
fi
if (( fetch_min_available_gb < min_safe_fetch_available_gb )); then
  echo "fetch_min_available_gb_clamped_from=${fetch_min_available_gb} to=${min_safe_fetch_available_gb}"
  fetch_min_available_gb="${min_safe_fetch_available_gb}"
fi
if (( max_swap_used_gb > max_safe_swap_used_gb )); then
  echo "max_swap_used_gb_clamped_from=${max_swap_used_gb} to=${max_safe_swap_used_gb}"
  max_swap_used_gb="${max_safe_swap_used_gb}"
fi

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

export MALLOC_ARENA_MAX="${MALLOC_ARENA_MAX:-2}"
export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"

normalized_file="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}/asia_gkg_filtered.csv.gz"
scored_file="data_lake/news_shock_taxonomy/processed/${run_id}/asia_gkg_scored.csv.gz"
daily_panel_file="data_lake/news_shock_taxonomy/processed/${run_id}/daily_country_shock_panel.csv"
url_queue_file="data_lake/news_shock_taxonomy/processed/${run_id}/url_enrichment_queue.csv.gz"
url_enriched_file="data_lake/news_shock_taxonomy/processed/${run_id}/url_enrichment_enrich_high_priority.csv.gz"

fetch_args=(
  --run-id "${run_id}"
  --start-date "${start_date}"
  --end-date "${end_date}"
  --timeout "${timeout_seconds}"
  --retries "${retries}"
  --sleep "${fetch_sleep}"
  --workers "${fetch_workers}"
  --master-refresh-seconds "${master_refresh_seconds}"
)

if [[ "${keep_raw}" != "1" ]]; then
  fetch_args+=(--no-keep-raw)
fi

echo "run_id=${run_id}"
echo "start_date=${start_date}"
echo "end_date=${end_date}"
echo "keep_raw=${keep_raw}"
echo "reuse_existing=${reuse_existing}"
echo "fetch_workers=${fetch_workers}"
echo "score_lock_file=${score_lock_file}"
echo "score_offload_node=${score_offload_node}"
echo "score_min_available_gb=${score_min_available_gb}"
echo "fetch_min_available_gb=${fetch_min_available_gb}"
echo "enrich_min_available_gb=${enrich_min_available_gb}"
echo "max_safe_fetch_workers=${max_safe_fetch_workers}"
echo "max_swap_used_gb=${max_swap_used_gb}"
echo "max_safe_swap_used_gb=${max_safe_swap_used_gb}"
echo "heavy_lock_file=${heavy_lock_file}"
echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

mem_available_gb() {
  awk '/MemAvailable:/ {printf "%d", $2 / 1024 / 1024}' /proc/meminfo
}

swap_used_gb() {
  awk '
    /SwapTotal:/ {total=$2}
    /SwapFree:/ {free=$2}
    END {printf "%d", (total - free) / 1024 / 1024}
  ' /proc/meminfo
}

resource_snapshot() {
  local stage="$1"
  echo "resource_snapshot_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) stage=${stage} mem_available_gb=$(mem_available_gb) swap_used_gb=$(swap_used_gb)"
}

wait_for_resource_headroom() {
  local stage="$1"
  local min_available_gb="$2"
  while true; do
    local available_gb swap_gb
    available_gb="$(mem_available_gb)"
    swap_gb="$(swap_used_gb)"
    echo "resource_check stage=${stage} available_gb=${available_gb} required_available_gb=${min_available_gb} swap_used_gb=${swap_gb} max_swap_used_gb=${max_swap_used_gb}"
    if (( available_gb >= min_available_gb && swap_gb <= max_swap_used_gb )); then
      return 0
    fi
    echo "resource_waiting_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) stage=${stage}"
    sleep "${resource_wait_seconds}"
  done
}

fetch_needed=1
score_needed=1

if [[ "${reuse_existing}" == "1" && -s "${normalized_file}" ]] && gzip -t "${normalized_file}"; then
  echo "fetch_skipped_existing=${normalized_file}"
  fetch_needed=0
fi

if [[ "${reuse_existing}" == "1" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] && gzip -t "${scored_file}" && gzip -t "${url_queue_file}"; then
  echo "score_skipped_existing=${scored_file}"
  score_needed=0
fi
enrich_needed=1
if [[ "${reuse_existing}" == "1" && -s "${url_enriched_file}" ]] && gzip -t "${url_enriched_file}"; then
  enrich_needed=0
  echo "enrichment_skipped_existing=${url_enriched_file}"
fi

mkdir -p "$(dirname "${score_lock_file}")" "$(dirname "${heavy_lock_file}")"

if (( fetch_needed == 1 )); then
  wait_for_resource_headroom "fetch" "${fetch_min_available_gb}"
  resource_snapshot "before_fetch"
  python3 scripts/news_shock_taxonomy/fetch_gdelt_gkg_asia_bulk.py "${fetch_args[@]}"
  resource_snapshot "after_fetch"
fi

if (( score_needed == 1 )) && [[ -n "${score_offload_node}" ]]; then
  echo "score_offload_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) node=${score_offload_node}"
  scripts/run_news_shock_gkg_windows_score_offload.sh "${run_id}" "${score_offload_node}"
  if [[ -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] && gzip -t "${scored_file}" && gzip -t "${url_queue_file}"; then
    score_needed=0
    echo "score_offload_verified_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) node=${score_offload_node}"
  else
    echo "score_offload_outputs_missing=${run_id}" >&2
    exit 1
  fi
fi

# Keep score/enrich phases serialized while allowing parallel fetch across lanes.
if (( score_needed == 1 || enrich_needed == 1 )); then
  (
    flock 8
    echo "heavy_lock_acquired_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    resource_snapshot "heavy_lock_acquired"

    if (( score_needed == 1 )) && [[ "${reuse_existing}" == "1" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] && gzip -t "${scored_file}" && gzip -t "${url_queue_file}"; then
      echo "score_skipped_existing_after_lock=${scored_file}"
      score_needed=0
    fi
    if (( score_needed == 1 )); then
      (
        flock 9
        echo "score_lock_acquired_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
        wait_for_resource_headroom "score" "${score_min_available_gb}"
        if [[ "${reuse_existing}" == "1" && -s "${scored_file}" && -s "${daily_panel_file}" && -s "${url_queue_file}" ]] && gzip -t "${scored_file}" && gzip -t "${url_queue_file}"; then
          echo "score_skipped_existing_after_wait=${scored_file}"
        else
          resource_snapshot "before_score"
          python3 scripts/news_shock_taxonomy/score_gdelt_gkg_asia.py \
            --input "${normalized_file}" \
            --run-id "${run_id}"
          resource_snapshot "after_score"
        fi
        echo "score_lock_released_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      ) 9>"${score_lock_file}"
    else
      echo "score_recheck_skipped=${scored_file}"
    fi

    if (( enrich_needed == 0 )); then
      echo "enrichment_skipped_existing=${url_enriched_file}"
    else
      wait_for_resource_headroom "enrich" "${enrich_min_available_gb}"
      resource_snapshot "before_enrich"
      python3 scripts/news_shock_taxonomy/enrich_gdelt_gkg_urls_local.py \
        --queue "${url_queue_file}" \
        --decisions enrich_high_priority \
        --max-urls "${max_enrich_urls}" \
        --timeout 15 \
        --max-bytes 600000 \
        --sleep 0.2 \
        --per-domain-delay 1.0
      resource_snapshot "after_enrich"
    fi

    echo "heavy_lock_released_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  ) 8>"${heavy_lock_file}"
else
  echo "score_and_enrich_skipped_all=${run_id}"
fi

gzip -t "${normalized_file}"
gzip -t "${scored_file}"
gzip -t "${url_enriched_file}"

echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
