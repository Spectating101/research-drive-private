#!/usr/bin/env bash
# Assign idle DataCite workers to incomplete or stalled lanes.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
catalog_dir="${repo_root}/scripts/data_catalog"
state_dir="${DATACITE_WATCHDOG_STATE_DIR:-${repo_root}/data_lake/dataset_catalog/watchdog}"
lanes_file="${catalog_dir}/datacite_cluster_lanes.list"
hosts_file="${catalog_dir}/datacite_cluster_hosts.list"
workers_file="${catalog_dir}/datacite_cluster_workers.list"
watchdog_file="${catalog_dir}/datacite_cluster_watchdog.list"
local_root="${DATACITE_LOCAL_ROOT:-${repo_root}/data_lake/dataset_catalog/index_v3}"
key="${DATACITE_CLUSTER_KEY:-/home/phyrexian/.ssh/id_rsa}"
stall_minutes="${DATACITE_STALL_MINUTES:-20}"
cooldown_minutes="${DATACITE_REBALANCE_COOLDOWN_MINUTES:-10}"
dry_run="${DATACITE_REBALANCE_DRY_RUN:-0}"
steal_active="${DATACITE_REBALANCE_STEAL_ACTIVE:-1}"

mkdir -p "${state_dir}"
probe_tmp="$(mktemp)"
trap 'rm -f "$probe_tmp"' EXIT

