#!/usr/bin/env bash
# Full CRSP US core pipeline: index + stock download, ingest, compustat/ccm attempts, audit refresh.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT:$ROOT/kernel"

LOG="$ROOT/data_lake/crsp/finish_all_run.log"
STATUS="$ROOT/data_lake/crsp/finish_all_status.json"
mkdir -p data_lake/crsp/raw data_lake/crsp/processed data_lake/compustat/raw

log() { echo "[$(date -Iseconds)] $*" | tee -a "$LOG"; }

run_step() {
  local name="$1"
  shift
  log ">>> $name"
  if "$@" >>"$LOG" 2>&1; then
    log "$name: OK"
    return 0
  fi
  log "$name: FAILED"
  return 1
}

log "=== CRSP finish-all start ==="

SYNC_OK=0
INGEST_OK=0
COMP_OK=0
CCM_OK=0

if run_step "sync us_core (index+stock)" python3 scripts/crsp_moveit_sync.py --tier us_core --json; then
  SYNC_OK=1
fi

if run_step "ingest all downloaded" python3 scripts/ingest_crsp_package.py --all-downloaded --json; then
  INGEST_OK=1
fi

run_step "crsp registry stamp" python3 scripts/sync_crsp_ingest_registry.py --json || true

if run_step "compustat ingest" python3 scripts/ingest_compustat_export.py --json; then
  COMP_OK=1
else
  log "compustat: skipped (no export in raw/)"
fi

if run_step "ccm link" python3 scripts/build_crsp_compustat_ccm_link.py --json; then
  CCM_OK=1
else
  log "ccm: skipped (no link file)"
fi

run_step "registry materialization sync" python3 scripts/sync_materialized_registry.py --json || true
run_step "platform audit refresh" python3 drive/scripts/sync_drive_platform_state.py || true

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path

root = Path("$ROOT")
zip_index = root / "data_lake/crsp/raw/stock_index_1925_annsub/fiz202412_cadb.zip"
zip_stock = root / "data_lake/crsp/raw/stock_25i_si_ascii_annual/siz202412_ascii.zip"

def _bytes(p: Path) -> int:
    return p.stat().st_size if p.is_file() else 0

status = {
    "finished_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    "sync_ok": bool(int("$SYNC_OK")),
    "ingest_ok": bool(int("$INGEST_OK")),
    "compustat_ok": bool(int("$COMP_OK")),
    "ccm_ok": bool(int("$CCM_OK")),
    "index_zip_bytes": _bytes(zip_index),
    "index_zip_target": 2269342522,
    "stock_zip_bytes": _bytes(zip_stock),
    "stock_zip_target": 4273999872,
    "log": "data_lake/crsp/finish_all_run.log",
}
Path("$STATUS").write_text(json.dumps(status, indent=2) + "\\n", encoding="utf-8")
print(json.dumps(status, indent=2))
PY

log "=== CRSP finish-all end ==="
