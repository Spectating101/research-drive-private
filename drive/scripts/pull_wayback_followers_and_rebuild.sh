#!/usr/bin/env bash
set -euo pipefail
SR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEST="$SR_DIR/data/datasets/stablecoin_trust_engagement/wayback_followers_monthly"
LOGDIR="$SR_DIR/data/datasets/stablecoin_trust_engagement/logs"
mkdir -p "$DEST" "$LOGDIR"
LOG="$LOGDIR/wayback_pull_$(date -u +%Y%m%dT%H%M%SZ).log"
exec > >(tee -a "$LOG") 2>&1

POINTS="$DEST/wayback_follower_points.csv"
TMP=$(mktemp)

pull_ip() {
  local ip="$1"
  echo "=== pull $ip ==="
  remote='C:/Users/user/wayback_follower_worker/out/wayback_follower_points.csv'
  local_tmp="$DEST/from_${ip//./_}.csv"
  scp -o ConnectTimeout=20 -q "user@$ip:$remote" "$local_tmp" 2>/dev/null && echo "got $local_tmp" || echo "no file yet $ip"
}

pull_ip 100.92.237.90 || true
pull_ip 100.102.0.84 || true
pull_ip 100.83.34.59 || true

# Merge all point CSVs (local + remote pulls), dedupe by handle|memento_ts
python3 - << PY
from pathlib import Path
import pandas as pd
dest = Path("$DEST")
files = list(dest.glob("from_*.csv")) + [dest / "wayback_follower_points.csv"]
dfs = []
for f in files:
    if f.exists() and f.stat().st_size > 50:
        try:
            dfs.append(pd.read_csv(f))
        except Exception as e:
            print("skip", f, e)
if not dfs:
    print("no points yet")
    raise SystemExit(0)
df = pd.concat(dfs, ignore_index=True)
df = df.drop_duplicates(subset=["twitter_handle", "memento_ts"], keep="last")
df.to_csv(dest / "wayback_follower_points.csv", index=False)
ok = df["followers"].notna() & (df["followers"].astype(str) != "")
print({"rows": len(df), "parsed": int(ok.sum()), "handles": int(df.twitter_handle.nunique())})
PY

cd "$SR_DIR"
.venv/bin/python drive/scripts/harvest_wayback_twitter_followers.py rollup --out "$DEST"

# Append archive growth into best dataset rebuild if builder exists
if [ -f drive/scripts/build_stablecoin_best_dataset_v1.py ]; then
  .venv/bin/python drive/scripts/build_stablecoin_best_dataset_v1.py || true
fi
echo DONE
