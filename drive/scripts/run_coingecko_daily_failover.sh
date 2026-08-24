#!/usr/bin/env bash
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
cd "$ROOT"

mkdir -p logs

COINGECKO_DAILY_UNIVERSE="${COINGECKO_DAILY_UNIVERSE:-clean}"
if [[ "$COINGECKO_DAILY_UNIVERSE" == "full" ]]; then
  PRICE_PANEL="$ROOT/data_lake/crypto_pipeline/exports/price_panel_wide.csv"
else
  PRICE_PANEL="$ROOT/data_lake/crypto_pipeline/exports/price_panel_clean.csv"
fi
MCAP_PANEL="$ROOT/data_lake/crypto_pipeline/exports/mcap_panel_wide.csv"
VOL_PANEL="$ROOT/data_lake/crypto_pipeline/exports/volume_panel_wide.csv"
STATE_DIR="${COINGECKO_FAILOVER_STATE_DIR:-$ROOT/data_lake/crypto_pipeline/failover_state}"
LOCK_FILE="${XDG_RUNTIME_DIR:-/tmp}/coingecko_daily_failover.lock"
RANDOM_DELAY_MAX_SEC="${COINGECKO_FAILOVER_RANDOM_DELAY_MAX_SEC:-1800}"
MACHINE_ID="${COINGECKO_MACHINE_ID:-$(hostname -s 2>/dev/null || hostname || uname -n)}"
SYNC_BACK_DEST="${COINGECKO_SYNC_BACK_DEST:-}"
SYNC_BACK_RETRIES="${COINGECKO_SYNC_BACK_RETRIES:-3}"
SYNC_BACK_RETRY_DELAY_SEC="${COINGECKO_SYNC_BACK_RETRY_DELAY_SEC:-20}"
SYNC_BACK_TIMEOUT_SEC="${COINGECKO_SYNC_BACK_TIMEOUT_SEC:-300}"
SYNC_BACK_SSH_COMMAND="${COINGECKO_SYNC_BACK_SSH_COMMAND:-}"
TODAY="$(date -u +%F)"
NOW_UTC="$(date -u +%FT%TZ)"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

mkdir -p \
  "$STATE_DIR/machines" \
  "$STATE_DIR/attempts/$TODAY" \
  "$STATE_DIR/success/$TODAY"

panel_has_today() {
  [[ -f "$PRICE_PANEL" ]] && tail -n 1 "$PRICE_PANEL" | grep -q "^${TODAY},"
}

write_state() {
  local path="$1"
  local status="$2"

  cat >"$path" <<EOF
{
  "machine_id": "${MACHINE_ID}",
  "date": "${TODAY}",
  "status": "${status}",
  "timestamp_utc": "${NOW_UTC}"
}
EOF
}

sync_back_panels() {
  if [[ -z "${SYNC_BACK_DEST}" ]]; then
    return 0
  fi

  if ! command -v rsync >/dev/null 2>&1; then
    echo "[warn] sync-back requested but rsync is not installed" >&2
    return 1
  fi

  local -a rsync_cmd=(
    rsync
    -az
    --partial
    --inplace
    --no-owner
    --no-group
    --human-readable
  )

  if [[ -n "${SYNC_BACK_SSH_COMMAND}" ]]; then
    rsync_cmd+=(-e "${SYNC_BACK_SSH_COMMAND}")
  fi

  local attempt=1
  local rc=0

  while [[ "${attempt}" -le "${SYNC_BACK_RETRIES}" ]]; do
    echo "[sync] attempt ${attempt}/${SYNC_BACK_RETRIES} -> ${SYNC_BACK_DEST}"
    if timeout "${SYNC_BACK_TIMEOUT_SEC}" "${rsync_cmd[@]}" \
      "${PRICE_PANEL}" \
      "${MCAP_PANEL}" \
      "${VOL_PANEL}" \
      "${SYNC_BACK_DEST}"; then
      echo "[sync] panel sync-back completed"
      return 0
    fi

    rc=$?
    if [[ "${attempt}" -lt "${SYNC_BACK_RETRIES}" ]]; then
      echo "[sync] attempt ${attempt} failed (rc=${rc}); retrying in ${SYNC_BACK_RETRY_DELAY_SEC}s" >&2
      sleep "${SYNC_BACK_RETRY_DELAY_SEC}"
    fi
    attempt=$((attempt + 1))
  done

  echo "[warn] panel sync-back failed after ${SYNC_BACK_RETRIES} attempts" >&2
  return "${rc}"
}

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[skip] local failover lock is already held on this machine"
  exit 0
fi

write_state "$STATE_DIR/machines/${MACHINE_ID}.json" "heartbeat"
write_state "$STATE_DIR/attempts/$TODAY/${MACHINE_ID}.json" "scheduled"

if panel_has_today; then
  echo "[skip] ${TODAY} is already present in $(basename "$PRICE_PANEL")"
  write_state "$STATE_DIR/success/$TODAY/${MACHINE_ID}.skip.json" "already_present"
  exit 0
fi

if [[ "${RANDOM_DELAY_MAX_SEC}" -gt 0 ]]; then
  DELAY_SEC="$("$PYTHON_BIN" - "$RANDOM_DELAY_MAX_SEC" <<'PY'
import random
import sys

max_delay = max(0, int(sys.argv[1]))
print(random.randint(0, max_delay) if max_delay else 0)
PY
)"
  if [[ "${DELAY_SEC}" -gt 0 ]]; then
    echo "[wait] sleeping ${DELAY_SEC}s before attempting daily update"
    sleep "${DELAY_SEC}"
  fi
fi

NOW_UTC="$(date -u +%FT%TZ)"

if panel_has_today; then
  echo "[skip] ${TODAY} was synced by another machine during the delay window"
  write_state "$STATE_DIR/success/$TODAY/${MACHINE_ID}.skip.json" "seen_after_delay"
  exit 0
fi

echo "[run] machine=${MACHINE_ID} date=${TODAY} mode=daily api=public"
env PYTHONUNBUFFERED=1 "$PYTHON_BIN" scripts/coingecko_panel_update.py \
  --mode daily \
  --universe "$COINGECKO_DAILY_UNIVERSE" \
  --min-price-points "${COINGECKO_DAILY_MIN_PRICE_POINTS:-0}" \
  --use-public-api

NOW_UTC="$(date -u +%FT%TZ)"

if panel_has_today; then
  echo "[ok] ${TODAY} daily snapshot completed on ${MACHINE_ID}"
  if sync_back_panels; then
    status="success"
    if [[ -n "${SYNC_BACK_DEST}" ]]; then
      status="success_synced"
    fi
    write_state "$STATE_DIR/success/$TODAY/${MACHINE_ID}.json" "${status}"
    exit 0
  fi

  write_state "$STATE_DIR/attempts/$TODAY/${MACHINE_ID}.sync_failed.json" "sync_back_failed"
  exit 1
fi

echo "[warn] updater exited but ${TODAY} is still missing from $(basename "$PRICE_PANEL")" >&2
write_state "$STATE_DIR/attempts/$TODAY/${MACHINE_ID}.failed.json" "missing_after_run"
exit 1
