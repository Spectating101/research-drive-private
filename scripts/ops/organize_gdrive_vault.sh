#!/usr/bin/env bash
# Re-order GDrive vault: backend sibling, clean catalog/, stage procurement junk.
set -euo pipefail

SR_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${SR_DIR}"

VAULT="${GDRIVE_VAULT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data}"
COLL="${VAULT}/collection"
LOG_DIR="${SR_DIR}/data_lake/collection/_index/migration"
LOG="${LOG_DIR}/organize_$(date -u +%Y%m%dT%H%M%SZ).log"
mkdir -p "${LOG_DIR}"

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "${LOG}"; }

purge_if_exists() {
  local remote="$1"
  if rclone lsf "${remote}" --max-depth 1 &>/dev/null | grep -q . || rclone lsd "${remote}" &>/dev/null; then
    log "PURGE ${remote}"
    rclone purge "${remote}" 2>&1 | tee -a "${LOG}" || log "WARN purge failed ${remote}"
  else
    log "SKIP missing ${remote}"
  fi
}

move_if_exists() {
  local src="$1" dst="$2"
  if rclone lsf "${src}" --max-depth 1 &>/dev/null | grep -q . || rclone lsd "${src}" &>/dev/null; then
    log "MOVE ${src} -> ${dst}"
    rclone move "${src}" "${dst}" --checkers 8 --transfers 4 2>&1 | tee -a "${LOG}" || log "WARN move failed ${src}"
  else
    log "SKIP missing ${src}"
  fi
}

log "=== organize_gdrive_vault started ==="

DATACITE_SRC="${COLL}/catalog/datacite"
DATACITE_DST="${VAULT}/datacite_catalog"
DATACITE_RELOCATED=0

# --- Phase 1: DataCite bulk → vault-root backend (professor tree stays clean) ---
if rclone size "${DATACITE_SRC}" 2>/dev/null | grep -qE 'GiB|MiB|[1-9][0-9]* Byte'; then
  log "Phase 1: relocate DataCite harvest (${DATACITE_SRC} → ${DATACITE_DST})"
  if python3 scripts/ops/relocate_datacite_to_sibling.py --apply 2>&1 | tee -a "${LOG}"; then
    if rclone size "${DATACITE_DST}" 2>/dev/null | grep -qE 'GiB|MiB|[1-9][0-9]* Byte'; then
      DATACITE_RELOCATED=1
      log "Phase 1 OK: datacite now at ${DATACITE_DST}"
    else
      log "ERROR Phase 1: relocate reported ok but ${DATACITE_DST} looks empty - not purging source"
    fi
  else
    log "ERROR Phase 1: relocate failed - not purging source"
  fi
else
  log "Phase 1: skip relocate (no bulk at ${DATACITE_SRC})"
  if rclone size "${DATACITE_DST}" 2>/dev/null | grep -qE 'GiB|MiB|[1-9][0-9]* Byte'; then
    DATACITE_RELOCATED=1
    log "Phase 1: bulk already at ${DATACITE_DST}"
  fi
fi

# Only remove wrong-location shells after bulk is confirmed at vault-root sibling.
if [[ "${DATACITE_RELOCATED}" == "1" ]]; then
  purge_if_exists "${COLL}/datacite_catalog"
  purge_if_exists "${DATACITE_SRC}"
  purge_if_exists "${COLL}/backend"
else
  log "SKIP shell purge: datacite bulk not verified at ${DATACITE_DST}"
fi

# --- Phase 2: Stage operator procurement clutter out of acquired/procured ---
STAGE="${COLL}/ops/procurement-staging"
PROC="${COLL}/acquired/procured"
mkdir -p "${LOG_DIR}/.noop" 2>/dev/null || true

log "Phase 2: move procured_src_* and test folders to ops/procurement-staging/"
for name in $(rclone lsf "${PROC}" --dirs-only 2>/dev/null | sed 's:/$::'); do
  case "${name}" in
    procured_src_*|*_test|test_*)
      move_if_exists "${PROC}/${name}" "${STAGE}/${name}"
      ;;
  esac
done

# --- Phase 3: Zenodo DOI duplicates (canonical under doi:10.5281/) ---
log "Phase 3: remove zenodo folders duplicated under doi:10.5281/"
for dup in \
  datacite_10.5281_zenodo.5215789 \
  datacite_10.5281_zenodo.6554504 \
  datacite_10.5281_zenodo.7545157 \
  datacite_10.5281_zenodo.8346843; do
  purge_if_exists "${PROC}/${dup}"
done

# doi:10.17608/ supersedes flat datacite copy (same bytes)
purge_if_exists "${PROC}/datacite_10.17608_k6.auckland.24773262"
purge_if_exists "${PROC}/datacite_10.6084_m9.figshare.9933536"

# --- Phase 4: Refresh professor nav docs on vault ---
if [[ -f scripts/ops/publish_gdrive_partition_nav.py ]]; then
  log "Phase 4: publish START_HERE + PARTITION_MAP"
  python3 scripts/ops/publish_gdrive_partition_nav.py --upload 2>&1 | tee -a "${LOG}" || log "WARN nav publish failed"
fi

log "=== organize_gdrive_vault finished log=${LOG} ==="
