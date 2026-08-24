#!/usr/bin/env bash
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

log_dir="logs/news_shock_taxonomy/gkg_backfill_2018_2023"
log_file="${log_dir}/health_monitor.log"
status_dir="data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023"

mkdir -p "${log_dir}"

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
free_gb="$(df -BG . | awk 'NR==2 {gsub("G", "", $4); print int($4)}')"
mem_available_gb="$(awk '/MemAvailable:/ {printf "%d", $2 / 1024 / 1024}' /proc/meminfo)"
swap_used_gb="$(awk '/SwapTotal:/ {total=$2} /SwapFree:/ {free=$2} END {printf "%d", (total - free) / 1024 / 1024}' /proc/meminfo)"
verified_count="$(find "${status_dir}" -maxdepth 1 -type f -name '*.ok.json' 2>/dev/null | wc -l | tr -d ' ')"

active_runs="$(
  ps -eo cmd \
    | sed -n 's/.*run_news_shock_gkg_window_pipeline.sh \(asia_gkg_window_[^ ]*\).*/\1/p' \
    | sort -u \
    | paste -sd ',' -
)"

fetch_processes="$(
  ps -eo cmd \
    | grep 'scripts/news_shock_taxonomy/fetch_gdelt_gkg_asia_bulk.py' \
    | grep -v grep \
    | sed 's/  */ /g' \
    | paste -sd '|' - || true
)"

rclone_processes="$(
  ps -eo cmd \
    | grep 'rclone copy data_lake/news_shock_taxonomy' \
    | grep -v grep \
    | sed 's/  */ /g' \
    | paste -sd '|' - || true
)"

printf '%s free_gb=%s mem_available_gb=%s swap_used_gb=%s verified_months=%s active_runs=%s fetch=%s rclone=%s\n' \
  "${ts}" \
  "${free_gb}" \
  "${mem_available_gb}" \
  "${swap_used_gb}" \
  "${verified_count}" \
  "${active_runs:-none}" \
  "${fetch_processes:-none}" \
  "${rclone_processes:-none}" \
  | tee -a "${log_file}"

if (( free_gb < 75 )); then
  printf '%s warning=disk_below_75G free_gb=%s\n' "${ts}" "${free_gb}" | tee -a "${log_file}"
fi

if (( mem_available_gb < 8 )); then
  printf '%s warning=mem_available_below_8G mem_available_gb=%s\n' "${ts}" "${mem_available_gb}" | tee -a "${log_file}"
fi

if (( swap_used_gb > 10 )); then
  printf '%s warning=swap_above_10G swap_used_gb=%s\n' "${ts}" "${swap_used_gb}" | tee -a "${log_file}"
fi
