#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
interval="${CURATOR_INTERVAL_SECONDS:-1800}"
while true; do
  python3 scripts/data_catalog/build_curated_dataset_index.py \
    --input data_lake/dataset_catalog/external_dataset_catalog_seed.jsonl \
    --input-dir data_lake/dataset_catalog/index_v2 \
    --input-dir data_lake/dataset_catalog/index_v3 \
    --out-dir data_lake/dataset_catalog/curated_live \
    --min-tier tier_3_research_candidate || true
  PYTHONPATH=. python3 scripts/data_catalog/build_curated_topic_fts.py --repo-root . || true
  PYTHONPATH=. python3 scripts/data_catalog/build_datacite_topic_index.py --repo-root . --all --only-stale || true
  sleep "$interval"
done
