#!/usr/bin/env bash
set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
state_dir="${DATACITE_WATCHDOG_STATE_DIR:-${repo_root}/data_lake/dataset_catalog/watchdog}"
key="${DATACITE_CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
stall_minutes="${DATACITE_STALL_MINUTES:-20}"
alert_url="${DATACITE_ALERT_URL:-}"
auto_rebalance="${DATACITE_AUTO_REBALANCE:-1}"
mkdir -p "${state_dir}"

if [[ "${auto_rebalance}" == "1" ]]; then
  "${repo_root}/scripts/data_catalog/datacite_cluster_rebalancer.sh" || true
fi

workers=()
while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line}" || "${line}" =~ ^# ]] && continue
  workers+=("${line}")
done < "${repo_root}/scripts/data_catalog/datacite_cluster_watchdog.list"

alert() {
  local severity="$1" host="$2" shard="$3" message="$4"
  local timestamp line fingerprint previous=""
  timestamp="$(date -Iseconds)"
  line="${timestamp}|${severity}|${host}|${shard}|${message}"
  fingerprint="${severity}|${host}|${shard}|${message}"
  [[ -f "${state_dir}/last_alert_${host}_${shard}" ]] && previous="$(cat "${state_dir}/last_alert_${host}_${shard}")"
  printf '%s\n' "$line" >> "${state_dir}/alerts.log"
  printf '%s\n' "$fingerprint" > "${state_dir}/last_alert_${host}_${shard}"
  if [[ -n "$alert_url" && "$fingerprint" != "$previous" ]]; then
    curl -fsS --max-time 10 -H "Title: DataCite cluster ${severity}" \
      -d "$line" "$alert_url" >/dev/null 2>&1 || true
  fi
}

status_tmp="$(mktemp)"
trap 'rm -f "$status_tmp"' EXIT
: > "${state_dir}/current_status.tsv"

for worker in "${workers[@]}"; do
  IFS='|' read -r host shard <<< "$worker"
  if [[ "${host}" == "local" ]]; then
    local_dir="${repo_root}/data_lake/dataset_catalog/index_v3/${shard}"
    pid="0"
    if pgrep -f "harvest_dataset_indexes_full.py.*dataset_index_${shard}" >/dev/null 2>&1 || \
       pgrep -f "harvest_dataset_indexes_full.py.*${shard}" >/dev/null 2>&1; then
      pid="$(pgrep -f "harvest_dataset_indexes_full.py.*${shard}" | head -n 1 || echo 0)"
    fi
    latest_utc=""
    latest_bytes="0"
    heartbeat_utc=""
    checkpoint_utc=""
    complete_chunks="0"
    error_bytes="0"
    task_state="Running"
    if [[ -s "${local_dir}/datacite.complete.json" ]]; then
      task_state="Complete"
    elif [[ "${pid}" == "0" ]]; then
      task_state="Ready"
    fi
    if [[ -s "${local_dir}/datacite.heartbeat.json" ]]; then
      heartbeat_utc="$(python3 -c "import json;print(json.load(open('${local_dir}/datacite.heartbeat.json')).get('updated_at',''))" 2>/dev/null || true)"
    fi
    if [[ -s "${local_dir}/datacite.checkpoint.json" ]]; then
      checkpoint_utc="$(python3 -c "import json;print(json.load(open('${local_dir}/datacite.checkpoint.json')).get('updated_at',''))" 2>/dev/null || true)"
    fi
    shopt -s nullglob
    chunks=("${local_dir}"/datacite_*.jsonl.gz)
    shopt -u nullglob
    complete_chunks="${#chunks[@]}"
    if (( ${#chunks[@]} > 0 )); then
      latest_utc="$(date -r "${chunks[-1]}" -Iseconds 2>/dev/null || true)"
      latest_bytes="$(stat -c %s "${chunks[-1]}" 2>/dev/null || echo 0)"
    fi
    if [[ -s "${local_dir}/harvest.stderr.log" ]]; then
      error_bytes="$(stat -c %s "${local_dir}/harvest.stderr.log" 2>/dev/null || echo 0)"
    fi
    printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
      "$host" "$shard" "$task_state" "$pid" "$latest_utc" "$latest_bytes" "$complete_chunks" "$error_bytes" "$heartbeat_utc" "$checkpoint_utc" \
      >> "${state_dir}/current_status.tsv"
    if [[ "${task_state}" == "Ready" && ! -s "${local_dir}/datacite.complete.json" ]]; then
      systemctl --user start "datacite-local-${shard}.service" 2>/dev/null || \
        alert "WARN" "$host" "$shard" "local worker stopped; restart datacite-local-${shard}.service"
    fi
    continue
  fi
  if ! ssh -n -i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "user@${host}" \
    "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\user\\datacite_watchdog_status.ps1 -ShardName ${shard}" \
    >"$status_tmp" 2>/dev/null; then
    alert "ERROR" "$host" "$shard" "host unreachable"
    printf '%s\t%s\t%s\n' "$host" "$shard" "UNREACHABLE" >> "${state_dir}/current_status.tsv"
    continue
  fi

  status="$(tr -d '\r' < "$status_tmp" | tail -n 1)"
  IFS='|' read -r computer reported_shard task_state pid latest_utc latest_bytes complete_chunks error_bytes heartbeat_utc checkpoint_utc <<< "$status"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$host" "$reported_shard" "$task_state" "$pid" "$latest_utc" "$latest_bytes" "$complete_chunks" "$error_bytes" "$heartbeat_utc" "$checkpoint_utc" \
    >> "${state_dir}/current_status.tsv"

  if [[ "$pid" == "0" ]]; then
    complete_flag="$(
      ssh -n -i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
        "user@${host}" \
        "powershell.exe -NoProfile -Command \"if (Test-Path C:\\cw\\dataset_index_${shard}\\datacite.complete.json) { '1' } else { '0' }\"" \
        2>/dev/null | tr -d '\r' | tail -n 1
    )"
    if [[ "${complete_flag}" == "1" ]]; then
      continue
    fi
    alert "ERROR" "$host" "$shard" "worker stopped; requesting scheduled-task restart"
    ssh -n -i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
      "user@${host}" "schtasks.exe /Run /TN ResearchDataIndexDataCite_${shard}" >/dev/null 2>&1 || \
      alert "ERROR" "$host" "$shard" "automatic restart failed"
    continue
  fi

  if [[ "$error_bytes" =~ ^[0-9]+$ ]] && (( error_bytes > 0 )); then
    alert "WARN" "$host" "$shard" "stderr log is non-empty (${error_bytes} bytes)"
  fi

  activity_utc="${heartbeat_utc:-$latest_utc}"
  if [[ -n "$activity_utc" ]]; then
    latest_epoch="$(date -d "$activity_utc" +%s 2>/dev/null || printf 0)"
    now_epoch="$(date +%s)"
    if (( latest_epoch > 0 && now_epoch - latest_epoch > stall_minutes * 60 )); then
      alert "WARN" "$host" "$shard" "no output-file activity for more than ${stall_minutes} minutes"
    fi
  fi
done

date -Iseconds > "${state_dir}/last_check.txt"

# Rebuild topic FTS for any shard that gained local datacite_*.jsonl.gz pieces.
PYTHONPATH="${repo_root}" python3 "${repo_root}/scripts/data_catalog/build_datacite_topic_index.py" \
  --repo-root "${repo_root}" --all-shards --only-stale >/dev/null 2>&1 || true
