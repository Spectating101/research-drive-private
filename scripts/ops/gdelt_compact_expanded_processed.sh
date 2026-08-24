#!/usr/bin/env bash
# Remove expanded processed/ month dirs after overlays rebuilt + GDrive verified.
# Keeps normalized/gdelt_gkg_expanded_bulk (source to re-score if needed).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO}"

PROC="data_lake/news_shock_taxonomy/processed"
DRY_RUN="${DRY_RUN:-1}"
removed=0
freed=0

if [[ ! -d "${PROC}" ]]; then
  echo "missing ${PROC}"
  exit 1
fi

for dir in "${PROC}"/expanded_gkg_window_*; do
  [[ -d "${dir}" ]] || continue
  bytes="$(du -sb "${dir}" 2>/dev/null | awk '{print $1}')"
  if [[ "${DRY_RUN}" == "1" ]]; then
    echo "would_remove ${dir} bytes=${bytes}"
  else
    rm -rf "${dir}"
    echo "removed ${dir} bytes=${bytes}"
  fi
  removed=$((removed + 1))
  freed=$((freed + bytes))
done

python3 scripts/ops/gdelt_retention_status.py >/dev/null || true

if [[ "${DRY_RUN}" == "1" ]]; then
  echo "dry_run done would_remove_dirs=${removed} would_free_gb=$((freed / 1024 / 1024 / 1024))"
  echo "Apply: DRY_RUN=0 bash scripts/ops/gdelt_compact_expanded_processed.sh"
else
  echo "compact_done removed_dirs=${removed} freed_gb=$((freed / 1024 / 1024 / 1024))"
fi
