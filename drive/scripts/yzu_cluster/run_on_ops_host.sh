#!/usr/bin/env bash
# Run a shell command on the cluster ops host when cluster_only=true; else run locally.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <command>" >&2
  exit 2
fi

command="$*"
export CLUSTER_OPS_COMMAND="${command}"
PYTHONPATH="${repo_root}" python3 -c "
import json, os, subprocess, sys
from pathlib import Path
from scripts.yzu_cluster.cluster_ops import cluster_only, run_on_ops_host

repo = Path('.').resolve()
cfg = json.loads((repo / 'config/yzu_cluster.json').read_text(encoding='utf-8'))
cmd = os.environ['CLUSTER_OPS_COMMAND']
if not cluster_only(cfg):
    raise SystemExit(subprocess.run(cmd, shell=True, cwd=repo, check=False).returncode)
timeout = int(os.environ.get('CLUSTER_OPS_TIMEOUT', '7200'))
proc = run_on_ops_host(cfg, cmd, timeout=timeout)
raise SystemExit(proc.returncode)
"
