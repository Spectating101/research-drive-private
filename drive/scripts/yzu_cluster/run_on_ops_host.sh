#!/usr/bin/env bash
# Run argv on the cluster ops host when cluster_only=true; else run locally.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <executable> [arg ...]" >&2
  exit 2
fi

PYTHONPATH="${repo_root}" python3 -c '
import json, os, sys
from pathlib import Path
from scripts.yzu_cluster.cluster_ops import cluster_only, run_on_ops_host

repo = Path(".").resolve()
cfg = json.loads((repo / "config/yzu_cluster.json").read_text(encoding="utf-8"))
argv = sys.argv[2:]
timeout = int(os.environ.get("CLUSTER_OPS_TIMEOUT", "7200"))
cfg = dict(cfg)
operations = dict(cfg.get("operations") or {})
host = dict(operations.get("ops_host") or {})
if not cluster_only(cfg):
    host["mode"] = "local"
if str(host.get("mode") or "local").lower() == "local":
    # A checked-in controller path is deployment metadata, not a valid cwd for
    # every checkout (for example, a CI runner or a second worktree).
    host["repo_root"] = str(repo)
operations["ops_host"] = host
cfg["operations"] = operations
proc = run_on_ops_host(cfg, argv, timeout=timeout)
raise SystemExit(proc.returncode)
' -- "$@"
