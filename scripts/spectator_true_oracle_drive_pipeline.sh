#!/usr/bin/env bash
set -euo pipefail

# Bridge backup pipeline for spectator -> Optiplex -> Google Drive.
#
# This intentionally runs from the Optiplex because spectator does not need
# rclone credentials. It snapshots SQLite databases on spectator, pulls one
# compressed archive per dataset locally, uploads exact files to Drive, verifies
# size, and optionally cleans remote staging. It never mutates live DBs.
#
# Usage:
#   scripts/spectator_true_oracle_drive_pipeline.sh backup          # 104 + upwork
#   DATASETS=104 scripts/spectator_true_oracle_drive_pipeline.sh backup
#   DATASETS=upwork scripts/spectator_true_oracle_drive_pipeline.sh backup
#   APPLY=1 scripts/spectator_true_oracle_drive_pipeline.sh dedupe-drive
#
# Environment:
#   SPECTATOR_HOST=spectator
#   REMOTE_ROOT=/home/spectator/Downloads/LLM-Job-System/True-Oracle
#   DRIVE_ROOT=gdrive:Machine_Archive/local_downloads/spectator
#   LOCAL_ROOT=data_lake/spectator_archives
#   MIN_FREE_GB=35
#   FORCE=0
#   CLEAN_REMOTE_STAGE=1
#   DATASETS="104 upwork"

mode="${1:-backup}"

spectator_host="${SPECTATOR_HOST:-spectator}"
remote_root="${REMOTE_ROOT:-/home/spectator/Downloads/LLM-Job-System/True-Oracle}"
drive_root="${DRIVE_ROOT:-gdrive:Machine_Archive/local_downloads/spectator}"
local_root="${LOCAL_ROOT:-data_lake/spectator_archives}"
min_free_gb="${MIN_FREE_GB:-35}"
force="${FORCE:-0}"
clean_remote_stage="${CLEAN_REMOTE_STAGE:-1}"
stamp="${STAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
datasets="${DATASETS:-104 upwork}"
remote_archive_root="/home/spectator/Downloads/spectator_archives"

log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"
}

remote_free_gb() {
  ssh "${spectator_host}" "df -BG / | awk 'NR==2 {gsub(\"G\", \"\", \$4); print int(\$4)}'"
}

pull_exact() {
  local remote_path="$1"
  local local_path="$2"
  mkdir -p "$(dirname "${local_path}")"
  ssh "${spectator_host}" "cat '${remote_path}'" > "${local_path}.part"
  mv "${local_path}.part" "${local_path}"
}

backup_dataset() {
  local dataset="$1"
  local created_name

  log "creating_remote_sqlite_snapshot dataset=${dataset}"
  created_name="$(
    ssh "${spectator_host}" bash -s -- "${remote_root}" "${remote_archive_root}" "${stamp}" "${dataset}" <<'REMOTE'
set -euo pipefail
remote_root="$1"
archive_root="$2"
stamp="$3"
dataset="$4"

case "${dataset}" in
  104)
    dbs="104.db"
    main_db="104.db"
    main_table="104_data"
    extra_files=""
    ;;
  upwork)
    dbs="upwork.db"
    main_db="upwork.db"
    main_table="upwork_data"
    extra_files="upwork_jobs_v2.zip upwork_shortlist.csv llm_categories.json skills_dictionary.json"
    ;;
  *)
    echo "unsupported_dataset=${dataset}" >&2
    exit 2
    ;;
esac

cd "${remote_root}/src/data"

if [[ ! -f "${main_db}" ]]; then
  echo "missing_db=${main_db}" >&2
  exit 1
fi

range_line="$(
  sqlite3 "${main_db}" <<SQL
.mode list
SELECT
  COALESCE(substr(MIN(timestamp), 1, 10), 'unknown'),
  COALESCE(substr(MAX(timestamp), 1, 10), 'unknown')
FROM "${main_table}";
SQL
)"
range_start="${range_line%%|*}"
range_end="${range_line##*|}"
range_start="${range_start//[^0-9A-Za-z._-]/-}"
range_end="${range_end//[^0-9A-Za-z._-]/-}"

