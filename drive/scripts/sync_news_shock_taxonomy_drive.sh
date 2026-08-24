#!/usr/bin/env bash
set -euo pipefail

# Copy-only archival sync for news-shock data. This intentionally uses
# `rclone copy`, not `rclone sync`, so missing local files never delete Drive
# files. Use this after pilots/backfills finish or during long runs if needed.

remote_root="${REMOTE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/news/gdelt-asia}"
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"

if ! command -v rclone >/dev/null 2>&1; then
  echo "rclone not found" >&2
  exit 1
fi

echo "remote_root=${remote_root}"
echo "started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "run_id=${RUN_ID:-}"

rclone copy config/news_shock_asia_universe.json "${remote_root}/config/" --stats-one-line
rclone copy docs/research_handoffs/asia_micro_macro_news_shock_dataset_20260520.md "${remote_root}/manifests/" --stats-one-line

copy_tree() {
  local src="$1"
  local dst="$2"
  rclone copy "${src}" "${dst}" \
    --stats-one-line \
    --transfers "${RCLONE_TRANSFERS:-8}" \
    --checkers "${RCLONE_CHECKERS:-16}" \
    --fast-list
}

if [[ -n "${RUN_ID:-}" ]]; then
  copy_tree "data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/${RUN_ID}" "${remote_root}/normalized/gdelt_gkg_asia_bulk/${RUN_ID}"
  copy_tree "data_lake/news_shock_taxonomy/processed/${RUN_ID}" "${remote_root}/processed/${RUN_ID}"
  if [[ "${INCLUDE_RAW:-1}" == "1" ]]; then
    copy_tree "data_lake/news_shock_taxonomy/raw/${RUN_ID}" "${remote_root}/raw/${RUN_ID}"
  else
    echo "skipping raw copy because INCLUDE_RAW=${INCLUDE_RAW}"
  fi
  echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  exit 0
fi

latest_child_dir() {
  local root="$1"
  find "${root}" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' 2>/dev/null \
    | sort -n \
    | tail -1 \
    | cut -d' ' -f2-
}

copy_latest_or_all() {
  local local_root="$1"
  local remote_subtree="$2"
  if [[ "${INCLUDE_RAW:-1}" == "0" && "${COPY_SCOPE:-latest}" == "latest" ]]; then
    local latest
    latest="$(latest_child_dir "${local_root}")"
    if [[ -n "${latest}" ]]; then
      local name
      name="$(basename "${latest}")"
      echo "copy_scope=latest local_root=${local_root} latest=${name}"
      copy_tree "${latest}" "${remote_root}/${remote_subtree}/${name}"
      return
    fi
  fi
  echo "copy_scope=all local_root=${local_root}"
  copy_tree "${local_root}" "${remote_root}/${remote_subtree}"
}

copy_latest_or_all data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk "normalized/gdelt_gkg_asia_bulk"
copy_latest_or_all data_lake/news_shock_taxonomy/processed "processed"

if [[ "${INCLUDE_RAW:-1}" == "1" ]]; then
  copy_tree data_lake/news_shock_taxonomy/raw "${remote_root}/raw"
else
  echo "skipping raw copy because INCLUDE_RAW=${INCLUDE_RAW}"
fi

echo "finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
