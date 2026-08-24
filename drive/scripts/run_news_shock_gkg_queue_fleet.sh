#!/usr/bin/env bash
set -Eeuo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
cd "$ROOT_DIR"

LOG_DIR="${LOG_DIR:-logs/news_shock_gkg_queues}"
mkdir -p "$LOG_DIR"

RESTART_SECONDS="${RESTART_SECONDS:-60}"
POLL_SECONDS="${POLL_SECONDS:-300}"
RETRY_SECONDS="${RETRY_SECONDS:-600}"
MAX_ENRICH_URLS="${MAX_ENRICH_URLS:-25}"

pids=()

start_supervised() {
  local name="$1"
  shift

  (
    while true; do
      printf '\n%s supervisor_start %s\n' "$(date -Is)" "$name"
      set +e
      "$@"
      code=$?
      set -e
      printf '%s supervisor_restart %s exit=%s sleep=%s\n' "$(date -Is)" "$name" "$code" "$RESTART_SECONDS"
      sleep "$RESTART_SECONDS"
    done
  ) >> "$LOG_DIR/${name}.log" 2>&1 &

  pids+=("$!")
  printf '%s fleet_started %s pid=%s log=%s\n' "$(date -Is)" "$name" "${pids[-1]}" "$LOG_DIR/${name}.log"
}

shutdown() {
  local code=$?
  trap - INT TERM EXIT
  for pid in "${pids[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
  exit "$code"
}

trap shutdown INT TERM EXIT

start_supervised worker_0_optiplex \
  env POLL_SECONDS="$POLL_SECONDS" RETRY_SECONDS="$RETRY_SECONDS" LOCAL_FETCH_WORKERS=1 \
  scripts/run_news_shock_gkg_worker_partition_queue.sh 0 4 local

# DESKTOP-VEFGGDH is often offline on Tailscale; DESKTOP-DHFGGVE is the hot spare.
start_supervised worker_1_DESKTOP-DHFGGVE \
  env POLL_SECONDS="$POLL_SECONDS" RETRY_SECONDS="$RETRY_SECONDS" RETURN_MODE=direct WINDOWS_FETCH_WORKERS=2 \
  scripts/run_news_shock_gkg_worker_partition_queue.sh 1 4 windows DESKTOP-DHFGGVE

start_supervised worker_2_DESKTOP-FGEDHGV \
  env POLL_SECONDS="$POLL_SECONDS" RETRY_SECONDS="$RETRY_SECONDS" RETURN_MODE=direct WINDOWS_FETCH_WORKERS=2 \
  scripts/run_news_shock_gkg_worker_partition_queue.sh 2 4 windows DESKTOP-FGEDHGV

start_supervised worker_3_DESKTOP-EDHFGGV \
  env POLL_SECONDS="$POLL_SECONDS" RETRY_SECONDS="$RETRY_SECONDS" RETURN_MODE=direct WINDOWS_FETCH_WORKERS=2 \
  scripts/run_news_shock_gkg_worker_partition_queue.sh 3 4 windows DESKTOP-EDHFGGV

start_supervised uploader \
  env POLL_SECONDS="$POLL_SECONDS" MAX_ENRICH_URLS="$MAX_ENRICH_URLS" \
  scripts/run_news_shock_gkg_upload_queue.sh

wait
