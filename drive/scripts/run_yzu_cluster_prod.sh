#!/usr/bin/env bash
# Production YZU Research Desk: build UI + API (with static serve) + worker
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/lib/platform_env.sh"
cd "${SR_DIR}"

API_PORT="${YZU_API_PORT:-8765}"
API_PID_FILE="${SR_DIR}/.locks/yzu_cluster_api.pid"
WORKER_PID_FILE="${SR_DIR}/.locks/yzu_cluster_worker.pid"
mkdir -p "${SR_DIR}/.locks" "${SR_DIR}/logs"

stop_if_running() {
  local pid_file="$1"
  if [[ -f "${pid_file}" ]]; then
    local pid
    pid="$(cat "${pid_file}")"
    if kill -0 "${pid}" 2>/dev/null; then
      echo "stopping pid=${pid} (${pid_file})"
      kill "${pid}" 2>/dev/null || true
      sleep 1
    fi
    rm -f "${pid_file}"
  fi
}

if [[ "${1:-}" == "stop" ]]; then
  stop_if_running "${API_PID_FILE}"
  stop_if_running "${WORKER_PID_FILE}"
  echo "yzu-cluster (prod) stopped"
  exit 0
fi

stop_if_running "${API_PID_FILE}"
stop_if_running "${WORKER_PID_FILE}"

if [[ ! -d node_modules ]]; then
  echo "installing npm deps…"
  npm install
fi

echo "building production UI…"
npm run build

echo "starting YZU API + desk UI on :${API_PORT}"
nohup "${SR_PYTHON}" -m scripts.research_query_engine.server \
  --host 127.0.0.1 \
  --port "${API_PORT}" \
  --serve-ui \
  > "${SR_DIR}/logs/yzu_cluster_api.log" 2>&1 &
echo $! > "${API_PID_FILE}"

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if ! curl -sf "http://127.0.0.1:${API_PORT}/health" >/dev/null 2>&1; then
  echo "API failed to start — see logs/yzu_cluster_api.log" >&2
  exit 1
fi

echo "starting YZU worker (job queue)"
nohup "${SR_PYTHON}" -m scripts.yzu_cluster.worker --poll 2 \
  > "${SR_DIR}/logs/yzu_cluster_worker.log" 2>&1 &
echo $! > "${WORKER_PID_FILE}"

echo ""
echo "YZU Research Desk (production) ready"
echo "  Desk: http://127.0.0.1:${API_PORT}/"
echo "  API:  http://127.0.0.1:${API_PORT}/health"
echo "  stop: scripts/run_yzu_cluster_prod.sh stop"
echo "  systemd: bash scripts/install_yzu_cluster_systemd_user.sh --prod"
