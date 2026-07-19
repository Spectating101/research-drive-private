#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

key="${DATACITE_CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
local_root="${DATACITE_LOCAL_ROOT:-data_lake/dataset_catalog/index_v3}"
drive_root="${DATACITE_DRIVE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/dataset_catalog/datacite/index_v3}"
interval="${DATACITE_PULL_INTERVAL:-300}"
upload_to_drive="${DATACITE_UPLOAD_TO_DRIVE:-1}"
delete_local_after_upload="${DATACITE_DELETE_LOCAL_AFTER_UPLOAD:-1}"
delete_remote_after_upload="${DATACITE_DELETE_REMOTE_AFTER_UPLOAD:-1}"
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

mkdir -p "${local_root}"

upload_verified() {
  local file="$1" target="$2" shard="$3" name="$4" local_bytes
  [[ "${upload_to_drive}" == "1" ]] || return 0
  [[ -s "${file}" ]] || return 0
  local_bytes="$(stat -c %s "${file}")"
  rclone copyto "${file}" "${target}" "${rclone_common[@]}"
  printf '%s uploaded shard=%s file=%s bytes=%s\n' "$(date -Iseconds)" "${shard}" "${name}" "${local_bytes}"
  if [[ "${delete_local_after_upload}" == "1" ]]; then
    rm -f "${file}"
  fi
}

delete_remote_file() {
  local host="$1" remote_dir="$2" name="$3"
  [[ "${delete_remote_after_upload}" == "1" ]] || return 0
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${host}" \
    "powershell -NoProfile -Command \"Remove-Item -LiteralPath '${remote_dir}/${name}' -Force -ErrorAction SilentlyContinue\"" \
    >/dev/null 2>&1 || true
}

pull_one_shard() {
  local host="$1" shard="$2" remote_dir="$3" local_dir
  local_dir="${local_root}/${shard}"
  mkdir -p "${local_dir}"

  mapfile -t files < <(
    ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${host}" \
      "powershell -NoProfile -Command \"Get-ChildItem '${remote_dir}' -Filter 'datacite_*.jsonl.gz' -File -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name\"" \
      2>/dev/null | tr -d '\r' || true
  )

  for name in "${files[@]}"; do
    [[ -n "${name}" ]] || continue
    if [[ ! -s "${local_dir}/${name}" ]]; then
      scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
        "user@${host}:${remote_dir}/${name}" "${local_dir}/${name}.partial"
      gzip -t "${local_dir}/${name}.partial"
      mv "${local_dir}/${name}.partial" "${local_dir}/${name}"
      printf '%s host=%s shard=%s pulled=%s\n' "$(date -Iseconds)" "${host}" "${shard}" "${name}"
    fi
    upload_verified "${local_dir}/${name}" "${drive_root}/${shard}/${name}" "${shard}" "${name}"
    if [[ "${upload_to_drive}" == "1" ]] && [[ ! -e "${local_dir}/${name}" ]]; then
      delete_remote_file "${host}" "${remote_dir}" "${name}"
    fi
  done

  for meta in datacite.checkpoint.json datacite.heartbeat.json harvest.stderr.log harvest.stdout.log; do
    scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
      "user@${host}:${remote_dir}/${meta}" "${local_dir}/${meta}.partial" 2>/dev/null || true
    if [[ -s "${local_dir}/${meta}.partial" ]]; then
      mv "${local_dir}/${meta}.partial" "${local_dir}/${meta}"
    else
      rm -f "${local_dir}/${meta}.partial"
    fi
    if [[ "${upload_to_drive}" == "1" && -s "${local_dir}/${meta}" ]]; then
      rclone copyto "${local_dir}/${meta}" "${drive_root}/${shard}/_meta/${meta}" \
        --transfers 1 --checkers 1 --tpslimit 1 --tpslimit-burst 1 \
        --drive-pacer-min-sleep 1s --retries 10 --low-level-retries 20 >/dev/null 2>&1 || true
    fi
  done
}

while true; do
  for worker in "${workers[@]}"; do
    IFS='|' read -r host shard remote_dir <<< "${worker}"
    pull_one_shard "${host}" "${shard}" "${remote_dir}"
  done
  sleep "${interval}"
done
