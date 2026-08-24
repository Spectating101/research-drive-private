#!/usr/bin/env bash
# Overnight CRSP index tier: download → ingest → status manifest.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT:$ROOT/kernel"

LOG="${CRSP_OVERNIGHT_LOG:-data_lake/crsp/overnight_run.log}"
STATUS="${CRSP_OVERNIGHT_STATUS:-data_lake/crsp/overnight_status.json}"
mkdir -p data_lake/crsp/raw data_lake/crsp/processed

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG"; }

log "=== CRSP overnight run start (tier=index) ==="

if python3 scripts/crsp_moveit_sync.py --tier index --json >>"$LOG" 2>&1; then
  SYNC_OK=1
  log "sync: OK"
else
  SYNC_OK=0
  log "sync: FAILED (see log)"
fi

INGEST_OK=0
if [[ "$SYNC_OK" == "1" ]]; then
  if python3 scripts/ingest_crsp_package.py --product stock_index_1925_annsub --json >>"$LOG" 2>&1; then
    INGEST_OK=1
    log "ingest: OK"
  else
    log "ingest: FAILED (see log)"
  fi
fi

ZIP="data_lake/crsp/raw/stock_index_1925_annsub/fiz202412_cadb.zip"
BYTES=0
if [[ -f "$ZIP" ]]; then
  BYTES=$(stat -c%s "$ZIP" 2>/dev/null || echo 0)
fi

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

root = Path("$ROOT")
status = {
    "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "sync_ok": bool(int("$SYNC_OK")),
    "ingest_ok": bool(int("$INGEST_OK")),
    "zip_bytes": int("$BYTES"),
    "zip_target_bytes": 2269342522,
    "log": str(Path("$LOG").relative_to(root)),
}
Path("$STATUS").write_text(json.dumps(status, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(status, indent=2))
PY

log "=== CRSP overnight run end ==="
