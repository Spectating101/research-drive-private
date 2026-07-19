#!/usr/bin/env bash
# Split the remaining y2025 harvest into disjoint quarterly query shards on idle workers.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
catalog_dir="${repo_root}/scripts/data_catalog"
key="${DATACITE_CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
python_exe="${DATACITE_WINDOWS_PYTHON:-C:/Users/user/AppData/Local/Programs/Python/Python39/python.exe}"
local_root="${DATACITE_LOCAL_ROOT:-${repo_root}/data_lake/dataset_catalog/index_v3}"
shards_file="${catalog_dir}/datacite_y2025_parallel_shards.list"
workers_file="${catalog_dir}/datacite_cluster_workers.list"
watchdog_file="${catalog_dir}/datacite_cluster_watchdog.list"
lanes_file="${catalog_dir}/datacite_cluster_lanes.list}"

log() { printf '%s y2025_parallel %s\n' "$(date -Iseconds)" "$*"; }

host_reachable() {
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "user@$1" "hostname" >/dev/null 2>&1
}

stop_lane_on_host() {
  local host="$1" lane="$2"
  host_reachable "${host}" || return 0
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${host}" \
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"
      Stop-ScheduledTask -TaskName ResearchDataIndexDataCite_${lane} -ErrorAction SilentlyContinue
      Disable-ScheduledTask -TaskName ResearchDataIndexDataCite_${lane} -ErrorAction SilentlyContinue | Out-Null
      Get-CimInstance Win32_Process |
        Where-Object { \$_.CommandLine -like '*dataset_index_${lane}*' } |
        ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }
    \"" 2>/dev/null || true
}

deploy_host_scripts() {
  local host="$1"
  for f in harvest_dataset_indexes_full.py install_datacite_shard.ps1 restart_datacite_shard_clean.ps1 datacite_lane_probe.ps1; do
    scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
      "${catalog_dir}/${f}" "user@${host}:C:/Users/user/${f}" 2>/dev/null || \
      scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
      "${repo_root}/scripts/data_catalog/${f}" "user@${host}:C:/Users/user/${f}"
  done
}

install_shard() {
  local host="$1" shard="$2" created="$3" query="$4"
  deploy_host_scripts "${host}"
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${host}" \
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/Users/user/install_datacite_shard.ps1 -ShardName ${shard} -CreatedYears ${created} -DataCiteQuery \"${query}\" -PythonExe \"${python_exe}\" -MaxRecords 0"
}

# Archive monolithic lane checkpoints locally.
archive_dir="${local_root}/y2025_monolith_archive_$(date +%Y%m%dT%H%M%S)"
if [[ -d "${local_root}/y2025" ]]; then
  mkdir -p "${archive_dir}"
  cp -a "${local_root}/y2025/." "${archive_dir}/" 2>/dev/null || true
  log "archived_monolith=${archive_dir}"
fi

while IFS= read -r host || [[ -n "${host}" ]]; do
  [[ -z "${host}" || "${host}" =~ ^# ]] && continue
  stop_lane_on_host "${host}" "y2025"
done < "${catalog_dir}/datacite_cluster_hosts.list"

log "stopped_monolithic_y2025"

{
  echo "# lane|created_years|target_records"
  grep -E '^y2011|^y2023|^y2026' "${lanes_file}" 2>/dev/null | grep -v '^#' || true
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^# ]] && continue
    IFS='|' read -r shard _host created _query target <<< "${line}"
    printf '%s|%s|%s\n' "${shard}" "${created}" "${target}"
  done < "${shards_file}"
} > "${lanes_file}.new"
mv "${lanes_file}.new" "${lanes_file}"

# workers + watchdog: keep completed archives, replace y2025 with q1-q3 active
{
  echo "# host|shard|remote_dir"
  grep -E 'y2023_2024|y2011_2020_2022|y2026' "${workers_file}" | grep -v '^#' || true
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^# ]] && continue
    IFS='|' read -r shard host created query target <<< "${line}"
    [[ -n "${host}" ]] || continue
    printf '%s|%s|C:/cw/dataset_index_%s\n' "${host}" "${shard}" "${shard}"
  done < "${shards_file}"
} > "${workers_file}"

{
  echo "# host|shard — active harvest lanes only (exclude completed archives)"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^# ]] && continue
    IFS='|' read -r shard host created query target <<< "${line}"
    [[ -n "${host}" ]] || continue
    printf '%s|%s\n' "${host}" "${shard}"
  done < "${shards_file}"
} > "${watchdog_file}"

mkdir -p "${local_root}/y2025_q1" "${local_root}/y2025_q2" "${local_root}/y2025_q3" "${local_root}/y2025_q4"

while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line}" || "${line}" =~ ^# ]] && continue
  IFS='|' read -r shard host created query target <<< "${line}"
  [[ -n "${host}" ]] || continue
  log "install shard=${shard} host=${host} target=${target}"
  install_shard "${host}" "${shard}" "${created}" "${query}"
done < "${shards_file}"

log "done launched=$(grep -c '|' "${watchdog_file}" || true) active_shards q4_waits_for_idle_rebalancer"
