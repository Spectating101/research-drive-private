#!/usr/bin/env bash
set -euo pipefail

# Run a safe Reddit ingest lane on a helper machine and rsync its separate
# output namespace back to optiplex. This deliberately avoids writing to the
# main optiplex reddit_ingest.sqlite to prevent cross-machine SQLite conflicts.

if [[ $# -lt 1 ]]; then
  echo "usage: $0 OPTIPLEX_REPO_ROOT" >&2
  exit 2
fi

optiplex_repo_root="$1"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

min_free_gb="${MIN_FREE_GB:-15}"
min_mem_gb="${MIN_MEM_GB:-2}"
max_swap_gb="${MAX_SWAP_GB:-1}"

namespace="data_lake/sentiment/remote_laptop"
db="${namespace}/reddit_ingest.sqlite"
raw_root="${namespace}/reddit/raw"
panel="${namespace}/reddit_daily_signals.parquet"
health_json="${namespace}/reddit_health.json"
health_md="${namespace}/reddit_health.md"
log_dir="logs/reddit_remote_worker"
log_file="${log_dir}/run_$(date -u +%Y%m%dT%H%M%SZ).log"

mkdir -p "${log_dir}" "${namespace}"

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

disk="$(free_gb)"
mem="$(mem_available_gb)"
swap="$(swap_used_gb)"
log "resource_check disk_free_gb=${disk} mem_available_gb=${mem} swap_used_gb=${swap}"
if (( disk < min_free_gb || mem < min_mem_gb || swap > max_swap_gb )); then
  log "resource_blocked min_free_gb=${min_free_gb} min_mem_gb=${min_mem_gb} max_swap_gb=${max_swap_gb}"
  exit 75
fi

log "reddit_ingest_start"
python3 scripts/reddit_ingest_daily.py \
  --db "${db}" \
  --raw-root "${raw_root}" \
  --panel-out "${panel}" \
  --tickers-file config/tickers_reddit_nasdaq100_plus_spy.txt \
  --fetch-modes new hot top:day top:week \
  --limit 100 \
  --max-pages 4 \
  --sleep-secs 1.2 \
  --stop-after-known 40 \
  --comments-lookback-hours 48 \
  --comments-max-posts 80 \
  --comments-min-refetch-hours 24 \
  --lookback-days 45 \
  --min-upvotes 3 2>&1 | tee -a "${log_file}"

log "reddit_health_start"
python3 scripts/reddit_data_health.py \
  --db "${db}" \
  --raw-root "${raw_root}" \
  --panel "${panel}" \
  --out-json "${health_json}" \
  --out-md "${health_md}" 2>&1 | tee -a "${log_file}"

log "rsync_back_start"
rsync -a --partial --info=progress2 \
  "${namespace}/" \
  "optiplex:${optiplex_repo_root}/${namespace}/" 2>&1 | tee -a "${log_file}"

rsync -a --partial \
  "${log_file}" \
  "optiplex:${optiplex_repo_root}/${log_file}" 2>&1 | tee -a "${log_file}" || true

log "reddit_remote_worker_done namespace=${namespace}"
