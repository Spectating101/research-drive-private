#!/usr/bin/env bash
# Monthly expanded-universe GDELT queue (Asia + global adjunct). Forward/backfill from QUEUE_START.
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

QUEUE_START="${QUEUE_START:-2018-01-01}"
QUEUE_END="${QUEUE_END:-2026-07-01}"
RUN_TAG="${RUN_TAG:-20260626TexpandedZ}"
WORKER_NODE="${WORKER_NODE:-DESKTOP-FGEDHGV}"
STATE_DIR="${STATE_DIR:-data_lake/news_shock_taxonomy/derived/gdelt_expanded_queue_state}"
LOG_DIR="${LOG_DIR:-logs/news_shock_taxonomy/expanded_queue}"
BUILD_OVERLAY="${BUILD_OVERLAY:-1}"

mkdir -p "${STATE_DIR}" "${LOG_DIR}"
SR_GDELT_TMP="${SR_GDELT_TMP:-/media/phyrexian/Transcend/sharpe-renaissance/tmp/gdelt_expanded}"
export SR_GDELT_TMP
mkdir -p "${SR_GDELT_TMP}"
python3 scripts/news_shock_taxonomy/build_expanded_universe_config.py

artifact_complete() {
  local run_id="$1"
  local norm="data_lake/news_shock_taxonomy/normalized/gdelt_gkg_expanded_bulk/${run_id}/asia_gkg_filtered.csv.gz"
  local scored="data_lake/news_shock_taxonomy/processed/${run_id}/asia_gkg_scored.csv.gz"
  local panel="data_lake/news_shock_taxonomy/processed/${run_id}/daily_country_shock_panel.csv"
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
while cur < end:
    nxt = min(add_month(cur), end)
    label = f"{cur:%Y%m%d}_{nxt:%Y%m%d}"
    run_id = f"expanded_gkg_window_{label}_{tag}"
    print(cur.isoformat(), nxt.isoformat(), run_id)
    cur = nxt
PY
}

total=0
done=0
while IFS=' ' read -r start_date end_date run_id; do
  total=$((total + 1))
  if artifact_complete "${run_id}"; then
    done=$((done + 1))
    echo "skip_complete ${run_id}"
    continue
  fi
  echo "queue_run_at=$(date -u +%Y-%m-%dT%H:%M:%SZ) run_id=${run_id} start=${start_date} end=${end_date}"
  log="${LOG_DIR}/${run_id}.log"
  if bash scripts/run_news_shock_gkg_expanded_windows_worker.sh "${run_id}" "${start_date}" "${end_date}" "${WORKER_NODE}" \
    >"${log}" 2>&1; then
    done=$((done + 1))
    if [[ "${BUILD_OVERLAY}" == "1" ]]; then
      build_overlay "${run_id}" >>"${log}" 2>&1 || true
    fi
  else
    echo "failed ${run_id} see ${log}" >&2
  fi
  printf '%s|%s|%s\n' "$(date -Iseconds)" "${done}" "${total}" > "${STATE_DIR}/current.txt"
done < <(month_windows)

printf '%s\n' "${total}" > "${STATE_DIR}/total_months.txt"
printf '%s\n' "${done}" > "${STATE_DIR}/completed_months.txt"
echo "expanded_queue_done completed=${done}/${total}"
