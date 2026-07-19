#!/usr/bin/env bash
# Hydrate datacite_*.jsonl.gz from GDrive → bulk index_v3, build shard FTS on bulk USB.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

bulk_root="${RESEARCH_BULK_ROOT:-/media/phyrexian/Transcend/sharpe-renaissance}"
if [[ ! -d "${bulk_root}/data_lake" ]]; then
  echo "bulk storage missing at ${bulk_root}" >&2
  exit 1
fi

export RESEARCH_BULK_ROOT="${bulk_root}"
export DATACITE_TOPIC_INDEX_ON_BULK=1
export DATACITE_COMPACT_FTS_PAYLOAD=1
export DATACITE_LOCAL_ROOT="${bulk_root}/data_lake/dataset_catalog/index_v3"
export DATACITE_TOPIC_INDEX_ROOT="${bulk_root}/data_lake/dataset_catalog/_topic_index"

drive_root="${DATACITE_DRIVE_ROOT:-gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/datacite_catalog/harvest/index_v3}"
local_root="${DATACITE_LOCAL_ROOT}"
log_dir="${DATACITE_TOPIC_INDEX_ROOT}"
log_file="${log_dir}/hydrate_index.log"
state_file="${log_dir}/hydrate_index.state.json"
mkdir -p "${log_dir}" "${local_root}"

# All GDrive lanes with jsonl, smallest first; y2025_q4 skipped when empty on Drive.
default_shards=(y2025_q2 y2025_q1 y2025 y2025_q3 y2026 y2023_2024 y2011_2020_2022)
if [[ -n "${DATACITE_INDEX_SHARDS:-}" ]]; then
  IFS=',' read -ra shards <<< "${DATACITE_INDEX_SHARDS}"
else
  shards=("${default_shards[@]}")
fi

delete_jsonl_after_index="${DATACITE_DELETE_JSONL_AFTER_INDEX:-1}"
skipped_log="${log_dir}/hydrate_skipped.jsonl"
ack_abuse="${DATACITE_DRIVE_ACKNOWLEDGE_ABUSE:-1}"

rclone_common=(
  --include 'datacite_*.jsonl.gz'
  --transfers 4
  --checkers 8
  --retries 3
  --low-level-retries 10
  --stats-one-line
  --stats 1m
)
if [[ "${ack_abuse}" == "1" ]]; then
  rclone_common+=(--drive-acknowledge-abuse)
fi

rclone_file=(
  --retries 3
  --low-level-retries 10
)
if [[ "${ack_abuse}" == "1" ]]; then
  rclone_file+=(--drive-acknowledge-abuse)
fi

log() {
  printf '%s %s\n' "$(date -Iseconds)" "$*" | tee -a "${log_file}"
}

write_state() {
  local phase="$1" shard="$2" detail="$3"
  python3 - <<PY
import json, time
from pathlib import Path
path = Path("${state_file}")
doc = json.loads(path.read_text()) if path.is_file() else {}
doc.update({
    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "phase": "${phase}",
    "shard": "${shard}",
    "detail": """${detail}""",
    "bulk_root": "${bulk_root}",
})
path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
PY
}

log_skipped_piece() {
  local shard="$1" piece="$2" reason="$3"
  printf '%s\n' "$(date -Iseconds) shard=${shard} file=${piece} reason=${reason}" >>"${skipped_log}"
  log "hydrate_skip shard=${shard} file=${piece} reason=${reason}"
}

