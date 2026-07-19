#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

remote="${DATACITE_CLUSTER_REMOTE:-user@100.102.0.84}"
key="${DATACITE_CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
remote_dir="${DATACITE_CLUSTER_DIR:-C:/cw/dataset_index_v3}"
local_dir="${DATACITE_LOCAL_DIR:-data_lake/dataset_catalog/index_v3}"
interval="${DATACITE_PULL_INTERVAL:-300}"

mkdir -p "${local_dir}"

while true; do
  mapfile -t files < <(
    ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "${remote}" \
      "powershell -NoProfile -Command \"Get-ChildItem '${remote_dir}' -Filter 'datacite_*.jsonl.gz' | ForEach-Object { \\$_.Name }\"" \
      2>/dev/null || true
  )

  for name in "${files[@]}"; do
    [[ -n "${name}" ]] || continue
    if [[ ! -s "${local_dir}/${name}" ]]; then
      scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
        "${remote}:${remote_dir}/${name}" "${local_dir}/${name}.partial"
      gzip -t "${local_dir}/${name}.partial"
      mv "${local_dir}/${name}.partial" "${local_dir}/${name}"
      echo "$(date -Iseconds) pulled=${name}"
    fi
  done

  scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "${remote}:${remote_dir}/datacite.checkpoint.json" "${local_dir}/datacite.remote.checkpoint.json.partial" 2>/dev/null || true
  if [[ -s "${local_dir}/datacite.remote.checkpoint.json.partial" ]]; then
    mv "${local_dir}/datacite.remote.checkpoint.json.partial" "${local_dir}/datacite.remote.checkpoint.json"
  fi

  sleep "${interval}"
done
