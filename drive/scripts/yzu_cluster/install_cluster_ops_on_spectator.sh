#!/usr/bin/env bash
# Bootstrap spectator (or other ops host) for cluster-only DataCite/GDELT operations.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

PYTHONPATH="${repo_root}" python3 -c "
import json
from scripts.yzu_cluster.cluster_ops import ops_host
cfg = json.loads(open('config/yzu_cluster.json').read())
print(ops_host(cfg)['ssh_target'])
" | {
  read -r target
  key="$(PYTHONPATH="${repo_root}" python3 -c "import json; print(json.load(open('config/yzu_cluster.json'))['operations']['ops_host']['ssh_key'])")"
  remote_repo="$(PYTHONPATH="${repo_root}" python3 -c "from scripts.yzu_cluster.cluster_ops import ops_host; import json; print(ops_host(json.load(open('config/yzu_cluster.json')))['repo_root'])")"
  staging="$(PYTHONPATH="${repo_root}" python3 -c "from scripts.yzu_cluster.cluster_ops import ops_host; import json; print(ops_host(json.load(open('config/yzu_cluster.json')))['staging_root'])")"

  echo "target=${target}"
  echo "repo=${remote_repo}"
  echo "staging=${staging}"

  ssh -i "${key}" -o BatchMode=yes "${target}" "mkdir -p '${staging}' '${remote_repo}/data_lake/dataset_catalog/watchdog' ~/.config/rclone"
  if [[ -f "${HOME}/.config/rclone/rclone.conf" ]]; then
    scp -q -i "${key}" "${HOME}/.config/rclone/rclone.conf" "${target}:.config/rclone/rclone.conf"
  fi
  ssh -i "${key}" -o BatchMode=yes "${target}" "
    mkdir -p ~/bin
    if ! command -v rclone >/dev/null 2>&1 && [[ ! -x ~/bin/rclone ]]; then
      curl -fsSL https://downloads.rclone.org/rclone-current-linux-amd64.zip -o /tmp/rclone.zip
      unzip -qo /tmp/rclone.zip -d /tmp
      cp /tmp/rclone-*-linux-amd64/rclone ~/bin/
      chmod +x ~/bin/rclone
    fi
    ~/bin/rclone version | head -1
  "
  echo "Done. Install systemd timer ON ${target} if you want ops to run without optiplex triggering SSH."
}
