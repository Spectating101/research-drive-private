#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

key="${DATACITE_CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
local_root="${DATACITE_LOCAL_ROOT:-data_lake/dataset_catalog/index_v3}"
drive_root="${DATACITE_DRIVE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/dataset_catalog/datacite/index_v3}"
delete_local_after_upload="${DATACITE_DELETE_LOCAL_AFTER_UPLOAD:-1}"
delete_remote_after_upload="${DATACITE_DELETE_REMOTE_AFTER_UPLOAD:-1}"
reverify_local="${DATACITE_REVERIFY_LOCAL:-0}"
rclone_common=(
  --checksum
  --transfers 1
  --checkers 1
  --no-traverse
  --tpslimit 1
  --tpslimit-burst 1
  --drive-pacer-min-sleep 1s
  --retries 20
  --low-level-retries 50
  --log-level INFO
  --stats 1m
)

workers=()
while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line}" || "${line}" =~ ^# ]] && continue
  workers+=("${line}")
done < "${repo_root}/scripts/data_catalog/datacite_cluster_workers.list"

remote_for_shard() {
  local shard="$1" worker host ws remote_dir
  for worker in "${workers[@]}"; do
    IFS='|' read -r host ws remote_dir <<< "${worker}"
    if [[ "${ws}" == "${shard}" ]]; then
      printf '%s|%s\n' "${host}" "${remote_dir}"
      return 0
    fi
  done
  return 1
}

delete_remote_file() {
  local shard="$1" name="$2" ref host remote_dir
  [[ "${delete_remote_after_upload}" == "1" ]] || return 0
  ref="$(remote_for_shard "${shard}")" || return 0
  IFS='|' read -r host remote_dir <<< "${ref}"
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${host}" \
    "powershell -NoProfile -Command \"Remove-Item -LiteralPath '${remote_dir}/${name}' -Force -ErrorAction SilentlyContinue\"" \
    >/dev/null 2>&1 || true
}

upload_meta() {
  local shard="$1" dir="$2" drive_dir="$3" meta
  for meta in datacite.checkpoint.json datacite.heartbeat.json harvest.stderr.log harvest.stdout.log; do
    if [[ -s "${dir}/${meta}" ]]; then
      rclone copyto "${dir}/${meta}" "${drive_dir}/_meta/${meta}" \
        --transfers 1 --checkers 1 --tpslimit 1 --tpslimit-burst 1 \
        --drive-pacer-min-sleep 1s --retries 10 --low-level-retries 20 >/dev/null 2>&1 || true
    fi
  done
}

for worker in "${workers[@]}"; do
  IFS='|' read -r _host shard _remote_dir <<< "${worker}"
  dir="${local_root}/${shard}"
  drive_dir="${drive_root}/${shard}"
  [[ -d "${dir}" ]] || continue
  shopt -s nullglob
  files=("${dir}"/datacite_*.jsonl.gz)
  shopt -u nullglob
  if (( ${#files[@]} > 0 )); then
    names=()
    total_bytes=0
    for file in "${files[@]}"; do
      if [[ "${reverify_local}" == "1" ]]; then
        gzip -t "${file}"
      fi
      names+=("$(basename "${file}")")
      total_bytes=$((total_bytes + $(stat -c %s "${file}")))
    done
    transfer_command="copy"
    if [[ "${delete_local_after_upload}" == "1" ]]; then
      transfer_command="move"
    fi
    rclone "${transfer_command}" "${dir}" "${drive_dir}" \
      --include "datacite_*.jsonl.gz" "${rclone_common[@]}"
    printf '%s uploaded_batch shard=%s files=%s bytes=%s\n' \
      "$(date -Iseconds)" "${shard}" "${#names[@]}" "${total_bytes}"
    for name in "${names[@]}"; do
      delete_remote_file "${shard}" "${name}"
    done
  fi
  upload_meta "${shard}" "${dir}" "${drive_dir}"
done
