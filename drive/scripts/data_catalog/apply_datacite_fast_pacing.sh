#!/usr/bin/env bash
# Apply faster (but not reckless) DataCite pacing to active y2025 quarterly shards.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
catalog_dir="${repo_root}/scripts/data_catalog"
key="${DATACITE_CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
python_exe="${DATACITE_WINDOWS_PYTHON:-C:/Users/user/AppData/Local/Programs/Python/Python39/python.exe}"
windows_sleep="${DATACITE_WINDOWS_SLEEP:-0.15}"
linux_sleep="${DATACITE_LINUX_SLEEP:-0.20}"
shards_file="${catalog_dir}/datacite_y2025_parallel_shards.list"

log() { printf '%s fast_pacing %s\n' "$(date -Iseconds)" "$*"; }

apply_windows_shard() {
  local host="$1" shard="$2" created="$3" query="$4"
  scp -q -i "${key}" -o BatchMode=yes \
    "${catalog_dir}/install_datacite_shard.ps1" \
    "${catalog_dir}/restart_datacite_shard_clean.ps1" \
    "${catalog_dir}/harvest_dataset_indexes_full.py" \
    "user@${host}:C:/Users/user/"
  ssh -n -i "${key}" -o BatchMode=yes "user@${host}" \
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"
      & C:/Users/user/install_datacite_shard.ps1 -ShardName ${shard} -CreatedYears ${created} -DataCiteQuery \\\"${query}\\\" -PythonExe \\\"${python_exe}\\\" -SleepSeconds ${windows_sleep} -MaxRecords 0 | Out-Null
    \""
  ssh -n -i "${key}" -o BatchMode=yes "user@${host}" \
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/Users/user/restart_datacite_shard_clean.ps1 -ShardName ${shard}" >/dev/null
  log "windows shard=${shard} host=${host} sleep=${windows_sleep}"
}

while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line}" || "${line}" =~ ^# ]] && continue
  IFS='|' read -r shard host created query _target <<< "${line}"
  [[ -n "${host}" && "${host}" != "local" ]] || continue
  apply_windows_shard "${host}" "${shard}" "${created}" "${query}"
done < "${shards_file}"

unit_src="${repo_root}/systemd/datacite-local-y2025-q3.service"
unit_dst="${HOME}/.config/systemd/user/datacite-local-y2025-q3.service"
mkdir -p "${HOME}/.config/systemd/user"
if [[ -f "${unit_src}" ]]; then
  sed "s/DATACITE_LOCAL_SLEEP=.*/DATACITE_LOCAL_SLEEP=${linux_sleep}/" "${unit_src}" > "${unit_dst}"
  systemctl --user daemon-reload
  systemctl --user restart datacite-local-y2025-q3.service
  log "linux shard=y2025_q3 sleep=${linux_sleep}"
fi

log "done windows_sleep=${windows_sleep} linux_sleep=${linux_sleep}"
