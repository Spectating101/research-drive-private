#!/usr/bin/env bash
# Pull one GDELT month + build entity overlay. Optional: delete normalized after success.
set -euo pipefail
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
cd "$ROOT"

if [[ $# -lt 1 ]]; then
  echo "usage: $0 WINDOW_KEY [RUN_ID]" >&2
  echo "  WINDOW_KEY like 20240101_20240201" >&2
  exit 2
fi

KEY="$1"
RUN_ID="${2:-ticker_$(date -u +%Y%m%d)}"
START="${KEY%%_*}"
END="${KEY#*_}"
DELETE_NORMALIZED="${DELETE_NORMALIZED:-1}"
LOG_DIR="${LOG_DIR:-logs/idn_entity_coverage/windows}"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${KEY}.log"
exec > >(tee -a "$LOG") 2>&1

echo "window_worker key=$KEY run_id=$RUN_ID started=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

echo "=== pull from GDrive if missing ==="
.venv/bin/python scripts/news_shock_taxonomy/expand_gdelt_entity_article_coverage.py \
  --start "$START" --end "$END" --limit 1

echo "=== entity overlay scan ==="
.venv/bin/python scripts/build_ticker_research_panels.py \
  --phase entity \
  --run-id "$RUN_ID" \
  --overlay-window "${START}_${END}" \
  --force-entity-overlay

if [[ "$DELETE_NORMALIZED" == "1" ]]; then
  norm_gz=(data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/asia_gkg_window_"${START}"_"${END}"_*/asia_gkg_filtered.csv.gz)
  for f in "${norm_gz[@]}"; do
    if [[ -f "$f" ]]; then
      echo "delete normalized $f (overlay on disk)"
      rm -f "$f"
    fi
  done
fi

echo "window_worker done key=$KEY"
