#!/usr/bin/env bash
# Conservative local DataCite harvest (Linux controller). One shard per invocation.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

shard="${DATACITE_LOCAL_SHARD:?set DATACITE_LOCAL_SHARD}"
created="${DATACITE_LOCAL_CREATED:-2025}"
query="${DATACITE_LOCAL_QUERY:-}"
shards_file="${repo_root}/scripts/data_catalog/datacite_y2025_parallel_shards.list"
if [[ ! "$query" =~ \] ]]; then
  while IFS='|' read -r s _h c q _t || [[ -n "${s:-}" ]]; do
    [[ -z "${s:-}" || "${s}" =~ ^# ]] && continue
    if [[ "${s}" == "${shard}" ]]; then
      created="${c:-${created}}"
      query="${q}"
      break
    fi
  done < "${shards_file}"
fi
sleep_s="${DATACITE_LOCAL_SLEEP:-0.45}"
page_size="${DATACITE_LOCAL_PAGE_SIZE:-500}"
local_root="${DATACITE_LOCAL_ROOT:-data_lake/dataset_catalog/index_v3}"
drive_root="${DATACITE_DRIVE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/dataset_catalog/datacite/index_v3}"
upload_chunks="${DATACITE_LOCAL_UPLOAD_CHUNKS:-1}"
delete_after_upload="${DATACITE_LOCAL_DELETE_AFTER_UPLOAD:-1}"
min_free_gb="${DATACITE_LOCAL_MIN_FREE_GB:-4}"
restart_seconds="${DATACITE_LOCAL_RESTART_SECONDS:-60}"

out_dir="${local_root}/${shard}"
mkdir -p "${out_dir}"

log() {
  printf '%s local_datacite shard=%s %s\n' "$(date -Iseconds)" "${shard}" "$*"
}

upload_complete_chunks() {
  [[ "${upload_chunks}" == "1" ]] || return 0
  shopt -s nullglob
  local files=("${out_dir}"/datacite_*.jsonl.gz)
  shopt -u nullglob
  local file name
  for file in "${files[@]}"; do
    name="$(basename "${file}")"
    rclone copyto "${file}" "${drive_root}/${shard}/${name}" \
      --transfers 1 --checkers 1 --tpslimit 1 --tpslimit-burst 1 \
      --drive-pacer-min-sleep 1s --retries 10 --low-level-retries 20 >/dev/null 2>&1 || continue
  done
  if [[ "${delete_after_upload}" == "1" ]]; then
    for file in "${files[@]}"; do
      rclone lsf "${drive_root}/${shard}/$(basename "${file}")" >/dev/null 2>&1 || continue
      rm -f "${file}"
    done
  fi
  for meta in datacite.checkpoint.json datacite.heartbeat.json; do
    [[ -s "${out_dir}/${meta}" ]] || continue
    rclone copyto "${out_dir}/${meta}" "${drive_root}/${shard}/_meta/${meta}" \
      --transfers 1 --checkers 1 --tpslimit 1 --tpslimit-burst 1 \
      --drive-pacer-min-sleep 1s --retries 5 --low-level-retries 10 >/dev/null 2>&1 || true
  done
}

free_gb() {
  df -BG "${repo_root}" | awk 'NR==2 {gsub(/G/,"",$4); print $4}'
}

while true; do
  if [[ -s "${out_dir}/datacite.complete.json" ]]; then
    upload_complete_chunks
    log "status=complete"
    exit 0
  fi
  if (( $(free_gb) < min_free_gb )); then
    log "status=pause_disk free_gb=$(free_gb) min=${min_free_gb}"
    upload_complete_chunks
    sleep "${restart_seconds}"
    continue
  fi
  args=(
    python3 scripts/data_catalog/harvest_dataset_indexes_full.py
    --out-dir "${out_dir}"
    --sources datacite
    --max-records-per-source 0
    --page-size "${page_size}"
    --sleep "${sleep_s}"
    --datacite-created-years "${created}"
  )
  if [[ -n "${query}" ]]; then
    args+=(--datacite-query "${query}")
  fi
  log "status=harvest_start sleep=${sleep_s}"
  set +e
  "${args[@]}"
  code=$?
  set -e
  upload_complete_chunks
  log "status=harvest_exit code=${code} restart_seconds=${restart_seconds}"
  sleep "${restart_seconds}"
done
