#!/usr/bin/env bash
# Background work unlocked by NVMe headroom + Transcend bulk storage.
# Safe to run while using the Research Drive UI (low priority, serialized heavy lock).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "${REPO_ROOT}"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOG_DIR="logs/gdelt_bulk_unlock_${STAMP}"
mkdir -p "${LOG_DIR}"

if [[ -f .env.local ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env.local
  set +a
fi

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "${LOG_DIR}/master.log"
}

log "bulk_unlock_started repo=${REPO_ROOT} bulk=${RESEARCH_BULK_ROOT:-auto}"
df -BG / "${RESEARCH_BULK_ROOT:-/media/phyrexian/Transcend}" 2>/dev/null | tee -a "${LOG_DIR}/master.log" || true

# Bulk disk holds data_lake I/O (symlinks). This machine only needs modest RAM for
# fetch/enrich; heavy scoring can run on Windows workers (their RAM + disk).
export FETCH_MIN_AVAILABLE_GB="${FETCH_MIN_AVAILABLE_GB:-8}"
export SCORE_MIN_AVAILABLE_GB="${SCORE_MIN_AVAILABLE_GB:-8}"
export ENRICH_MIN_AVAILABLE_GB="${ENRICH_MIN_AVAILABLE_GB:-6}"
export MIN_SAFE_FETCH_AVAILABLE_GB="${MIN_SAFE_FETCH_AVAILABLE_GB:-6}"
export MIN_SAFE_SCORE_AVAILABLE_GB="${MIN_SAFE_SCORE_AVAILABLE_GB:-6}"
export SCORE_CHUNK_SIZE="${SCORE_CHUNK_SIZE:-25000}"
export SCORE_OFFLOAD_NODES="${SCORE_OFFLOAD_NODES:-DESKTOP-FGEDHGV,DESKTOP-DHFGGVE,DESKTOP-EDHFGGV}"
export RESOURCE_WAIT_SECONDS="${RESOURCE_WAIT_SECONDS:-60}"
log "disk_backed_profile fetch_min_gb=${FETCH_MIN_AVAILABLE_GB} score_min_gb=${SCORE_MIN_AVAILABLE_GB} score_offload=${SCORE_OFFLOAD_NODES}"

# 2018-2023 lanes are complete; forward-fill the current month on bulk (keep staging gz).
RUN_TAG="${RUN_TAG:-${STAMP}}"
log "gdelt_forward_start tag=${RUN_TAG} window=2026-06-01..2026-07-01"
BACKFILL_START=2026-06-01 \
BACKFILL_END=2026-07-01 \
MONTH_MODULO=1 \
MONTH_REMAINDER=0 \
RUN_TAG="${RUN_TAG}" \
DISK_MIN_FREE_GB=50 \
LOCAL_RETENTION=compact \
FETCH_WORKERS=1 \
MAX_SAFE_FETCH_WORKERS=1 \
RESOURCE_WAIT_SECONDS=120 \
  scripts/run_news_shock_gkg_backfill_2018_2023_lane.sh \
  >> "${LOG_DIR}/gdelt_june_forward.log" 2>&1
log "gdelt_forward_done"

log "post_gdelt_queue_start"
python3 scripts/run_data_collection_queue.py \
  --queue config/post_gdelt_data_collection_queue_20260526.json \
  >> "${LOG_DIR}/post_gdelt_queue.log" 2>&1 || log "post_gdelt_queue_finished_with_errors"
log "post_gdelt_queue_done"

log "entity_article_pull_start"
.venv/bin/python scripts/news_shock_taxonomy/expand_gdelt_entity_article_coverage.py \
  >> "${LOG_DIR}/entity_article_pull.log" 2>&1 || log "entity_article_pull_finished_with_errors"
log "entity_article_pull_done"

RUN_ID="ticker_$(date -u +%Y%m%d)"
log "tier3_refresh_start run_id=${RUN_ID}"
RUN_ID="${RUN_ID}" scripts/run_gdelt_entity_tier3_pipeline.sh \
  >> "${LOG_DIR}/tier3_refresh.log" 2>&1 || log "tier3_refresh_finished_with_errors"
log "tier3_refresh_done run_id=${RUN_ID}"

log "bulk_unlock_finished"
df -BG / "${RESEARCH_BULK_ROOT:-/media/phyrexian/Transcend}" 2>/dev/null | tee -a "${LOG_DIR}/master.log" || true
