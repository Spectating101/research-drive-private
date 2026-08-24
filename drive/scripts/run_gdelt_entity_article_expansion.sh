#!/usr/bin/env bash
# Expand Tier-3 entity article coverage: GDrive pull -> entity overlay -> fused ticker panel.
set -euo pipefail
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
cd "$ROOT"

PULL_LIMIT="${PULL_LIMIT:-0}"
SCORE="${SCORE:-0}"
RUN_ID="${RUN_ID:-ticker_$(date -u +%Y%m%d)}"
LOG_DIR="${LOG_DIR:-logs/gdelt_entity_expansion}"
mkdir -p "$LOG_DIR"

score_args=()
if [[ "$SCORE" == "1" ]]; then
  score_args+=(--score)
fi

echo "=== phase 1: pull normalized article windows from GDrive ==="
pull_args=()
if [[ "${PULL_FORCE:-0}" == "1" ]]; then
  pull_args+=(--force)
fi
nice -n 10 ionice -c2 -n7 .venv/bin/python scripts/news_shock_taxonomy/expand_gdelt_entity_article_coverage.py \
  "${pull_args[@]}" \
  ${PULL_LIMIT:+--limit "$PULL_LIMIT"} \
  "${score_args[@]}" \
  2>&1 | tee -a "$LOG_DIR/pull_$(date -u +%Y%m%dT%H%M%SZ).log"

echo "=== phase 2: rebuild entity + fused ticker panels ==="
PHASE=entity RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh --force-entity-overlay
PHASE=fused RUN_ID="$RUN_ID" scripts/run_ticker_research_panels.sh

echo "=== done run_id=$RUN_ID ==="
RUN_ID="$RUN_ID" python3 - <<'PY'
import json
import os
from pathlib import Path
run_id = os.environ["RUN_ID"]
summary = Path("data_lake/research_panels/ticker_news_market") / run_id / "summary.json"
if summary.exists():
    print(json.dumps(json.loads(summary.read_text()), indent=2))
PY
