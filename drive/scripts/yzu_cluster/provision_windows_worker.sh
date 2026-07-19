#!/usr/bin/env bash
# Bootstrap Sharpe-Renaissance on joined Windows workers (required for remote queue/pipelines).
set -euo pipefail

SR_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INVENTORY="${WINDOWS_INVENTORY:-/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv}"
SSH_KEY="${SSH_KEY:-/home/phyrexian/.ssh/id_rsa}"
REMOTE_SR="${REMOTE_SR:-C:/cw/Sharpe-Renaissance}"
REMOTE_PARENT="$(dirname "$REMOTE_SR" | tr '\\' '/')"

echo "Provision Windows workers: $REMOTE_SR"
echo "Source (optiplex): $SR_ROOT"
echo ""

if [[ ! -f "$INVENTORY" ]]; then
  echo "Inventory not found: $INVENTORY" >&2
  exit 1
fi

while IFS=, read -r hostname tailscale_ip user status _rest; do
  [[ "$hostname" == "hostname" ]] && continue
  [[ "$status" != "joined" ]] && continue
  target="${user:-user}@${tailscale_ip}"
  echo "=== $hostname ($target) ==="

  ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=15 "$target" \
    "powershell.exe -NoProfile -Command \"
      New-Item -ItemType Directory -Force -Path '$REMOTE_PARENT' | Out-Null
      if (Test-Path '$REMOTE_SR\\.venv\\Scripts\\python.exe') {
        Write-Host 'Already provisioned'
        exit 0
      }
      if (-not (Test-Path '$REMOTE_SR')) {
        Write-Host 'Creating $REMOTE_SR — run full sync from optiplex (see below)'
        New-Item -ItemType Directory -Force -Path '$REMOTE_SR' | Out-Null
        exit 2
      }
      Write-Host 'Repo dir exists but venv missing'
      exit 3
    \"" && echo "OK: $hostname" || echo "NEEDS_SYNC: $hostname — copy repo to $REMOTE_SR and run .venv setup"
done < "$INVENTORY"

cat <<EOF

Next steps (per worker that needs sync):
  1. On optiplex, rsync or robocopy Sharpe-Renaissance to the worker at $REMOTE_SR
  2. On worker: cd $REMOTE_SR && py -3 -m venv .venv && .venv\\Scripts\\pip install -e .
  3. Re-run: python scripts/yzu_cluster/windows_lab_readiness.py (via probe in cluster status)

Until provisioned, jobs run on optiplex (prefer_local_queue + disable_local_http_collect=false).
EOF