hydrate_shard() {
  local shard="$1" remote="$2" local_dir="$3"
  local missing piece

  if ! rclone copy "${remote}" "${local_dir}" "${rclone_common[@]}" >>"${log_file}" 2>&1; then
    log "WARN hydrate_bulk_partial shard=${shard} — backfilling missing pieces"
  fi

  mapfile -t missing < <(
    comm -23 \
      <(rclone lsf "${remote}" --include 'datacite_*.jsonl.gz' --files-only 2>/dev/null | grep -E '^datacite_[0-9]+\.jsonl\.gz$' | LC_ALL=C sort -u) \
      <(find "${local_dir}" -maxdepth 1 -name 'datacite_*.jsonl.gz' -type f -printf '%f\n' 2>/dev/null | LC_ALL=C sort -u)
  )
  if [[ "${#missing[@]}" -eq 0 ]]; then
    return 0
  fi
  log "hydrate_backfill shard=${shard} missing_pieces=${#missing[@]}"
  for piece in "${missing[@]}"; do
    [[ -f "${local_dir}/${piece}" ]] && continue
    if rclone copyto "${remote}/${piece}" "${local_dir}/${piece}" "${rclone_file[@]}" >>"${log_file}" 2>&1; then
      log "hydrate_file_ok shard=${shard} file=${piece}"
      continue
    fi
    log_skipped_piece "${shard}" "${piece}" "rclone_copyto_failed"
  done
}

log "topic_indexing start bulk=${bulk_root} shards=${shards[*]} ack_abuse=${ack_abuse}"
write_state "start" "" "hydrate+index on bulk"

for shard in "${shards[@]}"; do
  remote="${drive_root}/${shard}"
  local_dir="${local_root}/${shard}"
  mkdir -p "${local_dir}"

  remote_count="$(rclone lsf "${remote}" --include 'datacite_*.jsonl.gz' 2>/dev/null | wc -l | tr -d ' ')"
  local_count="$(find "${local_dir}" -maxdepth 1 -name 'datacite_*.jsonl.gz' -type f 2>/dev/null | wc -l | tr -d ' ')"

  if [[ "${remote_count}" == "0" ]]; then
    log "skip shard=${shard} reason=no_remote_jsonl"
    continue
  fi

  log "hydrate shard=${shard} remote_pieces=${remote_count} local_pieces=${local_count}"
  write_state "hydrate" "${shard}" "remote_pieces=${remote_count} local_pieces=${local_count}"

  hydrate_shard "${shard}" "${remote}" "${local_dir}"

  local_count="$(find "${local_dir}" -maxdepth 1 -name 'datacite_*.jsonl.gz' -type f 2>/dev/null | wc -l | tr -d ' ')"
  missing_count=$((remote_count - local_count))
  if [[ "${missing_count}" -gt 0 ]]; then
    log "WARN hydrate_gap shard=${shard} missing_pieces=${missing_count} (indexing available local pieces)"
  fi
  log "index shard=${shard} local_pieces=${local_count}"
  write_state "index" "${shard}" "local_pieces=${local_count}"

  if PYTHONPATH="${repo_root}" python3 "${repo_root}/scripts/data_catalog/build_datacite_topic_index.py" \
    --repo-root "${repo_root}" --shard "${shard}" --force >>"${log_file}" 2>&1; then
    log "index_ok shard=${shard}"
    if [[ "${delete_jsonl_after_index}" == "1" ]]; then
      find "${local_dir}" -maxdepth 1 -name 'datacite_*.jsonl.gz' -type f -delete
      log "pruned_jsonl shard=${shard} (index on bulk; canonical on GDrive)"
    fi
  else
    log "WARN index_failed shard=${shard}"
  fi
done

log "rebuild manifest + curated + full_index"
write_state "finalize" "" "curated+full_index on repo nvme"
PYTHONPATH="${repo_root}" DATACITE_TOPIC_INDEX_ON_BULK=0 python3 "${repo_root}/scripts/data_catalog/build_datacite_topic_index.py" \
  --repo-root "${repo_root}" --all-shards --force >>"${log_file}" 2>&1 || true
PYTHONPATH="${repo_root}" DATACITE_TOPIC_INDEX_ON_BULK=0 python3 "${repo_root}/scripts/data_catalog/build_curated_topic_fts.py" \
  --repo-root "${repo_root}" >>"${log_file}" 2>&1 || true
PYTHONPATH="${repo_root}" DATACITE_TOPIC_INDEX_ON_BULK=0 python3 "${repo_root}/scripts/data_catalog/build_datacite_topic_index.py" \
  --repo-root "${repo_root}" >>"${log_file}" 2>&1 || true

log "topic_indexing done"
write_state "done" "" "complete"
