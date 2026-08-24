#!/usr/bin/env bash
set -euo pipefail
SR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="$SR_DIR/stablecoin_skynet/data/community/google_trends_solo_full"
LOGDIR="$SR_DIR/data/datasets/stablecoin_trust_engagement/logs"
mkdir -p "$DEST" "$LOGDIR"
LOG="$LOGDIR/cluster_pull_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG") 2>&1

pull_csvs() {
  local ip="$1"
  echo "=== pull $ip ==="
  ssh -o ConnectTimeout=15 -o BatchMode=yes "user@$ip" \
    'powershell -NoProfile -Command "Get-ChildItem -Path C:\Users\user\stablecoin_trends_worker -Recurse -Filter google_trends_weekly.csv | ForEach-Object { $_.FullName }"' \
    2>/dev/null | while read -r winpath; do
      winpath="${winpath//$'\r'/}"
      [[ -z "$winpath" ]] && continue
      entity=$(echo "$winpath" | tr '\\' '/' | awk -F'/' '{print $(NF-1)}')
      mkdir -p "$DEST/$entity"
      scppath=$(echo "$winpath" | tr '\\' '/')
      scp -o ConnectTimeout=20 -q "user@$ip:$scppath" "$DEST/$entity/google_trends_weekly.csv" && echo "ok $entity" || echo "fail $entity"
    done
}

pull_csvs 100.92.237.90 || true
pull_csvs 100.102.0.84 || true
pull_csvs 100.83.34.59 || true

echo "solo count: $(find "$DEST" "$SR_DIR/stablecoin_skynet/data/community/google_trends_solo_20260714" -name google_trends_weekly.csv 2>/dev/null | wc -l)"
cd "$SR_DIR"
export PYTHONPATH="$SR_DIR"
.venv/bin/python drive/scripts/build_stablecoin_best_dataset_v1.py
cp -f "$SR_DIR/data/datasets/stablecoin_trust_engagement"/stablecoin_best_dataset_v1_*.zip "$HOME/Downloads/" 2>/dev/null || true
echo DONE
