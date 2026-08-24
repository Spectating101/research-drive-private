#!/usr/bin/env bash
set -euo pipefail

# Fetch/filter one GDELT GKG Asia monthly window on a helper machine, then
# push the normalized output back to optiplex. This intentionally does not
# score, enrich, or upload to Drive.

if [[ $# -lt 4 ]]; then
  echo "usage: $0 RUN_ID START_DATE END_DATE OPTIPLEX_REPO_ROOT" >&2
  exit 2
fi

run_id="$1"
start_date="$2"
end_date="$3"
optiplex_repo_root="$4"

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

workers="${FETCH_WORKERS:-2}"
timeout_seconds="${TIMEOUT_SECONDS:-300}"
retries="${RETRIES:-4}"
fetch_sleep="${FETCH_SLEEP:-0.2}"
min_free_gb="${MIN_FREE_GB:-20}"
min_mem_gb="${MIN_MEM_GB:-3}"
max_swap_gb="${MAX_SWAP_GB:-1}"

log_dir="logs/news_shock_taxonomy/remote_prefetch"
log_file="${log_dir}/${run_id}.log"
mkdir -p "${log_dir}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${log_file}"
}

free_gb() {
  df -BG / | awk 'NR==2 {gsub("G", "", $4); print int($4)}'
}

mem_available_gb() {
  awk '/MemAvailable:/ {printf "%d", $2 / 1024 / 1024}' /proc/meminfo
}

swap_used_gb() {
  awk '/SwapTotal:/ {total=$2} /SwapFree:/ {free=$2} END {printf "%d", (total - free) / 1024 / 1024}' /proc/meminfo
}

wait_for_headroom() {
  while true; do
    local disk mem swap
    disk="$(free_gb)"
    mem="$(mem_available_gb)"
    swap="$(swap_used_gb)"
    log "resource_check disk_free_gb=${disk} mem_available_gb=${mem} swap_used_gb=${swap} required_disk_gb=${min_free_gb} required_mem_gb=${min_mem_gb} max_swap_gb=${max_swap_gb}"
    if (( disk >= min_free_gb && mem >= min_mem_gb && swap <= max_swap_gb )); then
      return 0
    fi
    sleep 120
  done
}

normalized_dir="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}"
normalized_file="${normalized_dir}/asia_gkg_filtered.csv.gz"

log "remote_prefetch_start host=$(hostname) run_id=${run_id} start=${start_date} end=${end_date} workers=${workers}"
wait_for_headroom

if [[ -s "${normalized_file}" ]] && gzip -t "${normalized_file}"; then
  log "fetch_skipped_existing=${normalized_file}"
else
  python3 scripts/news_shock_taxonomy/fetch_gdelt_gkg_asia_bulk.py \
    --run-id "${run_id}" \
    --start-date "${start_date}" \
    --end-date "${end_date}" \
    --timeout "${timeout_seconds}" \
    --retries "${retries}" \
    --sleep "${fetch_sleep}" \
    --workers "${workers}" \
    --master-refresh-seconds 86400 \
    --no-keep-raw 2>&1 | tee -a "${log_file}"
fi

gzip -t "${normalized_file}"
log "fetch_complete size_bytes=$(stat -c %s "${normalized_file}")"

rsync -a --partial --info=progress2 \
  "${normalized_dir}/" \
  "optiplex:${optiplex_repo_root}/${normalized_dir}/" 2>&1 | tee -a "${log_file}"

log "rsync_complete destination=optiplex:${optiplex_repo_root}/${normalized_dir}"
log "remote_prefetch_done run_id=${run_id}"
