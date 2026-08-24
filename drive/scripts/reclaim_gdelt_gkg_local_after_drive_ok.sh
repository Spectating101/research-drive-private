#!/usr/bin/env bash
# Delete large cache staging files for months already verified on GDrive.
# Prefer: bash scripts/ops/storage_compact_verified_cache.sh
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

status_dir="${STATUS_DIR:-data_lake/news_shock_taxonomy/backfill_status/gkg_backfill_2018_2023}"
remote_root="${REMOTE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/news/gdelt-asia/gdelt_gkg_asia_backfill_2018_2023}"
dry_run="${DRY_RUN:-0}"
max_months="${MAX_MONTHS:-0}"

log() {
  printf '%s reclaim_gdelt %s\n' "$(date -Iseconds)" "$*"
}

remote_size_bytes() {
  local remote_path="$1"
  rclone lsl "${remote_path}" 2>/dev/null | awk '{print $1}' | head -1
}

compact_local() {
  local run_id="$1"
  local norm_dir="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}"
  local proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"
  rm -f \
    "${norm_dir}/asia_gkg_filtered.csv.gz" \
    "${proc_dir}/asia_gkg_scored.csv.gz" \
    "${proc_dir}/url_enrichment_queue.csv.gz" \
    "${proc_dir}/url_enrichment_enrich_high_priority.csv.gz" \
    "${proc_dir}/url_enrichment_enrich_high_priority.jsonl.gz"
  rmdir "${norm_dir}" 2>/dev/null || true
}

reclaim_month() {
  local marker="$1"
  local run_id
  run_id="$(basename "${marker}" .ok.json)"
  local norm_dir="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${run_id}"
  local proc_dir="data_lake/news_shock_taxonomy/processed/${run_id}"
  local local_norm="${norm_dir}/asia_gkg_filtered.csv.gz"
  local remote_norm="${remote_root}/normalized/gdelt_gkg_asia_bulk/${run_id}/asia_gkg_filtered.csv.gz"

  if [[ ! -s "${local_norm}" ]]; then
    log "skip_no_local run_id=${run_id}"
    return 0
  fi

  local local_bytes remote_bytes
  local_bytes="$(stat -c%s "${local_norm}")"
  remote_bytes="$(remote_size_bytes "${remote_norm}")"
  if [[ -z "${remote_bytes}" || "${remote_bytes}" -lt 1 ]]; then
    log "skip_no_remote run_id=${run_id}"
    return 1
  fi
  if [[ "${remote_bytes}" -ne "${local_bytes}" ]]; then
    log "skip_size_mismatch run_id=${run_id} local=${local_bytes} remote=${remote_bytes}"
    return 1
  fi

  if [[ "${dry_run}" == "1" ]]; then
    log "dry_run_would_delete run_id=${run_id} bytes=${local_bytes}"
    return 0
  fi

  compact_local "${run_id}"
  log "reclaimed run_id=${run_id} bytes=${local_bytes}"
}

processed=0
reclaimed=0
skipped=0
failed=0

log "start status_dir=${status_dir} dry_run=${dry_run}"

shopt -s nullglob
markers=("${status_dir}"/*.ok.json)
shopt -u nullglob

for marker in "${markers[@]}"; do
  [[ -s "${marker}" ]] || continue
  processed=$((processed + 1))
  if (( max_months > 0 && processed > max_months )); then
    break
  fi
  if reclaim_month "${marker}"; then
    if [[ "${dry_run}" == "1" ]]; then
      skipped=$((skipped + 1))
    else
      reclaimed=$((reclaimed + 1))
    fi
  else
    failed=$((failed + 1))
  fi
done

log "done processed=${processed} reclaimed=${reclaimed} failed=${failed} dry_run=${dry_run}"
df -BG "${repo_root}" | awk 'NR==2 {print "disk_free_gb=" $4 " disk_used_pct=" $5}'
