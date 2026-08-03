#!/usr/bin/env bash
# Weekly Indonesia position sheet + optional paper mark
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -f .env ]]; then set -a; source .env; set +a; fi
python3 scripts/run_idn_research_audit.py
PYTHONPATH="$PWD:$PWD/scripts" python3 scripts/run_idn_retail_replication_study.py
python3 scripts/run_idn_weekly_position_sheet.py "$@"
if [[ "${1:-}" != "--sheet-only" ]]; then
  python3 scripts/idn_paper_tracker.py --portfolio backtests/outputs/idn_weekly_position_sheet/latest_portfolio.json
fi
