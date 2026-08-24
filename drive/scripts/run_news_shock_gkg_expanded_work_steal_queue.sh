#!/usr/bin/env bash
# Work-steal expanded-universe GDELT queue (local optiplex or Windows cluster nodes).
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 HELPER_NAME local|windows [WINDOWS_HOSTNAME_OR_IP]" >&2
  echo "example: $0 helper_optiplex local" >&2
  echo "example: $0 helper_fgedhgv windows DESKTOP-FGEDHGV" >&2
  exit 2
fi

helper_name="$1"
worker_kind="$2"
worker_node="${3:-}"

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

QUEUE_START="${QUEUE_START:-2018-01-01}"
QUEUE_END="${QUEUE_END:-2026-07-01}"
RUN_TAG="${RUN_TAG:-20260626TexpandedZ}"
STATE_DIR="${STATE_DIR:-data_lake/news_shock_taxonomy/derived/gdelt_expanded_queue_state}"
LOCK_DIR="${LOCK_DIR:-data_lake/news_shock_taxonomy/backfill_status/gdelt_expanded_work_steal_locks}"
LOG_DIR="${LOG_DIR:-logs/news_shock_taxonomy/expanded_work_steal}"
BUILD_OVERLAY="${BUILD_OVERLAY:-1}"
POLL_SECONDS="${POLL_SECONDS:-120}"
STALE_LOCK_SECONDS="${STALE_LOCK_SECONDS:-21600}"

mkdir -p "${STATE_DIR}" "${LOCK_DIR}" "${LOG_DIR}"
SR_GDELT_TMP="${SR_GDELT_TMP:-/media/phyrexian/Transcend/sharpe-renaissance/tmp/gdelt_expanded}"
export SR_GDELT_TMP
mkdir -p "${SR_GDELT_TMP}"
python3 scripts/news_shock_taxonomy/build_expanded_universe_config.py
python3 scripts/plan_news_shock_gkg_expanded_queue.py \
  --repo-root "${repo_root}" \
  --queue-start "${QUEUE_START}" \
  --queue-end "${QUEUE_END}" \
  --run-tag "${RUN_TAG}" \
  --state-dir "${STATE_DIR}" >/dev/null

log() {
  printf '%s helper=%s kind=%s node=%s %s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    "${helper_name}" \
    "${worker_kind}" \
    "${worker_node:-optiplex}" \
    "$*"
}

artifact_complete() {
  local run_id="$1"
  local norm="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk/${run_id}/asia_gkg_filtered.csv.gz"
  local scored="data_lake/news_shock_taxonomy/processed/${run_id}/asia_gkg_scored.csv.gz"
  local panel="data_lake/news_shock_taxonomy/processed/${run_id}/daily_country_shock_panel.csv"
  # Cheap check (match plan_news_shock_gkg_expanded_queue.py): existence + 1-byte gunzip.
  # Full gzip -t on multi-GB USB artifacts serializes the whole fleet for hours.
  [[ -s "${norm}" && -s "${scored}" && -s "${panel}" ]] || return 1
  python3 - "${norm}" "${scored}" <<'PY'
import gzip, sys
try:
    for path in sys.argv[1:]:
        with gzip.open(path, "rb") as fh:
            fh.read(1)
except OSError:
    raise SystemExit(1)
raise SystemExit(0)
PY
}

build_overlay() {
  local run_id="$1"
  local norm="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk/${run_id}/asia_gkg_filtered.csv.gz"
  [[ -s "${norm}" ]] || return 0
  nice -n 10 ionice -c3 python3 scripts/news_shock_taxonomy/build_gdelt_crypto_overlay.py \
    --source-file "${norm}" \
    --window-name "${run_id}" \
    --out-dir data_lake/news_shock_taxonomy/derived/gdelt_crypto_overlay
}

month_windows() {
  python3 - "$QUEUE_START" "$QUEUE_END" "$RUN_TAG" <<'PY'
import sys
from datetime import date

def parse(v):
    y, m, d = map(int, v.split("-"))
    return date(y, m, d)

def add_month(v):
    return date(v.year + (1 if v.month == 12 else 0), 1 if v.month == 12 else v.month + 1, 1)

start, end, tag = parse(sys.argv[1]), parse(sys.argv[2]), sys.argv[3]
cur = date(start.year, start.month, 1)
idx = 0
while cur < end:
    nxt = min(add_month(cur), end)
    label = f"{cur:%Y%m%d}_{nxt:%Y%m%d}"
    run_id = f"expanded_gkg_window_{label}_{tag}"
    print(idx, cur.isoformat(), nxt.isoformat(), run_id)
    cur = nxt
    idx += 1
PY
}

run_is_active() {
  local run_id="$1"
  ps -eo pid=,cmd= \
    | grep -F "${run_id}" \
    | grep -E "fetch_gdelt_gkg_asia_bulk|score_gdelt_gkg_asia|run_news_shock_gkg_expanded" \
    | grep -v "run_news_shock_gkg_expanded_work_steal_queue" \
    >/dev/null
}

