#!/usr/bin/env bash
# Weekly quant-AI memo — Indonesia first; extend via --country in config.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY=python3; fi
exec "$PY" scripts/run_quant_ai_analyst.py \
  --country "${QUANT_AI_COUNTRY:-IDN}" \
  --brief \
  --llm "${QUANT_AI_LLM:-auto}" \
  --recent-weeks "${QUANT_AI_RECENT_WEEKS:-2}" \
  "$@"
