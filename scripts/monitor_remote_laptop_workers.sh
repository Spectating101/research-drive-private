#!/usr/bin/env bash
set -euo pipefail

inventory="${CLUSTER_INVENTORY:-/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv}"
key="${CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
log_dir="logs/remote_workers"
mkdir -p "${log_dir}"

probe_host() {
  local hostname="$1"
  local ip="$2"
  local user="$3"
  local status="$4"
  local log_file="${log_dir}/${hostname}_health.log"
  local ts
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

  if [[ "${status}" != "joined" ]]; then
    printf '%s host=%s ip=%s status=skipped inventory_status=%s\n' \
      "${ts}" "${hostname}" "${ip}" "${status}" | tee -a "${log_file}"
    return 0
  fi

  if ! ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "${user}@${ip}" 'hostname' 2>/dev/null | grep -qi "${hostname}"; then
    printf '%s host=%s ip=%s status=ssh_unreachable\n' \
      "${ts}" "${hostname}" "${ip}" | tee -a "${log_file}"
    return 0
  fi

  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "${user}@${ip}" \
    "powershell -NoProfile -Command \"\$d=[math]::Floor((Get-PSDrive C).Free/1GB); \$m=[math]::Floor((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB); \$sshd=(Get-Service sshd).Status; \$ts=(Get-Service Tailscale).Status; Write-Output ('disk_free_gb='+\$d+' mem_available_gb='+\$m+' sshd='+\$sshd+' tailscale='+\$ts)\"" \
    2>/dev/null | while IFS= read -r line; do
    printf '%s host=%s ip=%s status=ok %s\n' "${ts}" "${hostname}" "${ip}" "${line}" | tee -a "${log_file}"
  done || printf '%s host=%s ip=%s status=ssh_probe_failed\n' "${ts}" "${hostname}" "${ip}" | tee -a "${log_file}"
}

if [[ ! -f "${inventory}" ]]; then
  echo "missing inventory: ${inventory}" >&2
  exit 1
fi

while IFS=, read -r hostname ip user status notes; do
  [[ "${hostname}" == "hostname" ]] && continue
  [[ -n "${hostname}" ]] || continue
  probe_host "${hostname}" "${ip}" "${user}" "${status}"
done < "${inventory}"
