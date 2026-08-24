#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SHARD_COUNT="${SHARD_COUNT:-4}"
SLEEP_SECS="${SLEEP_SECS:-0.35}"
TIMEOUT_SECS="${TIMEOUT_SECS:-120}"
RETRIES="${RETRIES:-5}"
STATUS_UPLOAD_EVERY="${STATUS_UPLOAD_EVERY:-250}"
LOG_ROOT="logs/crypto_landscape_history_backfill/protocol_shards"
mkdir -p "$LOG_ROOT"

echo "starting protocol-only shards: count=${SHARD_COUNT} sleep=${SLEEP_SECS}" | tee -a "$LOG_ROOT/orchestrator.log"
date -Is | tee -a "$LOG_ROOT/orchestrator.log"

pids=()
for shard in $(seq 0 "$((SHARD_COUNT - 1))"); do
  shard_dir="$LOG_ROOT/shard_${shard}_of_${SHARD_COUNT}"
  mkdir -p "$shard_dir"
  (
    python3 scripts/backfill_crypto_landscape_history_drive.py \
      --no-overviews \
      --no-chains \
      --no-stablecoins \
      --no-upload-local-coingecko-db \
      --no-upload-discovery \
      --protocol-shards "$SHARD_COUNT" \
      --protocol-shard-index "$shard" \
      --sleep "$SLEEP_SECS" \
      --timeout "$TIMEOUT_SECS" \
      --retries "$RETRIES" \
      --status-upload-every "$STATUS_UPLOAD_EVERY" \
      --stage-root "/tmp/sharpe_crypto_landscape_history_shard_${shard}_of_${SHARD_COUNT}" \
      --state-dir "$shard_dir" \
      --status-filename "backfill_status_protocol_shard_${shard}_of_${SHARD_COUNT}.jsonl"
  ) >"$shard_dir/run.log" 2>&1 &
  pids+=("$!")
  echo "launched shard ${shard}/${SHARD_COUNT} pid=${pids[-1]}" | tee -a "$LOG_ROOT/orchestrator.log"
done

failed=0
for pid in "${pids[@]}"; do
  if ! wait "$pid"; then
    failed=1
    echo "shard pid ${pid} failed" | tee -a "$LOG_ROOT/orchestrator.log"
  fi
done

summary="$LOG_ROOT/parallel_protocol_shards_summary.json"
python3 - <<'PY' "$LOG_ROOT" "$SHARD_COUNT" "$summary"
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

log_root = Path(sys.argv[1])
shard_count = int(sys.argv[2])
summary_path = Path(sys.argv[3])
summary = {
    "ts": datetime.now(UTC).isoformat(),
    "status": "done",
    "shard_count": shard_count,
    "shards": [],
}
for shard in range(shard_count):
    status_path = log_root / f"shard_{shard}_of_{shard_count}" / f"backfill_status_protocol_shard_{shard}_of_{shard_count}.jsonl"
    counts = {}
    last = None
    if status_path.exists():
        for line in status_path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            last = row
            status = row.get("status")
            if status:
                counts[status] = counts.get(status, 0) + 1
    summary["shards"].append({
        "shard": shard,
        "status_path": str(status_path),
        "status_counts": counts,
        "last": last,
    })
summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
PY

rclone copyto "$summary" \
  "gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/markets/crypto-landscape/historical_backfill/manifests/parallel_protocol_shards_summary.json" \
  --stats-one-line || true

if [[ "$failed" -ne 0 ]]; then
  echo "one or more shards failed" | tee -a "$LOG_ROOT/orchestrator.log"
  exit 1
fi

echo "all protocol shards finished successfully" | tee -a "$LOG_ROOT/orchestrator.log"
date -Is | tee -a "$LOG_ROOT/orchestrator.log"
