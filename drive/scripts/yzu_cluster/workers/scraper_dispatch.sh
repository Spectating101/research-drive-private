#!/usr/bin/env bash
# Run Molina spectator scrapers on any Linux cluster node (optiplex or SSH target).
# Spectator scripts + node_modules live in MOLINA_REPO; SQLite staging under SPECTATOR_STAGING.

set -euo pipefail

SCRIPT="${1:?script path required (e.g. spectator_scrape_cake.mjs or ops/foo.sh)}"
shift
if [[ "${1:-}" == "--" ]]; then
  shift
fi

SR_REPO_ROOT="${SR_REPO_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
MOLINA_REPO="${MOLINA_REPO:-$(cd "$SR_REPO_ROOT/.." && pwd)}"
SPECTATOR_STAGING="${SPECTATOR_STAGING:-$SR_REPO_ROOT/data_lake/spectator_engine}"
DISPATCH_LOG="${DISPATCH_LOG:-}"

mkdir -p "$SPECTATOR_STAGING/src/data" "$MOLINA_REPO/src"

# Cluster nodes write job-board SQLite under staging, not True-Oracle on spectator.
if [[ -z "${TRUE_ORACLE_DIR:-}" && "${SPECTATOR_USE_STAGING:-1}" == "1" ]]; then
  if [[ ! -e "$MOLINA_REPO/src/data" ]]; then
    ln -sfn "$SPECTATOR_STAGING/src/data" "$MOLINA_REPO/src/data"
  elif [[ -L "$MOLINA_REPO/src/data" ]]; then
    :
  else
    mkdir -p "$MOLINA_REPO/src/data"
  fi
else
  mkdir -p "$MOLINA_REPO/src/data"
fi

export NODE_PATH="${MOLINA_REPO}/node_modules${NODE_PATH:+:$NODE_PATH}"

log() {
  if [[ -n "$DISPATCH_LOG" ]]; then
    echo "$*" >>"$DISPATCH_LOG"
  fi
  echo "$*"
}

log "sr_repo=$SR_REPO_ROOT molina_repo=$MOLINA_REPO staging=$SPECTATOR_STAGING script=$SCRIPT args=$*"

# Sharpe-Renaissance generic scrapers (any-URL Playwright)
if [[ "$SCRIPT" == yzu_cluster/scrapers/* ]]; then
  cd "$SR_REPO_ROOT"
  etherscan=0
  for arg in "$@"; do
    if [[ "$arg" == *etherscan.io* ]]; then
      etherscan=1
      break
    fi
  done
  if [[ "$etherscan" == 1 ]]; then
    export PLAYWRIGHT_CHANNEL="${PLAYWRIGHT_CHANNEL:-chrome}"
    export PLAYWRIGHT_HEADLESS="${PLAYWRIGHT_HEADLESS:-false}"
  fi
  if [[ "$etherscan" == 1 && -z "${DISPLAY:-}" ]] && command -v xvfb-run >/dev/null 2>&1; then
    exec xvfb-run -a node "$SR_REPO_ROOT/scripts/$SCRIPT" "$@"
  fi
  exec node "$SR_REPO_ROOT/scripts/$SCRIPT" "$@"
fi

cd "$MOLINA_REPO"

if [[ "$SCRIPT" == *.mjs || "$SCRIPT" == *.js ]]; then
  exec node "scripts/$SCRIPT" "$@"
fi
if [[ "$SCRIPT" == ops/* || "$SCRIPT" == scripts/* ]]; then
  exec bash "$SCRIPT" "$@"
fi
if [[ "$SCRIPT" == *.sh ]]; then
  exec bash "scripts/$SCRIPT" "$@"
fi
exec bash "scripts/$SCRIPT" "$@"
