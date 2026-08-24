#!/usr/bin/env bash
# Manage expanded GDELT work-steal fleet (start | stop | status | ensure).
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

ACTION="${1:-status}"
FLEET_CONFIG="${FLEET_CONFIG:-config/gdelt_expanded_fleet.json}"
LOG_DIR="${LOG_DIR:-logs/news_shock_taxonomy/expanded_work_steal}"
PID_DIR="${PID_DIR:-logs/news_shock_taxonomy/expanded_work_steal/fleet}"
SSH_KEY="${CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
KNOWN_HOSTS="${HOME}/.ssh/known_hosts"

usage() {
  echo "usage: $0 {start|stop|status|ensure|probe}" >&2
  echo "  start   — launch all enabled workers (skip if already running)" >&2
  echo "  stop    — stop all fleet helpers" >&2
  echo "  status  — manifest + per-worker process state" >&2
  echo "  ensure  — probe SSH, refresh plan, start missing helpers (idempotent)" >&2
  echo "  probe   — SSH reachability for enabled workers" >&2
  exit 2
}

[[ -f "${FLEET_CONFIG}" ]] || {
  echo "missing fleet config: ${FLEET_CONFIG}" >&2
  exit 1
}

mkdir -p "${LOG_DIR}" "${PID_DIR}"

fleet_env() {
  python3 - "${FLEET_CONFIG}" <<'PY'
import json
import sys
from pathlib import Path

cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
lanes = cfg.get("lanes") or {}
default_py = cfg.get("default_windows_python_exe") or "C:\\Users\\user\\anaconda3\\python.exe"
poll = str(cfg.get("poll_seconds", 60))
for w in cfg.get("workers") or []:
    if not w.get("enabled", True):
        continue
    lane = lanes.get(w.get("lane") or "full") or lanes.get("full") or {}
    wid = w["id"]
    kind = w.get("kind") or "windows"
    host = w.get("host") or "optiplex"
    user = w.get("user") or "user"
    py = w.get("windows_python_exe") or default_py
    qs = lane.get("queue_start", "2018-01-01")
    qe = lane.get("queue_end", cfg.get("queue_end", "2026-07-01"))
    tag = cfg.get("run_tag", "20260626TexpandedZ")
    tmp = cfg.get("sr_gdelt_tmp", "")
    overlay = "1" if cfg.get("build_overlay", True) else "0"
    print(
        f'{wid}\t{kind}\t{host}\t{user}\t{py}\t{qs}\t{qe}\t{tag}\t{tmp}\t{overlay}\t{poll}'
    )
PY
}

resolve_ip() {
  local host="$1"
  local inv="${2:-/home/phyrexian/cluster-lab-logs/windows-cluster-inventory.csv}"
  awk -F, -v h="${host}" '
    NR > 1 && $1 == h && $4 == "joined" { print $2; exit }
  ' "${inv}"
}

helper_running() {
  local helper_id="$1"
  pgrep -f "run_news_shock_gkg_expanded_work_steal_queue.sh helper_${helper_id} " >/dev/null 2>&1
}

