#!/usr/bin/env bash
# Sync spectator engine to joined Windows workers (node + Molina scripts path).
set -euo pipefail

SR_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INVENTORY="${WINDOWS_INVENTORY:-/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv}"
SSH_KEY="${SSH_KEY:-/home/phyrexian/.ssh/id_rsa}"
REMOTE_MOLINA="${REMOTE_MOLINA:-C:/cw/Molina-Optiplex}"
REMOTE_SR="${REMOTE_SR:-C:/cw/Sharpe-Renaissance}"

if [[ ! -f "$INVENTORY" ]]; then
  echo "Inventory not found: $INVENTORY" >&2
  exit 1
fi

echo "Syncing spectator engine to joined Windows workers..."
while IFS=, read -r hostname tailscale_ip user status _rest; do
  [[ "$hostname" == "hostname" ]] && continue
  [[ "$status" != "joined" ]] && continue
  target="${user:-user}@${tailscale_ip}"
  echo "--- $hostname ($target) ---"
  ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=10 "$target" \
    "powershell.exe -NoProfile -Command \"
      if (-not (Test-Path '$REMOTE_SR/scripts/yzu_cluster/workers/scraper_dispatch.sh')) { Write-Host 'Sharpe repo missing at $REMOTE_SR'; exit 2 }
      if (-not (Test-Path '$REMOTE_MOLINA/scripts/spectator_scrape_cake.mjs')) { Write-Host 'Molina spectator scripts missing'; exit 3 }
      node --version
    \"" || echo "WARN: probe failed for $hostname"
done < "$INVENTORY"

echo "Local optiplex install:"
bash "$SR_ROOT/scripts/yzu_cluster/install_spectator_engine.sh"
echo "Done. Configure REMOTE_MOLINA/REMOTE_SR if your lab paths differ."
