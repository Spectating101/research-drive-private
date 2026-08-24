#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${repo_root}"

run_id="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
out_root="${OUT_ROOT:-backtests/outputs/asia_news_market_modeling}"
auto_rebuild_panel="${AUTO_REBUILD_PANEL:-1}"
panel_run_id="${PANEL_RUN_ID:-asia_news_market_auto_latest}"
panel="${PANEL:-data_lake/research_panels/asia_news_market/post_gdelt_parallel_20260526_marresume_repaired/asia_country_week_news_market_primary_panel.parquet}"
remote_root="${REMOTE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/research_models/asia_news_market_modeling}"
panel_remote_root="${PANEL_REMOTE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/research_panels/asia_news_market}"

mkdir -p logs/asia_news_market_modeling "${out_root}"

if [[ "${auto_rebuild_panel}" == "1" ]]; then
  python3 scripts/build_asia_news_market_panel.py \
    --market-run latest \
    --run-id "${panel_run_id}"
  python3 scripts/analyze_asia_news_market_panel.py \
    --panel-dir "data_lake/research_panels/asia_news_market/${panel_run_id}" \
    --out-dir "data_lake/research_panels/asia_news_market/${panel_run_id}/diagnostics"
  rclone copy "data_lake/research_panels/asia_news_market/${panel_run_id}" \
    "${panel_remote_root}/${panel_run_id}" \
    --transfers 2 --checkers 4 --stats-one-line
  panel="data_lake/research_panels/asia_news_market/${panel_run_id}/asia_country_week_news_market_primary_panel.parquet"
fi

python3 scripts/run_asia_news_market_modeling_trial.py \
  --panel "${panel}" \
  --out-root "${out_root}" \
  --run-id "${run_id}"

rclone copy "${out_root}/${run_id}" "${remote_root}/${run_id}" --transfers 2 --checkers 4 --stats-one-line
rclone check "${out_root}/${run_id}" "${remote_root}/${run_id}" --one-way --size-only --combined -
