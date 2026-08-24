#!/usr/bin/env bash
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
COINGECKO_DAILY_UNIVERSE="${COINGECKO_DAILY_UNIVERSE:-clean}"
if [[ "$COINGECKO_DAILY_UNIVERSE" == "full" ]]; then
  PRICE_PANEL="$ROOT/data_lake/crypto_pipeline/exports/price_panel_wide.csv"
else
  PRICE_PANEL="$ROOT/data_lake/crypto_pipeline/exports/price_panel_clean.csv"
fi
PULL_SYNC_SCRIPT="$ROOT/scripts/sync_coingecko_panels_from_backup.sh"
NODES_FILE="${COINGECKO_CLUSTER_NODES_FILE:-$ROOT/config/coingecko_cluster_nodes.conf}"
STATE_DIR="${COINGECKO_CLUSTER_STATE_DIR:-$ROOT/data_lake/crypto_pipeline/failover_state/cluster_coordinator}"
STATE_FILE="${STATE_DIR}/last_success.env"
PROBE_TIMEOUT_SEC="${COINGECKO_REMOTE_PROBE_TIMEOUT_SEC:-45}"
REMOTE_TIMEOUT_SEC="${COINGECKO_REMOTE_RUN_TIMEOUT_SEC:-900}"
SSH_COMMAND="${COINGECKO_COORDINATOR_SSH_COMMAND:-ssh -o BatchMode=yes -o ConnectTimeout=10}"
LOCK_FILE="${XDG_RUNTIME_DIR:-/tmp}/coingecko_network_coordinator.lock"
FORCE_DISPATCH="${COINGECKO_FORCE_DISPATCH:-0}"
DRY_RUN="${COINGECKO_CLUSTER_DRY_RUN:-0}"
TODAY="$(date +%F)"

panel_has_today() {
  [[ -f "$PRICE_PANEL" ]] && tail -n 1 "$PRICE_PANEL" | grep -q "^${TODAY},"
}

