#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/data_catalog/harvest_dataset_indexes_full.py \
  --out-dir "${FULL_INDEX_OUT:-data_lake/dataset_catalog/full_index}" \
  --sources "${FULL_INDEX_SOURCES:-datacite,openaire,openml,huggingface,aws_open_data_registry}" \
  --max-records-per-source "${FULL_INDEX_MAX_RECORDS_PER_SOURCE:-0}" \
  --page-size "${FULL_INDEX_PAGE_SIZE:-500}" \
  --sleep "${FULL_INDEX_SLEEP:-0.2}" \
  --datacite-created-years "${FULL_INDEX_DATACITE_CREATED_YEARS:-}"