# When a quarterly shard completes, assign y2025_q4 to the freed host if pending.
maybe_launch_y2025_q4() {
  local host="$1" shards_file="${catalog_dir}/datacite_y2025_parallel_shards.list"
  [[ -f "${shards_file}" ]] || return 0
  local line shard pending_host created query target
  for pending in y2025_q3 y2025_q4; do
    while IFS= read -r line || [[ -n "${line}" ]]; do
      [[ -z "${line}" || "${line}" =~ ^# ]] && continue
      IFS='|' read -r shard pending_host created query target <<< "${line}"
      if [[ "${shard}" == "${pending}" && -z "${pending_host}" ]]; then
        if [[ "${dry_run}" == "1" ]]; then
          log "dry_run launch_pending shard=${shard} host=${host}"
        else
          log "launch_pending shard=${shard} host=${host}"
          awk -F'|' -v shard="${shard}" -v host="${host}" '
            /^#/ || $0 == "" { print; next }
            $1 == shard { print shard "|" host "|" $3 "|" $4 "|" $5; next }
            { print }
          ' "${shards_file}" > "${shards_file}.tmp"
          mv "${shards_file}.tmp" "${shards_file}"
          if [[ "${shard}" == "y2025_q3" && "${host}" == "100.122.168.34" ]]; then
            remote_dir="C:/Users/user/dataset_index_${shard}"
          else
            remote_dir="C:/cw/dataset_index_${shard}"
          fi
          printf '%s|%s|%s\n' "${host}" "${shard}" "${remote_dir}" >> "${workers_file}"
          printf '%s|%s\n' "${host}" "${shard}" >> "${watchdog_file}"
          "${catalog_dir}/reassign_datacite_lane.sh" "${shard}" "${host}"
        fi
        return 0
      fi
    done < "${shards_file}"
  done
}

log() {
  printf '%s rebalancer %s\n' "$(date -Iseconds)" "$*"
}

host_reachable() {
  ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "user@$1" "hostname" >/dev/null 2>&1
}

assigned_host() {
  local lane="$1" line host _shard _remote
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^# ]] && continue
    IFS='|' read -r host _shard _remote <<< "${line}"
    if [[ "${_shard}" == "${lane}" ]]; then
      printf '%s' "${host}"
      return 0
    fi
  done < "${workers_file}"
  return 1
}

probe_lane() {
  local host="$1" lane="$2" line
  if ! host_reachable "${host}"; then
    printf '%s|unreachable|0|0|0|Missing||\n' "${lane}"
    return 0
  fi
  line="$(
    ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
      "user@${host}" \
      "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\\Users\\user\\datacite_lane_probe.ps1 -ShardName ${lane}" \
      2>/dev/null | tr -d '\r' | tail -n 1
  )"
  if [[ -z "${line}" ]]; then
    printf '%s|probe_failed|0|0|0|Missing||\n' "${lane}"
  else
    printf '%s\n' "${line}"
  fi
}

lane_target() {
  local lane="$1" line _years target
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" || "${line}" =~ ^# ]] && continue
    IFS='|' read -r _lane _years target <<< "${line}"
    if [[ "${_lane}" == "${lane}" ]]; then
      printf '%s' "${target}"
      return 0
    fi
  done < "${lanes_file}"
  printf '0'
}

activity_stale() {
  local activity_utc="$1"
  [[ -z "${activity_utc}" ]] && return 0
  local latest_epoch now_epoch
  latest_epoch="$(date -d "${activity_utc}" +%s 2>/dev/null || printf 0)"
  now_epoch="$(date +%s)"
  (( latest_epoch > 0 && now_epoch - latest_epoch > stall_minutes * 60 ))
}

sync_lane_meta_locally() {
  local lane="$1" host="$2" lane_dir="${local_root}/${lane}" remote_dir="C:/cw/dataset_index_${lane}"
  mkdir -p "${lane_dir}"
  if ! host_reachable "${host}"; then
    return 0
  fi
  for meta in datacite.checkpoint.json datacite.heartbeat.json datacite.complete.json; do
    scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
      "user@${host}:${remote_dir}/${meta}" "${lane_dir}/${meta}.partial" 2>/dev/null || continue
    if [[ -s "${lane_dir}/${meta}.partial" ]]; then
      mv -f "${lane_dir}/${meta}.partial" "${lane_dir}/${meta}"
    else
      rm -f "${lane_dir}/${meta}.partial"
    fi
  done
}

remove_watchdog_lane() {
  local lane="$1"
  [[ -f "${watchdog_file}" ]] || return 0
  local tmp
  tmp="$(mktemp)"
  awk -F'|' -v lane="${lane}" '
    /^#/ || $0 == "" { print; next }
    $2 == lane { next }
    { print }
  ' "${watchdog_file}" > "${tmp}"
  mv "${tmp}" "${watchdog_file}"
}

ensure_watchdog_lane() {
  local host="$1" lane="$2"
  [[ -f "${watchdog_file}" ]] || return 0
  if grep -q "|${lane}$" "${watchdog_file}" 2>/dev/null; then
    local tmp
    tmp="$(mktemp)"
    awk -F'|' -v lane="${lane}" -v host="${host}" '
      /^#/ || $0 == "" { print; next }
      $2 == lane { print host "|" lane; next }
      { print }
    ' "${watchdog_file}" > "${tmp}"
    mv "${tmp}" "${watchdog_file}"
  else
    printf '%s|%s\n' "${host}" "${lane}" >> "${watchdog_file}"
  fi
}

on_cooldown() {
  local host="$1" marker="${state_dir}/last_rebalance_${host}"
  [[ -f "${marker}" ]] || return 1
  local last now
  last="$(cat "${marker}")"
  now="$(date +%s)"
  (( now - last < cooldown_minutes * 60 ))
}

mark_rebalanced() {
  date +%s > "${state_dir}/last_rebalance_${1}"
}

# Ensure probe script exists on reachable hosts.
while IFS= read -r host || [[ -n "${host}" ]]; do
  [[ -z "${host}" || "${host}" =~ ^# ]] && continue
  host_reachable "${host}" || continue
  scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
    "${catalog_dir}/datacite_lane_probe.ps1" "user@${host}:C:/Users/user/datacite_lane_probe.ps1" 2>/dev/null || true
done < "${hosts_file}"

declare -A lane_status lane_complete lane_committed lane_pid lane_activity lane_host host_freed
declare -a all_lanes=()

while IFS= read -r line || [[ -n "${line}" ]]; do
  [[ -z "${line}" || "${line}" =~ ^# ]] && continue
  IFS='|' read -r lane _years _target <<< "${line}"
  all_lanes+=("${lane}")
  host="$(assigned_host "${lane}" || true)"
  if [[ -z "${host}" ]]; then
    lane_status["${lane}"]="unassigned"
    lane_complete["${lane}"]=0
    lane_committed["${lane}"]=0
    lane_pid["${lane}"]=0
    lane_activity["${lane}"]=""
    lane_host["${lane}"]=""
    continue
  fi
  lane_host["${lane}"]="${host}"
  IFS='|' read -r _lane status is_complete committed pid _task_state activity _heartbeat <<< "$(probe_lane "${host}" "${lane}")"
  lane_status["${lane}"]="${status}"
  lane_complete["${lane}"]="${is_complete}"
  lane_committed["${lane}"]="${committed:-0}"
  lane_pid["${lane}"]="${pid:-0}"
  lane_activity["${lane}"]="${activity}"
  sync_lane_meta_locally "${lane}" "${host}"
  if [[ "${is_complete}" == "1" ]]; then
    if [[ "${dry_run}" != "1" ]]; then
      remove_watchdog_lane "${lane}"
    fi
    host_freed["${host}"]=1
    log "lane=${lane} host=${host} status=complete committed=${committed}"
    if [[ "${dry_run}" != "1" ]]; then
      maybe_launch_y2025_q4 "${host}"
    fi
  fi
done < "${lanes_file}"

declare -a idle_hosts=()
while IFS= read -r host || [[ -n "${host}" ]]; do
  [[ -z "${host}" || "${host}" =~ ^# ]] && continue
  host_reachable "${host}" || continue
  local_busy=0
  for lane in "${all_lanes[@]}"; do
    [[ "${lane_host[$lane]:-}" == "${host}" ]] || continue
    [[ "${lane_complete[$lane]:-0}" == "1" ]] && continue
    if [[ "${lane_pid[$lane]:-0}" != "0" ]]; then
      local_busy=1
      break
    fi
    if [[ "${lane_status[$lane]:-}" == "running" ]]; then
      local_busy=1
      break
    fi
  done
  if (( local_busy == 0 )); then
    idle_hosts+=("${host}")
    log "host=${host} status=idle"
  fi
done < "${hosts_file}"

if (( ${#idle_hosts[@]} == 0 )); then
  log "action=none reason=no_idle_hosts"
  exit 0
fi

declare -a candidates=()
for lane in "${all_lanes[@]}"; do
  [[ "${lane_complete[$lane]:-0}" == "1" ]] && continue
  target="$(lane_target "${lane}")"
  committed="${lane_committed[$lane]:-0}"
  if (( target > 0 && committed >= target )); then
    continue
  fi
  host="${lane_host[$lane]:-}"
  status="${lane_status[$lane]:-missing}"
  pid="${lane_pid[$lane]:-0}"
  activity="${lane_activity[$lane]:-}"
  needs_help=0
  if [[ -z "${host}" || "${status}" == "unassigned" || "${status}" == "unreachable" || "${status}" == "probe_failed" || "${status}" == "missing" ]]; then
    needs_help=1
  elif [[ "${pid}" == "0" && "${status}" != "running" ]]; then
    needs_help=1
  elif activity_stale "${activity}"; then
    needs_help=1
  fi
  if (( needs_help == 0 )); then
    continue
  fi
  remaining=$(( target > committed ? target - committed : 1 ))
  candidates+=("${remaining}|${lane}|${host:-none}")
done

if (( ${#candidates[@]} == 0 )); then
  if [[ "${steal_active}" == "1" ]]; then
    best_lane=""
    best_remaining=0
    best_host=""
    for lane in "${all_lanes[@]}"; do
      [[ "${lane_complete[$lane]:-0}" == "1" ]] && continue
      target="$(lane_target "${lane}")"
      committed="${lane_committed[$lane]:-0}"
      remaining=$(( target > committed ? target - committed : 0 ))
      (( remaining <= 0 )) && continue
      host="${lane_host[$lane]:-}"
      [[ -z "${host}" ]] && continue
      if (( remaining > best_remaining )); then
        best_remaining="${remaining}"
        best_lane="${lane}"
        best_host="${host}"
      fi
    done
    if [[ -n "${best_lane}" && ${#idle_hosts[@]} -gt 0 ]]; then
      new_host=""
      for candidate in "${idle_hosts[@]}"; do
        if [[ "${host_freed[$candidate]:-0}" == "1" ]]; then
          new_host="${candidate}"
          break
        fi
      done
      [[ -n "${new_host}" ]] || new_host="${idle_hosts[0]}"
      if [[ "${host_freed[$new_host]:-0}" != "1" ]]; then
        log "action=none reason=steal_active_skipped idle_not_freed host=${new_host}"
        exit 0
      fi
      if [[ "${best_host}" != "${new_host}" ]] && ! on_cooldown "${new_host}"; then
        if [[ "${dry_run}" == "1" ]]; then
          log "dry_run steal_active lane=${best_lane} from=${best_host} to=${new_host} remaining=${best_remaining}"
        else
          log "steal_active lane=${best_lane} from=${best_host} to=${new_host} remaining=${best_remaining}"
          sync_lane_meta_locally "${best_lane}" "${best_host}"
          "${catalog_dir}/reassign_datacite_lane.sh" "${best_lane}" "${new_host}"
          ensure_watchdog_lane "${new_host}" "${best_lane}"
          mark_rebalanced "${new_host}"
        fi
        log "action=done reassigned=1 mode=steal_active"
        exit 0
      fi
    fi
  fi
  log "action=none reason=no_stalled_lanes idle_hosts=${#idle_hosts[@]}"
  exit 0
fi

IFS=$'\n' sorted_candidates=($(printf '%s\n' "${candidates[@]}" | sort -t'|' -k1,1n))
reassigned=0

for entry in "${sorted_candidates[@]}"; do
  (( ${#idle_hosts[@]} == 0 )) && break
  IFS='|' read -r _remaining lane old_host <<< "${entry}"
  new_host=""
  restart_same_host=0

  if [[ -n "${old_host}" && "${old_host}" != "none" ]]; then
    for candidate_host in "${idle_hosts[@]}"; do
      if [[ "${candidate_host}" == "${old_host}" ]]; then
        new_host="${old_host}"
        restart_same_host=1
        break
      fi
    done
  fi
  if [[ -z "${new_host}" ]]; then
    new_host="${idle_hosts[0]}"
  fi
  [[ -n "${new_host}" ]] || break

  if on_cooldown "${new_host}"; then
    log "skip lane=${lane} host=${new_host} reason=cooldown"
    continue
  fi

  if [[ "${dry_run}" == "1" ]]; then
    if (( restart_same_host )); then
      log "dry_run lane=${lane} host=${new_host} action=restart"
    else
      log "dry_run lane=${lane} from=${old_host} to=${new_host} action=reassign"
    fi
    reassigned=$((reassigned + 1))
    idle_hosts=("${idle_hosts[@]:1}")
    continue
  fi

  if (( restart_same_host )); then
    log "restart lane=${lane} host=${new_host}"
    scp -q -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 \
      "${catalog_dir}/restart_datacite_shard_clean.ps1" "user@${new_host}:C:/Users/user/restart_datacite_shard_clean.ps1"
    ssh -n -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=8 "user@${new_host}" \
      "powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:/Users/user/restart_datacite_shard_clean.ps1 -ShardName ${lane}"
    ensure_watchdog_lane "${new_host}" "${lane}"
    mark_rebalanced "${new_host}"
    reassigned=$((reassigned + 1))
    idle_hosts=("${idle_hosts[@]:1}")
    continue
  fi

  log "assign lane=${lane} from=${old_host} to=${new_host}"
  if [[ -n "${old_host}" && "${old_host}" != "none" ]] && host_reachable "${old_host}"; then
    sync_lane_meta_locally "${lane}" "${old_host}"
  fi
  "${catalog_dir}/reassign_datacite_lane.sh" "${lane}" "${new_host}"
  ensure_watchdog_lane "${new_host}" "${lane}"
  mark_rebalanced "${new_host}"
  reassigned=$((reassigned + 1))
  idle_hosts=("${idle_hosts[@]:1}")
done

log "action=done reassigned=${reassigned}"
