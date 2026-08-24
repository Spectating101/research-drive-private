#!/usr/bin/env bash
# Move heavy data_lake subtrees to mobile bulk disk and symlink back into the repo.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BULK_ROOT="${RESEARCH_BULK_ROOT:-/media/phyrexian/Transcend/sharpe-renaissance}"
LAKE_LOCAL="${REPO_ROOT}/data_lake"
LAKE_BULK="${BULK_ROOT}/data_lake"

# Largest pipeline / archive folders first (~30GB+ total).
MOVE_DIRS=(
  crypto_pipeline
  news_shock_taxonomy
  coingecko_archive
  dataset_catalog
  markets
  opensea
  spectator_archives
  refinitiv_backfill
)

echo "Repo:      ${REPO_ROOT}"
echo "Bulk root: ${BULK_ROOT}"

if [[ ! -d "$(dirname "${BULK_ROOT}")" ]]; then
  echo "Bulk parent not mounted. Plug in the drive or set RESEARCH_BULK_ROOT." >&2
  exit 1
fi

mkdir -p "${BULK_ROOT}" "${LAKE_BULK}"
touch "${BULK_ROOT}/.sharpe_research_bulk"

for name in "${MOVE_DIRS[@]}"; do
  src="${LAKE_LOCAL}/${name}"
  dst="${LAKE_BULK}/${name}"
  if [[ ! -e "${src}" ]]; then
    echo "skip (missing): ${name}"
    continue
  fi
  if [[ -L "${src}" ]]; then
    echo "skip (already linked): ${name} -> $(readlink "${src}")"
    continue
  fi
  if [[ -d "${dst}" ]]; then
    echo "bulk exists: ${name} — merging leftovers if any"
    if [[ -d "${src}" && ! -L "${src}" ]]; then
      rsync -a --copy-links "${src}/" "${dst}/"
      rm -rf "${src}"
    fi
  else
    echo "moving ${name} ..."
    # rsync handles Chrome Singleton* symlinks on exFAT bulk (mv fails there).
    rsync -a --copy-links "${src}/" "${dst}/"
    rm -rf "${src}"
  fi
  if [[ ! -e "${src}" ]]; then
    ln -s "${dst}" "${src}"
    echo "linked ${name}"
  fi
done

ENV_FILE="${REPO_ROOT}/.env.local"
LINE="RESEARCH_BULK_ROOT=${BULK_ROOT}"
if [[ -f "${ENV_FILE}" ]] && grep -q '^RESEARCH_BULK_ROOT=' "${ENV_FILE}"; then
  sed -i "s|^RESEARCH_BULK_ROOT=.*|${LINE}|" "${ENV_FILE}"
else
  printf '\n# Mobile bulk storage (Transcend USB)\n%s\n' "${LINE}" >> "${ENV_FILE}"
fi

echo ""
echo "Done. Bulk data_lake: ${LAKE_BULK}"
echo "Set in ${ENV_FILE}: ${LINE}"
df -h "${BULK_ROOT}" | tail -1
df -h / | tail -1
