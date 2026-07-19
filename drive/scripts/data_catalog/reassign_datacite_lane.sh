#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: reassign_datacite_lane.sh <lane> <new_host> [created_years]

Fail over a stalled DataCite harvest lane to a new Windows worker.
Updates cluster worker maps, seeds checkpoint on the new host, and starts the shard task.

Example:
  scripts/data_catalog/reassign_datacite_lane.sh y2025 100.102.0.84 2025
EOF
}

if [[ $# -lt 2 ]]; then
  usage
  exit 2
fi

lane="$1"
new_host="$2"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
created_years=""
datacite_query=""
shards_file="${repo_root}/scripts/data_catalog/datacite_y2025_parallel_shards.list"
if [[ -f "${shards_file}" ]]; then
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^# ]] && continue
    IFS='|' read -r shard _host spec_created spec_query _target <<< "${line}"
    if [[ "${shard}" == "${lane}" ]]; then
      created_years="${spec_created}"
      datacite_query="${spec_query}"
      break
    fi
  done < "${shards_file}"
fi
case "${lane}" in
  y2011_2020_2022) created_years="2011,2012,2013,2014,2015,2016,2017,2018,2019,2020,2022" ;;
  y2023_2024) created_years="2023,2024" ;;
  y2025) created_years="2025" ;;
  y2026) created_years="2026" ;;
  y2025_q1|y2025_q2|y2025_q3|y2025_q4)
    [[ -n "${created_years}" ]] || created_years="2025"
    ;;
  *)
    if [[ -z "${created_years}" ]]; then
      echo "ERROR: unknown lane ${lane}" >&2
      exit 2
    fi
    ;;
esac
catalog_dir="${repo_root}/scripts/data_catalog"
workers_file="${catalog_dir}/datacite_cluster_workers.list"
watchdog_file="${catalog_dir}/datacite_cluster_watchdog.list"
local_root="${DATACITE_LOCAL_ROOT:-${repo_root}/data_lake/dataset_catalog/index_v3}"
key="${DATACITE_CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
python_exe="${DATACITE_WINDOWS_PYTHON:-C:/Users/user/AppData/Local/Programs/Python/Python39/python.exe}"
remote_dir="C:/cw/dataset_index_${lane}"
lane_dir="${local_root}/${lane}"

old_host=""
while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line}" || "${line}" =~ ^# ]] && continue
  IFS='|' read -r host shard _remote <<< "${line}"
  if [[ "${shard}" == "${lane}" ]]; then
    old_host="${host}"
    break
  fi
done < "${workers_file}"

tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT

awk -F'|' -v lane="${lane}" -v host="${new_host}" -v remote="${remote_dir}" '
  /^#/ || $0 == "" { print; next }
  $2 == lane { print host "|" lane "|" remote; next }
  { print }
' "${workers_file}" > "${tmp}"
mv "${tmp}" "${workers_file}"

if [[ -f "${watchdog_file}" ]]; then
  awk -F'|' -v lane="${lane}" -v host="${new_host}" '
    /^#/ || $0 == "" { print; next }
    $2 == lane { print host "|" lane; next }
    { print }
  ' "${watchdog_file}" > "${tmp}"
  mv "${tmp}" "${watchdog_file}"
fi

if ! ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${new_host}" "hostname" >/dev/null 2>&1; then
  echo "ERROR: new host ${new_host} is unreachable" >&2
  exit 1
fi

mkdir -p "${lane_dir}"

if [[ -n "${old_host}" && "${old_host}" != "${new_host}" ]] && \
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${old_host}" "hostname" >/dev/null 2>&1; then
  for meta in datacite.checkpoint.json datacite.heartbeat.json datacite.complete.json; do
    scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
      "user@${old_host}:${remote_dir}/${meta}" "${lane_dir}/${meta}.partial" 2>/dev/null || continue
    if [[ -s "${lane_dir}/${meta}.partial" ]]; then
      mv -f "${lane_dir}/${meta}.partial" "${lane_dir}/${meta}"
    else
      rm -f "${lane_dir}/${meta}.partial"
    fi
  done
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${old_host}" \
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"
      Stop-ScheduledTask -TaskName ResearchDataIndexDataCite_${lane} -ErrorAction SilentlyContinue
      Disable-ScheduledTask -TaskName ResearchDataIndexDataCite_${lane} -ErrorAction SilentlyContinue | Out-Null
      Get-CimInstance Win32_Process |
        Where-Object { \$_.CommandLine -like '*dataset_index_${lane}*' } |
        ForEach-Object { Stop-Process -Id \$_.ProcessId -Force -ErrorAction SilentlyContinue }
    \"" 2>/dev/null || true
fi

ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${new_host}" \
  "powershell.exe -NoProfile -Command \"New-Item -ItemType Directory -Force -Path '${remote_dir}' | Out-Null\""

for meta in datacite.checkpoint.json datacite.heartbeat.json; do
  if [[ -s "${lane_dir}/${meta}" ]]; then
    scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
      "${lane_dir}/${meta}" "user@${new_host}:${remote_dir}/${meta}"
  fi
done

for script in install_datacite_shard.ps1 restart_datacite_shard_clean.ps1 harvest_dataset_indexes_full.py; do
  scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "${catalog_dir}/${script}" "user@${new_host}:C:/Users/user/${script}"
done

ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${new_host}" \
  "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"
    \$ErrorActionPreference = 'Stop'
    \$lane = '${lane}'
    \$outDir = '${remote_dir}'
    \$taskName = 'ResearchDataIndexDataCite_' + \$lane
    Get-ScheduledTask -TaskName 'ResearchDataIndexDataCite_*' -ErrorAction SilentlyContinue |
      Where-Object { \$_.TaskName -ne \$taskName -and \$_.State -ne 'Disabled' } |
      ForEach-Object {
        Stop-ScheduledTask -TaskName \$_.TaskName -ErrorAction SilentlyContinue
        Disable-ScheduledTask -TaskName \$_.TaskName -ErrorAction SilentlyContinue | Out-Null
      }
    Remove-Item -Force (Join-Path \$outDir 'datacite.complete.json') -ErrorAction SilentlyContinue
    Get-ChildItem \$outDir -Filter 'datacite_0*.jsonl.gz*' -ErrorAction SilentlyContinue |
      Where-Object { \$_.Name -lt ('datacite_' + ('{0:D6}' -f (Get-Content (Join-Path \$outDir 'datacite.checkpoint.json') | ConvertFrom-Json).next_chunk_index) + '.jsonl.gz') } |
      Remove-Force -ErrorAction SilentlyContinue
  \"" 2>/dev/null || true

if ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${new_host}" \
  "schtasks.exe /Query /TN ResearchDataIndexDataCite_${lane}" >/dev/null 2>&1; then
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${new_host}" \
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/Users/user/restart_datacite_shard_clean.ps1 -ShardName ${lane}"
else
  query_arg=""
  if [[ -n "${datacite_query}" ]]; then
    query_arg="-DataCiteQuery \"${datacite_query}\""
  fi
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${new_host}" \
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/Users/user/install_datacite_shard.ps1 -ShardName ${lane} -CreatedYears ${created_years} ${query_arg} -PythonExe \"${python_exe}\" -MaxRecords 0"
fi

printf '%s lane=%s host=%s created_years=%s status=started\n' "$(date -Iseconds)" "${lane}" "${new_host}" "${created_years}"
