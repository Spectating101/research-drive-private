#!/usr/bin/env bash
# Purge stale legacy vault roots, merge split partitions, dedupe procured copies.
# Safe: only removes paths verified redundant in 2026-07-07 audit.
set -euo pipefail

SR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${SR_DIR}"

VAULT="${GDRIVE_VAULT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data}"
LOG_DIR="${SR_DIR}/data_lake/collection/_index/migration"
LOG="${LOG_DIR}/cleanup_$(date -u +%Y%m%dT%H%M%SZ).log"
mkdir -p "${LOG_DIR}"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${LOG}"; }

purge_if_exists() {
  local remote="$1"
  if rclone lsd "${remote}" &>/dev/null || rclone lsf "${remote}" &>/dev/null; then
    log "PURGE ${remote}"
    rclone purge "${remote}" 2>&1 | tee -a "${LOG}"
  else
    log "SKIP missing ${remote}"
  fi
}

move_if_exists() {
  local src="$1" dst="$2"
  if rclone lsd "${src}" &>/dev/null || rclone lsf "${src}" --max-depth 1 &>/dev/null | grep -q .; then
    log "MOVE ${src} -> ${dst}"
    # Files must use copyto/moveto — plain move creates INDEX.json/ folder wrappers on Drive.
    if rclone lsf "${src}" --files-only --max-depth 1 &>/dev/null | grep -q . && ! rclone lsd "${src}" &>/dev/null; then
      rclone moveto "${src}" "${dst}" --stats-one-line 2>&1 | tee -a "${LOG}"
    else
      rclone move "${src}" "${dst}" --checkers 8 --transfers 4 2>&1 | tee -a "${LOG}"
    fi
  else
    log "SKIP move (missing) ${src}"
  fi
}

log "=== cleanup_gdrive_vault started vault=${VAULT} ==="

# --- Phase 1: Refinitiv — real data at legacy root; chrome junk in collection ---
REF_LEGACY="${VAULT}/refinitiv_backfill"
REF_COLL="${VAULT}/collection/reference/refinitiv-backfill"

purge_if_exists "${REF_COLL}/chrome_profile"
purge_if_exists "${REF_COLL}/local_chrome_profile"

for item in \
  2026-07-06-complete \
  2026-07-06-fundamentals \
  2026-07-06-scale \
  2026-07-06-value-v2 \
  rescued_desktop_20251215 \
  INDEX.json; do
  move_if_exists "${REF_LEGACY}/${item}" "${REF_COLL}/${item}"
done
purge_if_exists "${REF_LEGACY}"

# --- Phase 2: Legacy vault roots (stale subsets; canonical under collection/) ---
for leg in \
  crypto_landscape \
  dataset_catalog \
  entity_mapping \
  official_disclosures \
  research_models \
  research_panels \
  sec \
  social_reddit; do
  purge_if_exists "${VAULT}/${leg}"
done

# --- Phase 3: Crypto pipeline smoke / staging junk ---
CRYPTO="${VAULT}/collection/markets/crypto-landscape"
for junk in \
  smoke-coingecko-pipeline \
  smoke-crypto-pipeline-public-v3 \
  wrapper-smoke-crypto \
  staging \
  validation \
  failover_state; do
  purge_if_exists "${CRYPTO}/${junk}"
done

# --- Phase 4: SEC EDGAR duplicate procured copies ---
SEC="${VAULT}/collection/reference/sec-edgar"
purge_if_exists "${SEC}/procured_src_ace4a0fb8e9e"
purge_if_exists "${SEC}/company_tickers.json"

# --- Phase 5: Procured DOI naming duplicates (keep full datacite_* DOI paths) ---
PROC="${VAULT}/collection/acquired/procured"
for dup in \
  datacite_58938 \
  datacite_58938_test \
  datacite_5215789 \
  datacite_6554504 \
  datacite_7545157 \
  datacite_8346843 \
  datacite_3561826 \
  bts_db1bmarket_2010_q1 \
  bts_db1bmarket_2015_q1 \
  bts_db1bmarket_2020_q1 \
  bts_db1bmarket_2024_q1 \
  10.17608_k6.auckland.24773262 \
  10.6084_m9.figshare.9933536; do
  purge_if_exists "${PROC}/${dup}"
done

log "=== cleanup_gdrive_vault finished log=${LOG} ==="