start_worker() {
  local helper_id="$1" kind="$2" host="$3" user="$4" pyexe="$5" qstart="$6" qend="$7" tag="$8" tmp="$9" overlay="${10}" poll="${11}"
  local log="${LOG_DIR}/helper_${helper_id}.log"
  local pidfile="${PID_DIR}/helper_${helper_id}.pid"

  if helper_running "${helper_id}"; then
    echo "skip_running helper_${helper_id} kind=${kind} host=${host}"
    return 0
  fi

  if [[ "${kind}" == "local" ]]; then
    echo "starting helper_${helper_id} kind=local lane=${qstart}..${qend}"
    nohup env \
      QUEUE_START="${qstart}" \
      QUEUE_END="${qend}" \
      RUN_TAG="${tag}" \
      BUILD_OVERLAY="${overlay}" \
      SR_GDELT_TMP="${tmp}" \
      TMPDIR="${tmp}" \
      POLL_SECONDS="${poll}" \
      LOCAL_FETCH_WORKERS="${LOCAL_FETCH_WORKERS:-2}" \
      bash scripts/run_news_shock_gkg_expanded_work_steal_queue.sh "helper_${helper_id}" local \
      >>"${log}" 2>&1 &
    echo $! >"${pidfile}"
    return 0
  fi

  local ip
  ip="$(resolve_ip "${host}")" || true
  if [[ -z "${ip}" ]]; then
    echo "skip_no_inventory helper_${helper_id} host=${host}" >&2
    return 1
  fi

  if ! ssh-keygen -F "[${ip}]:22" >/dev/null 2>&1 && ! ssh-keygen -F "${ip}" >/dev/null 2>&1; then
    ssh-keyscan -H "${ip}" 2>/dev/null >>"${KNOWN_HOSTS}" || true
  fi

  if ! ssh -n -i "${SSH_KEY}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 \
    "${user}@${ip}" "hostname" >/dev/null 2>&1; then
    echo "skip_unreachable helper_${helper_id} ${user}@${ip}" >&2
    return 1
  fi

  echo "starting helper_${helper_id} host=${host} lane=${qstart}..${qend}"
  nohup env \
    QUEUE_START="${qstart}" \
    QUEUE_END="${qend}" \
    RUN_TAG="${tag}" \
    BUILD_OVERLAY="${overlay}" \
    SR_GDELT_TMP="${tmp}" \
    TMPDIR="${tmp}" \
    POLL_SECONDS="${poll}" \
    WINDOWS_PYTHON_EXE="${pyexe}" \
    bash scripts/run_news_shock_gkg_expanded_work_steal_queue.sh "helper_${helper_id}" windows "${host}" \
    >>"${log}" 2>&1 &
  echo $! >"${pidfile}"
}

stop_workers() {
  pkill -f "run_news_shock_gkg_expanded_work_steal_queue.sh helper_" 2>/dev/null || true
  rm -f "${PID_DIR}"/*.pid 2>/dev/null || true
  echo "fleet_stopped"
}

show_status() {
  python3 scripts/plan_news_shock_gkg_expanded_queue.py 2>/dev/null || true
  echo "--- workers ---"
  while IFS=$'\t' read -r helper_id kind host user _py _qs _qe _tag _tmp _ov _poll; do
  [[ -n "${helper_id}" ]] || continue
    if helper_running "${helper_id}"; then
      echo "RUNNING helper_${helper_id} ${kind} ${host}"
    else
      echo "STOPPED helper_${helper_id} ${kind} ${host}"
    fi
  done < <(fleet_env)
  echo "--- locks ---"
  lock_dir="data_lake/news_shock_taxonomy/backfill_status/gdelt_expanded_work_steal_locks"
  if [[ -d "${lock_dir}" ]]; then
    find "${lock_dir}" -name '*.lock' 2>/dev/null | wc -l | xargs -I{} echo "active_locks={}"
  fi
}

probe_workers() {
  set +e
  while IFS=$'\t' read -r helper_id kind host user _py _qs _qe _tag _tmp _ov _poll; do
    [[ -n "${helper_id}" ]] || continue
    if [[ "${kind}" == "local" ]]; then
      echo "OK ${helper_id} local"
      continue
    fi
    ip="$(resolve_ip "${host}")"
    if [[ -z "${ip}" ]]; then
      echo "MISSING_INVENTORY ${helper_id} ${host}"
      continue
    fi
    if ssh -n -i "${SSH_KEY}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 \
      "${user}@${ip}" "hostname" 2>/dev/null; then
      echo "OK ${helper_id} ${user}@${ip}"
    else
      echo "FAIL ${helper_id} ${user}@${ip}"
    fi
  done < <(fleet_env)
  set -e
}

case "${ACTION}" in
  start | ensure)
  python3 scripts/plan_news_shock_gkg_expanded_queue.py >/dev/null
  started=0
  failed=0
  set +e
  while IFS=$'\t' read -r helper_id kind host user pyexe qstart qend tag tmp overlay poll; do
    [[ -n "${helper_id}" ]] || continue
    if start_worker "${helper_id}" "${kind}" "${host}" "${user}" "${pyexe}" "${qstart}" "${qend}" "${tag}" "${tmp}" "${overlay}" "${poll}"; then
      started=$((started + 1))
    else
      failed=$((failed + 1))
    fi
  done < <(fleet_env)
  set -e
  echo "fleet_${ACTION} started=${started} failed=${failed}"
  ;;
  stop)
  stop_workers
  ;;
  status)
  show_status
  ;;
  probe)
  probe_workers
  ;;
  *)
  usage
  ;;
esac
