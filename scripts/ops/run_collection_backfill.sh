#!/usr/bin/env bash
# Backfill stub/drift partitions to GDrive (excludes GDELT + DataCite harvest bulk).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/../lib/platform_env.sh"

LOG="${SR_DIR}/logs/collection_backfill.log"
mkdir -p "${SR_DIR}/logs"

PARTITIONS=(
  markets.crypto-coingecko
  markets.nft-opensea
  markets.crypto-landscape
  markets.ethereum-usdt
  markets.equities-asia
  catalog.curated-index
  derived.research-panels
  acquired.procured
  ops.spectator-archives
  reference.refinitiv-backfill
  reference.sec-edgar
  reference.entity-mapping-asia
  social.reddit
  official.exchange-disclosures
  official.macro-asia
)

echo "[backfill] $(date -Is) start" | tee -a "${LOG}"

for pid in "${PARTITIONS[@]}"; do
  echo "[backfill] partition=${pid}" | tee -a "${LOG}"
  if ! "${SR_PYTHON}" "${SR_DIR}/scripts/ops/sync_collection_partitions_to_gdrive.py" \
    --partition "${pid}" \
    --skip-pull \
    --skip-inventory \
    --update-partition-status \
    --pretty 2>&1 | tee -a "${LOG}"; then
    echo "[backfill] WARN failed ${pid}" | tee -a "${LOG}"
  fi
done

echo "[backfill] refresh inventory + model guide" | tee -a "${LOG}"
"${SR_PYTHON}" "${SR_DIR}/scripts/data_catalog/inventory_canonical_collection.py" --quick 2>&1 | tee -a "${LOG}"
"${SR_PYTHON}" "${SR_DIR}/scripts/ops/build_model_collection_guide.py" --upload 2>&1 | tee -a "${LOG}"

echo "[backfill] $(date -Is) done" | tee -a "${LOG}"