lock_is_stale() {
  local claim_dir="$1"
  [[ -d "${claim_dir}" ]] || return 1
  local now mtime
  now="$(date +%s)"
  mtime="$(stat -c %Y "${claim_dir}" 2>/dev/null || echo "${now}")"
  (( now - mtime > STALE_LOCK_SECONDS ))
}

clear_stale_claim() {
  local claim_dir="$1"
  # claim.txt makes rmdir fail; remove it first so dead helpers cannot pin months forever.
  rm -f "${claim_dir}/claim.txt" 2>/dev/null || true
  rmdir "${claim_dir}" 2>/dev/null || true
}

try_claim() {
  local run_id="$1"
  local claim_dir="${LOCK_DIR}/${run_id}.lock"
  if lock_is_stale "${claim_dir}"; then
    clear_stale_claim "${claim_dir}"
  fi
  if mkdir "${claim_dir}" 2>/dev/null; then
    {
      echo "helper=${helper_name}"
      echo "worker_kind=${worker_kind}"
      echo "worker_node=${worker_node:-optiplex}"
      echo "pid=$$"
      echo "claimed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "${claim_dir}/claim.txt"
    return 0
  fi
  return 1
}

release_claim() {
  local run_id="$1"
  local claim_dir="${LOCK_DIR}/${run_id}.lock"
  rm -f "${claim_dir}/claim.txt" 2>/dev/null || true
  rmdir "${claim_dir}" 2>/dev/null || true
}

run_worker_once() {
  local run_id="$1"
  local start_date="$2"
  local end_date="$3"
  local log="${LOG_DIR}/${run_id}.log"

  if [[ "${worker_kind}" == "local" ]]; then
    env \
      GKG_CONFIG="config/news_shock_expanded_universe.json" \
      GKG_OUT_ROOT="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk" \
      FETCH_WORKERS="${LOCAL_FETCH_WORKERS:-1}" \
      bash scripts/run_news_shock_gkg_expanded_fetch_score_worker.sh "${run_id}" "${start_date}" "${end_date}" \
      >"${log}" 2>&1
  elif [[ "${worker_kind}" == "windows" ]]; then
    [[ -n "${worker_node}" ]] || {
      echo "windows helper requires WINDOWS_HOSTNAME_OR_IP" >&2
      return 2
    }
    env \
      WINDOWS_PYTHON_EXE="${WINDOWS_PYTHON_EXE:-py}" \
      SR_GDELT_TMP="${SR_GDELT_TMP:-/media/phyrexian/Transcend/sharpe-renaissance/tmp/gdelt_expanded}" \
      bash scripts/run_news_shock_gkg_expanded_windows_worker.sh \
      "${run_id}" "${start_date}" "${end_date}" "${worker_node}" >"${log}" 2>&1
  else
    echo "unknown worker kind: ${worker_kind}" >&2
    return 2
  fi
}

find_and_run_one() {
  local saw_pending=0
  while read -r month_index start_date end_date run_id; do
    [[ -n "${run_id:-}" ]] || continue
    if artifact_complete "${run_id}"; then
      continue
    fi
    saw_pending=1
    if run_is_active "${run_id}"; then
      log "skip_active month_index=${month_index} run_id=${run_id}"
      continue
    fi
    if ! try_claim "${run_id}"; then
      log "skip_locked month_index=${month_index} run_id=${run_id}"
      continue
    fi
    log "claimed month_index=${month_index} run_id=${run_id} start=${start_date} end=${end_date}"
    if run_worker_once "${run_id}" "${start_date}" "${end_date}"; then
      if [[ "${BUILD_OVERLAY}" == "1" ]] && artifact_complete "${run_id}"; then
        build_overlay "${run_id}" >>"${LOG_DIR}/${run_id}.log" 2>&1 || true
      fi
      log "complete run_id=${run_id}"
    else
      log "failed run_id=${run_id} see ${LOG_DIR}/${run_id}.log"
    fi
    release_claim "${run_id}"
    return 0
  done < <(month_windows)

  if (( saw_pending == 0 )); then
    log "queue_finished_no_pending"
    return 2
  fi
  return 1
}

log "queue_started start=${QUEUE_START} end=${QUEUE_END} run_tag=${RUN_TAG}"

desk_yield_pause() {
  python3 - "${repo_root}" <<'PY'
import sys
from pathlib import Path

from scripts.research_data_mcp.desk_runtime import fleet_should_yield

if fleet_should_yield(Path(sys.argv[1])):
    raise SystemExit(0)
raise SystemExit(1)
PY
}

while true; do
  if desk_yield_pause; then
    log "desk_active_yield sleep=${POLL_SECONDS}"
    sleep "${POLL_SECONDS}"
    continue
  fi
  set +e
  find_and_run_one
  status=$?
  set -e
  if (( status == 0 )); then
    continue
  fi
  if (( status == 2 )); then
    break
  fi
  log "no_claimable_work sleep=${POLL_SECONDS}"
  sleep "${POLL_SECONDS}"
done

python3 scripts/plan_news_shock_gkg_expanded_queue.py \
  --repo-root "${repo_root}" \
  --queue-start "${QUEUE_START}" \
  --queue-end "${QUEUE_END}" \
  --run-tag "${RUN_TAG}" \
  --state-dir "${STATE_DIR}"
