#!/usr/bin/env bash
# Sync minimal Playwright scraper bundle to joined Windows workers (Etherscan backfill lane).
set -uo pipefail

SR_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
INVENTORY="${WINDOWS_INVENTORY:-/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv}"
SSH_KEY="${SSH_KEY:-/home/phyrexian/.ssh/id_rsa}"
REMOTE_SR="${REMOTE_SR:-C:/cw/Sharpe-Renaissance}"
BUNDLE="/tmp/sr_scraper_bundle_$$.tgz"

cleanup() { rm -f "$BUNDLE"; }
trap cleanup EXIT

echo "Building scraper bundle from $SR_ROOT"
tar -C "$SR_ROOT" -czf "$BUNDLE" \
  scripts/yzu_cluster/scrapers/generic_url_scrape.mjs \
  scripts/yzu_cluster/workers/scraper_dispatch.sh

remote_ps() {
  local target="$1"
  local user_name="$2"
  local ps1
  ps1="$(mktemp)"
  cat >"$ps1" <<EOF
\$ErrorActionPreference = 'Stop'
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
  winget install OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements --scope user
}
New-Item -ItemType Directory -Force -Path '${REMOTE_SR}/scripts/yzu_cluster/scrapers' | Out-Null
New-Item -ItemType Directory -Force -Path '${REMOTE_SR}/data_lake/spectator_engine/scrapes' | Out-Null
Set-Location '${REMOTE_SR}'
tar -xzf C:/Users/${user_name}/sr_scraper_bundle.tgz -C '${REMOTE_SR}'
if (-not (Test-Path package.json)) {
@'
{
  "name": "sr-scraper-host",
  "private": true,
  "type": "module",
  "dependencies": { "playwright": "^1.52.0" }
}
'@ | Set-Content -Encoding UTF8 package.json
}
if (-not (Test-Path node_modules/playwright)) {
  \$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
  npm install --omit=dev --no-fund --no-audit playwright@1.52.0
        npx playwright install chrome 2>$null; if ($LASTEXITCODE -ne 0) { npx playwright install chrome --force }
}
if (Test-Path scripts/yzu_cluster/scrapers/generic_url_scrape.mjs) { Write-Output SCRAPER_OK } else { Write-Output SCRAPER_MISSING }
EOF
  scp -q -i "$SSH_KEY" -o BatchMode=yes "$ps1" "$target:C:/Users/${user_name}/provision_scraper.ps1"
  ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=120 "$target" \
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/Users/${user_name}/provision_scraper.ps1"
  rm -f "$ps1"
}

while IFS=, read -r hostname tailscale_ip user status _rest; do
  [[ "$hostname" == "hostname" ]] && continue
  [[ "$status" != "joined" ]] && continue
  user_name="${user:-user}"
  target="${user_name}@${tailscale_ip}"
  echo ""
  echo "=== $hostname ($target) ==="
  scp -q -i "$SSH_KEY" -o BatchMode=yes "$BUNDLE" "$target:C:/Users/${user_name}/sr_scraper_bundle.tgz"
  remote_ps "$target" "$user_name" || echo "WARN: provision failed on $hostname"
done < "$INVENTORY"

echo ""
echo "Re-probe readiness:"
cd "$SR_ROOT"
PYTHONPATH=. .venv/bin/python scripts/yzu_cluster/windows_lab_readiness.py --force
