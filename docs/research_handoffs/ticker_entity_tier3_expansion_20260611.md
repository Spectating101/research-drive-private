# Tier 3 Entity-Resolved Ticker Panel Expansion

**Date:** 2026-06-11  
**Goal:** Expand `ticker_week_entity_market_panel` from ~4 months / 6k rows to full GDELT article coverage (~100 monthly windows, 2018–2026).

## Problem

Phase 2 entity panel was thin because only **5** local article-level GDELT windows existed (3 scored + 2 corrupt normalized). Country **daily** panels cover 101 months, but entity resolution needs `asia_gkg_filtered.csv.gz` or `asia_gkg_scored.csv.gz` per month.

**GDrive has 100/101** matching normalized windows under:

- `.../gdelt_gkg_asia_backfill_2018_2023/normalized/gdelt_gkg_asia_bulk/`
- `.../normalized/gdelt_gkg_asia_bulk/`

## Solution pipeline

```text
expand_gdelt_entity_article_coverage.py   # pull missing months from GDrive
  → build_ticker_research_panels.py --phase entity --force-entity-overlay
  → build_ticker_research_panels.py --phase fused
  → update registry default_run_id
```

### Scripts

| Script | Role |
|---|---|
| `scripts/news_shock_taxonomy/expand_gdelt_entity_article_coverage.py` | Pull + optional score |
| `scripts/run_gdelt_entity_article_expansion.sh` | Pull + entity + fused (single shell) |
| `scripts/run_gdelt_entity_tier3_pipeline.sh` | Wait for pull PID, then entity + fused |
| `scripts/build_ticker_research_panels.py` | `--force-entity-overlay` rebuilds per-window overlay |

### One-shot (foreground)

```bash
# Pull all missing months (~1–2 hours)
.venv/bin/python scripts/news_shock_taxonomy/expand_gdelt_entity_article_coverage.py

# Rebuild entity + fused (~10 min/window entity scan; plan overnight for 100 windows)
RUN_ID=ticker_20260611 PHASE=entity scripts/run_ticker_research_panels.sh --force-entity-overlay
RUN_ID=ticker_20260611 PHASE=fused scripts/run_ticker_research_panels.sh
```

### Background (started 2026-06-11)

```bash
# Pull all windows
nohup .venv/bin/python scripts/news_shock_taxonomy/expand_gdelt_entity_article_coverage.py \
  > logs/gdelt_entity_expansion/pull_all.log 2>&1 &

# Chain entity+fused after pull
nohup env RUN_ID=ticker_20260611 WAIT_PULL_PID=<pull_pid> scripts/run_gdelt_entity_tier3_pipeline.sh \
  > logs/gdelt_entity_expansion/tier3_nohup.log 2>&1 &
```

### Monitor

```bash
tail -f logs/gdelt_entity_expansion/pull_all_*.log
tail -f logs/gdelt_entity_expansion/tier3_*.log
wc -l data_lake/news_shock_taxonomy/derived/gdelt_entity_article_prefetch/manifest.jsonl
python3 -c "
import sys; sys.path.insert(0,'scripts')
from ticker_research_panel_lib import canonical_article_source_dirs, REPO
print(len(canonical_article_source_dirs(
  REPO/'data_lake/news_shock_taxonomy/processed',
  REPO/'data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk',
)))
"
```

## Outputs (target run)

| Artifact | Path |
|---|---|
| Entity overlay per window | `data_lake/news_shock_taxonomy/derived/gdelt_entity_ticker_overlay/` |
| Daily entity shocks | `data_lake/research_panels/ticker_news_market/ticker_20260611/daily_ticker_entity_shock_panel.parquet` |
| Weekly entity news | `.../ticker_week_entity_news_panel.parquet` |
| **Fused Tier 3 panel** | `.../ticker_week_entity_market_panel.parquet` |

## Tier 3 v2 enhancements (2026-06-11)

| Feature | Location |
|---|---|
| Supplemental aliases + ADR bridge | `config/ticker_entity_aliases_v2.json` |
| Match tiers (`exact_ticker`, `alias_high`, `alias_fuzzy`) | `scripts/ticker_research_panel_lib.py` |
| URL dedupe + optional relevance floor | `build_ticker_research_panels.py` flags |
| Lower entity liquidity gate (60d vs 200d broadcast) | `--min-price-rows-entity` |
| Long zero-filled panel | `ticker_week_entity_long_panel.parquet` |
| Entity − broadcast residual panel | `ticker_week_entity_residual_panel.parquet` |
| Liquidity strata | `liquidity_bucket` on fused/long panels |
| QA report | `scripts/qa_ticker_entity_tier3.py` |

Registry datasets: `ticker_week_entity_long_panel`, `ticker_week_entity_residual_panel`.

Rebuild v2 entity mentions after article pull completes:

```bash
RUN_ID=ticker_20260611 PHASE=entity scripts/run_ticker_research_panels.sh --force-entity-overlay
RUN_ID=ticker_20260611 PHASE=fused scripts/run_ticker_research_panels.sh
RUN_ID=ticker_20260611 PHASE=tier3_extras scripts/run_ticker_research_panels.sh
.venv/bin/python scripts/qa_ticker_entity_tier3.py --run-dir data_lake/research_panels/ticker_news_market/ticker_20260611
```

## After validation

Update `config/research_query_registry.json`:

```json
"default_run_id": "ticker_20260611"
```

for entity-tier datasets (`ticker_week_entity_market_panel`, long, residual). Broadcast can stay on `ticker_20260610`.

## Performance notes

- GDrive pull: ~1–3 min / month
- Entity overlay scan: ~10 min / month (~1M GKG rows, entity alias match)
- Full 100-window entity rebuild: **plan ~15–20 hours** unattended
- Scoring (`--score` on expand script) is optional; entity phase reads normalized files directly

## Prior state (reference)

| Metric | `ticker_20260610` |
|---|---|
| Entity panel rows | 6,199 |
| Tickers | 565 |
| Week range | 2023-10 → 2025-05 |
| Article windows | 5 (3 complete, 2 corrupt) |