name="spectator_true-oracle_${dataset}-sqlite_scraped-${range_start}_to_${range_end}_${stamp}"
stage="${archive_root}/${name}/stage"
archive="${archive_root}/${name}.tar.zst"
manifest="${archive_root}/${name}.manifest.txt"
sha="${archive}.sha256"

rm -rf "${archive_root:?}/${name}" "${archive}" "${sha}" "${manifest}"
mkdir -p "${stage}" "${archive_root}"

{
  echo "archive_name=${name}"
  echo "created_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "source_host=$(hostname)"
  echo "source=${remote_root}/src/data"
  echo "dataset=${dataset}"
  echo "main_db=${main_db}"
  echo "main_table=${main_table}"
  echo "scraped_start_date=${range_start}"
  echo "scraped_end_date=${range_end}"
  echo "strategy=separate_dataset_sqlite_backup_then_zstd_archive"
  echo "restore_hint=tar --use-compress-program=zstd -xf ${name}.tar.zst"
  echo "disk_before=$(df -h / | tail -1)"
} > "${manifest}"

for db in ${dbs}; do
  if [[ -f "${db}" ]]; then
    echo "sqlite_backup ${db}" | tee -a "${manifest}" >&2
    sqlite3 "${db}" ".backup '${stage}/${db}'"
    sqlite3 "${stage}/${db}" "PRAGMA quick_check(1);" | sed "s/^/quick_check ${db} /" >> "${manifest}"
  fi
done

if [[ "${dataset}" == "104" ]]; then
  sqlite3 "${stage}/${main_db}" <<SQL >> "${manifest}"
.mode list
SELECT 'table_stats|104_data|count|' || COUNT(*) || '|timestamp_min|' || COALESCE(MIN(timestamp), '') || '|timestamp_max|' || COALESCE(MAX(timestamp), '') || '|first_seen_min|' || COALESCE(MIN(first_seen), '') || '|last_seen_max|' || COALESCE(MAX(last_seen), '') || '|post_date_min|' || COALESCE(MIN(post_date), '') || '|post_date_max|' || COALESCE(MAX(post_date), '') FROM "104_data";
SELECT 'table_stats|104_data_raw|count|' || COUNT(*) || '|timestamp_min|' || COALESCE(MIN(timestamp), '') || '|timestamp_max|' || COALESCE(MAX(timestamp), '') || '|first_seen_min|' || COALESCE(MIN(first_seen), '') || '|last_seen_max|' || COALESCE(MAX(last_seen), '') || '|post_date_min|' || COALESCE(MIN(post_date), '') || '|post_date_max|' || COALESCE(MAX(post_date), '') FROM "104_data_raw";
SQL
else
  sqlite3 "${stage}/${main_db}" <<SQL >> "${manifest}"
.mode list
SELECT 'table_stats|upwork_data|count|' || COUNT(*) || '|timestamp_min|' || COALESCE(MIN(timestamp), '') || '|timestamp_max|' || COALESCE(MAX(timestamp), '') || '|post_date_min|' || COALESCE(MIN(post_date), '') || '|post_date_max|' || COALESCE(MAX(post_date), '') FROM upwork_data;
SELECT 'table_stats|upwork_backup|count|' || COUNT(*) || '|timestamp_min|' || COALESCE(MIN(timestamp), '') || '|timestamp_max|' || COALESCE(MAX(timestamp), '') || '|post_date_min|' || COALESCE(MIN(post_date), '') || '|post_date_max|' || COALESCE(MAX(post_date), '') FROM upwork_backup;
SELECT 'table_stats|upwork_query_hits|count|' || COUNT(*) || '|last_seen_min|' || COALESCE(MIN(last_seen), '') || '|last_seen_max|' || COALESCE(MAX(last_seen), '') FROM upwork_query_hits;
SQL
fi

for f in ${extra_files}; do
  if [[ -f "${f}" ]]; then
    echo "copy ${f}" | tee -a "${manifest}" >&2
    cp -a "${f}" "${stage}/${f}"
  fi
done