load_nodes() {
  if [[ ! -f "$NODES_FILE" ]]; then
    echo "[error] cluster node file not found: $NODES_FILE" >&2
    return 1
  fi

  NODE_NAMES=()
  NODE_HOSTS=()
  NODE_REPOS=()
  NODE_EXPORTS=()
  NODE_RUNNERS=()
  NODE_OSTYPES=()

  while IFS='|' read -r raw_name raw_host raw_repo raw_exports raw_runner raw_ostype; do
    line="$(printf '%s' "${raw_name}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    if [[ -z "${line}" || "${line}" == \#* ]]; then
      continue
    fi

    name="$(printf '%s' "${raw_name}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    host="$(printf '%s' "${raw_host}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    repo="$(printf '%s' "${raw_repo}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    exports="$(printf '%s' "${raw_exports}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    runner="$(printf '%s' "${raw_runner:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
    ostype="$(printf '%s' "${raw_ostype:-linux}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

    if [[ -z "${name}" || -z "${host}" || -z "${repo}" || -z "${exports}" ]]; then
      echo "[warn] skipping invalid cluster node line in $NODES_FILE: ${raw_name}|${raw_host}|${raw_repo}|${raw_exports}|${raw_runner:-}|${raw_ostype:-}" >&2
      continue
    fi
    if [[ -z "${runner}" ]]; then
      runner="./scripts/run_coingecko_daily_failover.sh"
    fi

    NODE_NAMES+=("${name}")
    NODE_HOSTS+=("${host}")
    NODE_REPOS+=("${repo}")
    NODE_EXPORTS+=("${exports}")
    NODE_RUNNERS+=("${runner}")
    NODE_OSTYPES+=("${ostype}")
  done <"$NODES_FILE"

  if [[ "${#NODE_NAMES[@]}" -eq 0 ]]; then
    echo "[error] no valid nodes configured in $NODES_FILE" >&2
    return 1
  fi
}

probe_node() {
  local host="$1"
  local repo="$2"
  local exports="$3"
  local runner="$4"
  local ostype="$5"

  if [[ "$ostype" == "windows" ]]; then
    timeout "$PROBE_TIMEOUT_SEC" $SSH_COMMAND "$host" \
      "powershell -NoProfile -Command \"if ((Test-Path -LiteralPath '$exports') -and (Test-Path -LiteralPath '$runner')) { exit 0 } else { exit 1 }\""
  else
    timeout "$PROBE_TIMEOUT_SEC" $SSH_COMMAND "$host" \
      "test -d '$repo' && test -d '$exports' && test -x '$repo/$runner'"
  fi
}

dispatch_node() {
  local host="$1"
  local repo="$2"
  local runner="$3"
  local ostype="$4"

  if [[ "$ostype" == "windows" ]]; then
    timeout "$REMOTE_TIMEOUT_SEC" $SSH_COMMAND "$host" \
      "cmd /c powershell -NoProfile -ExecutionPolicy Bypass -File \"$runner\" -RandomDelayMaxSec 0"
  else
    timeout "$REMOTE_TIMEOUT_SEC" $SSH_COMMAND "$host" \
      "cd '$repo' && COINGECKO_FAILOVER_RANDOM_DELAY_MAX_SEC=0 '$runner'"
  fi
}

pull_from_node() {
  local host="$1"
  local exports="$2"

  COINGECKO_BACKUP_SOURCE="${host}:${exports}" "$PULL_SYNC_SCRIPT"
}

next_start_index() {
  local count="$1"
  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
    if [[ "${last_index:-}" =~ ^[0-9]+$ ]]; then
      echo $(((last_index + 1) % count))
      return 0
    fi
  fi
  echo 0
}

record_success() {
  local idx="$1"
  local name="$2"
  local host="$3"
  mkdir -p "$STATE_DIR"
  cat >"$STATE_FILE" <<EOF
last_index=${idx}
last_node_name=${name}
last_node_host=${host}
last_success_date=${TODAY}
last_success_utc=$(date -u +%FT%TZ)
EOF
}

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "[skip] coordinator lock is already held"
  exit 0
fi

mkdir -p "$ROOT/logs"

if [[ "$FORCE_DISPATCH" != "1" ]] && panel_has_today; then
  echo "[ok] canonical panel already has ${TODAY}; no remote dispatch needed"
  exit 0
fi

load_nodes

count="${#NODE_NAMES[@]}"
start_idx="$(next_start_index "$count")"
echo "[coord] ${TODAY} missing locally; evaluating ${count} cluster node(s), start_index=${start_idx}"

for ((offset = 0; offset < count; offset++)); do
  idx=$(((start_idx + offset) % count))
  name="${NODE_NAMES[$idx]}"
  host="${NODE_HOSTS[$idx]}"
  repo="${NODE_REPOS[$idx]}"
  exports="${NODE_EXPORTS[$idx]}"
  runner="${NODE_RUNNERS[$idx]}"
  ostype="${NODE_OSTYPES[$idx]}"

  echo "[coord] node=${name} host=${host} os=${ostype} probe"
  if ! probe_node "$host" "$repo" "$exports" "$runner" "$ostype"; then
    echo "[warn] node=${name} probe failed" >&2
    continue
  fi

  if [[ "$DRY_RUN" == "1" ]]; then
    echo "[coord] dry-run enabled; stopping after probe success on node=${name}"
    exit 0
  fi

  echo "[coord] node=${name} dispatch"
  if dispatch_node "$host" "$repo" "$runner" "$ostype"; then
    echo "[coord] node=${name} remote run completed"
  else
    rc=$?
    echo "[warn] node=${name} remote run failed (rc=${rc}); trying pull-sync anyway" >&2
  fi

  if pull_from_node "$host" "$exports" && panel_has_today; then
    record_success "$idx" "$name" "$host"
    echo "[ok] canonical panel now contains ${TODAY} (source node=${name})"
    exit 0
  fi

  echo "[warn] node=${name} did not produce a confirmed canonical ${TODAY} row" >&2
done

if panel_has_today; then
  echo "[ok] canonical panel now contains ${TODAY}"
  exit 0
fi

echo "[error] ${TODAY} is still missing after full cluster coordinator cycle" >&2
exit 1
