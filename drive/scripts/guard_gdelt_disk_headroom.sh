#!/usr/bin/env bash
set -euo pipefail

# Keep enough local disk headroom for the GDELT backfill lanes.
#
# This is intentionally conservative. It only compacts local GDELT artifacts
# for monthly runs that have already been checked against Drive by a previous
# cleanup pass. It does not touch active 2018 backfill windows or unverified
# local-only data.

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

# When USB bulk cache is mounted, only NVMe headroom matters for desk/OS — bulk lives on Transcend.
min_free_gb="${MIN_FREE_GB:-75}"
target_free_gb="${TARGET_FREE_GB:-90}"
tier_limits="$(python3 -c "
import sys
sys.path.insert(0, '.')
from pathlib import Path
from scripts.research_data_mcp.data_paths import bulk_storage_root
from scripts.research_data_mcp.storage_tiers import load_storage_tiers, nvme_disk_headroom_gb
repo = Path('.')
if bulk_storage_root() is not None:
    rules = (load_storage_tiers(repo).get('rules') or {})
    print(rules.get('nvme_min_free_gb_when_cache_mounted', 40))
    print(rules.get('nvme_target_free_gb_when_cache_mounted', 55))
" 2>/dev/null || true)"
if [[ -n "${tier_limits}" ]]; then
  tier_min="$(printf '%s\n' "${tier_limits}" | sed -n '1p')"
  tier_target="$(printf '%s\n' "${tier_limits}" | sed -n '2p')"
  if [[ -n "${tier_min}" ]]; then
    min_free_gb="${tier_min}"
    target_free_gb="${tier_target:-$(( tier_min + 15 ))}"
  fi
fi
work_dir="${WORK_DIR:-logs/news_shock_taxonomy/gkg_backfill_2018_2023/verified_cleanup_index}"
local_norm="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk"
local_proc="data_lake/news_shock_taxonomy/processed"
log_dir="logs/news_shock_taxonomy/gkg_backfill_2018_2023"
log_file="${log_dir}/disk_guard.log"

mkdir -p "${log_dir}"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${log_file}"
}

free_gb() {
  df -BG . | awk 'NR==2 {gsub("G", "", $4); print int($4)}'
}

bytes_path() {
  local path="$1"
  [[ -e "${path}" ]] || {
    printf '0\n'
    return 0
  }
  du -sb "${path}" 2>/dev/null | awk '{print $1}'
}

active_run_ids() {
  ps -eo cmd \
    | sed -n 's/.*run_news_shock_gkg_window_pipeline.sh \(asia_gkg_window_[^ ]*\).*/\1/p' \
    | sort -u
}

is_active_run() {
  local run_id="$1"
  active_run_ids | grep -Fxq "${run_id}"
}

compact_verified_run() {
  local run_id="$1"

  if is_active_run "${run_id}"; then
    log "skip_active run_id=${run_id}"
    return 0
  fi

  log "compact_start run_id=${run_id}"
  rm -f \
    "${local_norm}/${run_id}/asia_gkg_filtered.csv.gz" \
    "${local_proc}/${run_id}/asia_gkg_scored.csv.gz" \
    "${local_proc}/${run_id}/url_enrichment_queue.csv.gz" \
    "${local_proc}/${run_id}/url_enrichment_enrich_high_priority.csv.gz" \
    "${local_proc}/${run_id}/url_enrichment_enrich_high_priority.jsonl.gz"
  rmdir "${local_norm}/${run_id}" 2>/dev/null || true
  log "compact_done run_id=${run_id}"
}

free_before="$(free_gb)"
log "disk_guard_start free_gb=${free_before} min_free_gb=${min_free_gb} target_free_gb=${target_free_gb}"

if (( free_before >= min_free_gb )); then
  log "disk_guard_noop reason=above_min"
  exit 0
fi

verified_file="${work_dir}/verified.txt"
if [[ ! -s "${verified_file}" ]]; then
  log "disk_guard_no_verified_index path=${verified_file}"
  exit 0
fi

tmp_candidates="$(mktemp)"
trap 'rm -f "${tmp_candidates}"' EXIT

while IFS= read -r run_id; do
  [[ -n "${run_id}" ]] || continue
  bytes=$(( $(bytes_path "${local_norm}/${run_id}") + $(bytes_path "${local_proc}/${run_id}") ))
  if (( bytes > 0 )); then
    printf '%s\t%s\n' "${bytes}" "${run_id}" >> "${tmp_candidates}"
  fi
done < "${verified_file}"

sort -nr "${tmp_candidates}" -o "${tmp_candidates}"

while IFS=$'\t' read -r _bytes run_id; do
  [[ -n "${run_id:-}" ]] || continue
  current_free="$(free_gb)"
  if (( current_free >= target_free_gb )); then
    log "disk_guard_target_reached free_gb=${current_free}"
    exit 0
  fi
  compact_verified_run "${run_id}"
done < "${tmp_candidates}"

log "disk_guard_finished free_gb=$(free_gb)"