echo "archive_started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${manifest}"
tar --use-compress-program="zstd -T1 -3" -cf "${archive}" -C "${stage}" .
sha256sum "${archive}" | awk -v n="${name}.tar.zst" '{print $1 "  " n}' > "${sha}"
echo "archive_finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${manifest}"
du -h "${archive}" >> "${manifest}"
cat "${sha}" >> "${manifest}"
echo "disk_after=$(df -h / | tail -1)" >> "${manifest}"
printf '%s\n' "${name}"
REMOTE
  )"

  local remote_archive="${remote_archive_root}/${created_name}.tar.zst"
  local remote_manifest="${remote_archive_root}/${created_name}.manifest.txt"
  local remote_sha="${remote_archive}.sha256"
  local local_dir="${local_root}/${created_name}"
  local drive_dir="${drive_root}/${created_name}"

  log "pulling_archive_to_local dataset=${dataset} local_dir=${local_dir}"
  mkdir -p "${local_dir}"
  pull_exact "${remote_archive}" "${local_dir}/${created_name}.tar.zst"
  pull_exact "${remote_sha}" "${local_dir}/${created_name}.tar.zst.sha256"
  pull_exact "${remote_manifest}" "${local_dir}/${created_name}.manifest.txt"

  local expected actual
  expected="$(awk '{print $1}' "${local_dir}/${created_name}.tar.zst.sha256")"
  actual="$(sha256sum "${local_dir}/${created_name}.tar.zst" | awk '{print $1}')"
  if [[ "${expected}" != "${actual}" ]]; then
    log "checksum_mismatch dataset=${dataset} expected=${expected} actual=${actual}"
    return 1
  fi

  log "uploading_to_drive dataset=${dataset} drive_dir=${drive_dir}"
  rclone copyto "${local_dir}/${created_name}.tar.zst" "${drive_dir}/${created_name}.tar.zst" \
    --transfers 1 --checkers 1 --tpslimit 2 --drive-pacer-min-sleep 500ms --drive-pacer-burst 5 --stats 30s --stats-one-line
  rclone copyto "${local_dir}/${created_name}.tar.zst.sha256" "${drive_dir}/${created_name}.tar.zst.sha256" \
    --transfers 1 --checkers 1 --tpslimit 2 --drive-pacer-min-sleep 500ms --drive-pacer-burst 5
  rclone copyto "${local_dir}/${created_name}.manifest.txt" "${drive_dir}/${created_name}.manifest.txt" \
    --transfers 1 --checkers 1 --tpslimit 2 --drive-pacer-min-sleep 500ms --drive-pacer-burst 5

  log "verifying_drive_size dataset=${dataset}"
  rclone check "${local_dir}" "${drive_dir}" --one-way --size-only --checkers 1 \
    --combined "/tmp/${created_name}.drive_check.txt"

  if [[ "${clean_remote_stage}" == "1" ]]; then
    log "cleaning_remote_stage dataset=${dataset}"
    ssh "${spectator_host}" "rm -rf '${remote_archive_root:?}/${created_name}' '${remote_archive}' '${remote_sha}' '${remote_manifest}'"
  fi
  log "backup_complete dataset=${dataset} name=${created_name}"
}

backup_mode() {
  local free_gb
  free_gb="$(remote_free_gb)"
  log "spectator_free_gb=${free_gb} min_free_gb=${min_free_gb} force=${force}"
  if [[ "${force}" != "1" && "${free_gb}" -ge "${min_free_gb}" ]]; then
    log "skip_backup reason=above_threshold"
    return 0
  fi

  local dataset
  for dataset in ${datasets}; do
    backup_dataset "${dataset}"
  done
}

dedupe_drive_mode() {
  local target="${DRIVE_DEDUPE_TARGET:-${drive_root}/true_oracle_good_data_20260529}"
  if [[ "${APPLY:-0}" != "1" ]]; then
    log "dry_run_dedupe target=${target}"
    rclone dedupe "${target}" --dedupe-mode first --dry-run -vv
  else
    log "apply_dedupe target=${target}"
    rclone dedupe "${target}" --dedupe-mode first -vv
    rclone lsl "${target}" --max-depth 1
  fi
}

case "${mode}" in
  backup)
    backup_mode
    ;;
  dedupe-drive)
    dedupe_drive_mode
    ;;
  *)
    echo "usage: $0 {backup|dedupe-drive}" >&2
    exit 2
    ;;
esac
