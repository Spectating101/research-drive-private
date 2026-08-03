#!/usr/bin/env bash
# Mark Indonesia invest trial portfolio to market + print recent moves.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
[[ -x "$PY" ]] || PY=python3
exec "$PY" scripts/idn_paper_tracker.py --strategy "${IDN_STRATEGY:-top5}" "$@"
