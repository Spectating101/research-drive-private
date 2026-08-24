#!/usr/bin/env bash
# Expanded GDELT fleet watchdog: progress, /tmp, workers, auto-ensure on stall.
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"

FLEET_CONFIG="${FLEET_CONFIG:-config/gdelt_expanded_fleet.json}"
MANIFEST="${MANIFEST:-/media/phyrexian/Transcend/sharpe-renaissance/data_lake/news_shock_taxonomy/derived/gdelt_expanded_queue_state/queue_manifest.json}"
STATE_FILE="${STATE_FILE:-data_lake/news_shock_taxonomy/derived/gdelt_expanded_queue_state/fleet_health_state.json}"
LOG_DIR="${LOG_DIR:-logs/news_shock_taxonomy/expanded_work_steal}"
LOG_FILE="${LOG_DIR}/fleet_health_monitor.log"
ALERT_JSON="${ALERT_JSON:-docs/status/generated/gdelt_expanded_fleet_alert.json}"

STALL_WARN_HOURS="${STALL_WARN_HOURS:-3}"
STALL_CRIT_HOURS="${STALL_CRIT_HOURS:-6}"
TMP_WARN_PCT="${TMP_WARN_PCT:-80}"
USB_TEMP_WARN_C="${USB_TEMP_WARN_C:-52}"
USB_TEMP_CRIT_C="${USB_TEMP_CRIT_C:-58}"
AUTO_ENSURE="${AUTO_ENSURE:-1}"
AUTO_IO_GUARD="${AUTO_IO_GUARD:-1}"
AUTO_THERMAL_PAUSE_LOCAL="${AUTO_THERMAL_PAUSE_LOCAL:-1}"
DESKTOP_NOTIFY="${DESKTOP_NOTIFY:-0}"
NOTIFY_DEDUP_FILE="${NOTIFY_DEDUP_FILE:-data_lake/news_shock_taxonomy/derived/gdelt_expanded_queue_state/fleet_notify_dedup.txt}"

mkdir -p "${LOG_DIR}" "$(dirname "${ALERT_JSON}")" "$(dirname "${STATE_FILE}")"

ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
now_epoch="$(date +%s)"

log() {
  printf '%s %s\n' "${ts}" "$*" | tee -a "${LOG_FILE}"
}

desktop_notify() {
  local urgency="$1"
  local title="$2"
  local body="$3"
  local sig="$4"
  [[ "${DESKTOP_NOTIFY}" == "1" ]] || return 0
  command -v notify-send >/dev/null 2>&1 || return 0

  if [[ -f "${NOTIFY_DEDUP_FILE}" ]] && [[ "$(cat "${NOTIFY_DEDUP_FILE}" 2>/dev/null)" == "${sig}" ]]; then
    return 0
  fi
  printf '%s\n' "${sig}" >"${NOTIFY_DEDUP_FILE}"

  export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
  export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=${XDG_RUNTIME_DIR}/bus}"
  notify-send -u "${urgency}" -t 0 "${title}" "${body}" 2>/dev/null \
    || log "notify_skipped title=${title}"
}

read_manifest() {
  python3 - "${MANIFEST}" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.is_file():
    print("0\t0\t0\tmissing")
    raise SystemExit(0)
d = json.loads(p.read_text(encoding="utf-8"))
print(
    f"{d.get('complete_months', 0)}\t{d.get('total_months', 0)}\t"
    f"{d.get('pending_months', 0)}\t{d.get('run_tag', '')}"
)
PY
}

count_enabled_workers() {
  python3 - "${FLEET_CONFIG}" <<'PY'
import json, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(sum(1 for w in cfg.get("workers") or [] if w.get("enabled", True)))
PY
}

count_running_helpers() {
  # pgrep exits 1 when idle; do not fail the monitor under pipefail.
  pgrep -f "run_news_shock_gkg_expanded_work_steal_queue.sh helper_" 2>/dev/null | wc -l | tr -d ' ' || true
}

tmp_pct() {
  df /tmp | awk 'NR==2 {gsub("%","",$5); print $5}'
}

transcend_free_gb() {
  df -BG /media/phyrexian/Transcend 2>/dev/null | awk 'NR==2 {gsub("G","",$4); print $4}' || echo "0"
}

usb_temp_c() {
  bash scripts/ops/disk_health_check.sh --json --force 2>/dev/null \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('usb_temp_c') or '')" \
    || true
}

load_state() {
  if [[ -f "${STATE_FILE}" ]]; then
    python3 - "${STATE_FILE}" <<'PY'
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(d.get("complete_months", 0), d.get("recorded_at_epoch", 0), sep="\t")
PY
  else
    echo -e "0\t0"
  fi
}

save_state() {
  local complete="$1"
  python3 - "${STATE_FILE}" "${complete}" "${now_epoch}" "${ts}" <<'PY'
import json, sys
from pathlib import Path
path, complete, epoch, ts = sys.argv[1:5]
Path(path).write_text(
    json.dumps(
        {
            "complete_months": int(complete),
            "recorded_at_epoch": int(epoch),
            "recorded_at": ts,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
PY
}

IFS=$'\t' read -r complete total pending run_tag < <(read_manifest)
enabled="$(count_enabled_workers)"
running="$(count_running_helpers)"
tmp_use="$(tmp_pct)"
transcend_free="$(transcend_free_gb)"
usb_temp="$(usb_temp_c)"

IFS=$'\t' read -r prev_complete prev_epoch < <(load_state)

stall_hours="0"
level="ok"
actions=()
warnings=()

if (( complete > prev_complete )) || (( prev_epoch == 0 )); then
  save_state "${complete}" "${now_epoch}"
  stall_hours="0"
elif (( prev_epoch > 0 )); then
  stall_secs=$(( now_epoch - prev_epoch ))
  stall_hours="$(python3 -c "print(round(${stall_secs}/3600, 2))")"
fi

if (( running < enabled )); then
  warnings+=("workers_running_${running}_of_${enabled}")
  level="warn"
  if [[ "${AUTO_ENSURE}" == "1" ]]; then
    actions+=("fleet_ensure")
  fi
fi

if [[ -n "${stall_hours}" ]] && python3 -c "exit(0 if float('${stall_hours}') >= float('${STALL_WARN_HOURS}') else 1)"; then
  warnings+=("no_progress_${stall_hours}h")
  level="warn"
fi

if [[ -n "${stall_hours}" ]] && python3 -c "exit(0 if float('${stall_hours}') >= float('${STALL_CRIT_HOURS}') else 1)"; then
  warnings+=("stalled_${stall_hours}h")
  level="crit"
  if [[ "${AUTO_ENSURE}" == "1" ]]; then
    actions+=("fleet_ensure")
  fi
fi

if (( tmp_use >= TMP_WARN_PCT )); then
  warnings+=("tmp_${tmp_use}pct")
  level="warn"
fi

if (( transcend_free < 100 )); then
  warnings+=("transcend_free_${transcend_free}G")
  if (( transcend_free < 50 )); then
    level="crit"
  elif [[ "${level}" == "ok" ]]; then
    level="warn"
  fi
fi

if [[ -n "${usb_temp}" ]]; then
  if python3 -c "exit(0 if float('${usb_temp}') >= float('${USB_TEMP_CRIT_C}') else 1)"; then
    warnings+=("usb_temp_${usb_temp}C")
    level="crit"
    if [[ "${AUTO_IO_GUARD}" == "1" ]]; then
      actions+=("desk_io_guard")
    fi
    if [[ "${AUTO_THERMAL_PAUSE_LOCAL}" == "1" ]]; then
      actions+=("pause_local_fetch")
    fi
  elif python3 -c "exit(0 if float('${usb_temp}') >= float('${USB_TEMP_WARN_C}') else 1)"; then
    warnings+=("usb_warm_${usb_temp}C")
    if [[ "${level}" == "ok" ]]; then
      level="warn"
    fi
    if [[ "${AUTO_IO_GUARD}" == "1" ]]; then
      actions+=("desk_io_guard")
    fi
  fi
fi

if (( complete >= total && total > 0 )); then
  level="done"
  warnings=()
  printf 'done\n' >"${NOTIFY_DEDUP_FILE}" 2>/dev/null || true
fi

# De-dupe actions
if ((${#actions[@]} > 0)); then
  mapfile -t actions < <(printf '%s\n' "${actions[@]}" | sort -u)
fi

log "level=${level} complete=${complete}/${total} pending=${pending} running=${running}/${enabled} tmp=${tmp_use}% transcend_free=${transcend_free}G usb_temp=${usb_temp:-na}C stall_h=${stall_hours} warnings=${warnings[*]:-none}"

for action in "${actions[@]}"; do
  case "${action}" in
    fleet_ensure)
      log "action=fleet_ensure reason=${warnings[*]:-workers}"
      bash scripts/run_news_shock_gkg_expanded_fleet.sh ensure >>"${LOG_FILE}" 2>&1 || true
      ;;
    desk_io_guard)
      log "action=desk_io_guard reason=${warnings[*]:-thermal}"
      bash scripts/ops/desk_io_guard.sh >>"${LOG_FILE}" 2>&1 || true
      ;;
    pause_local_fetch)
      log "action=pause_local_fetch reason=usb_temp_${usb_temp:-hot}"
      pkill -f "fetch_gdelt_gkg_asia_bulk.py" 2>/dev/null || true
      pkill -f "gzip -t.*gdelt_gkg" 2>/dev/null || true
      ;;
  esac
done

warn_args=()
if ((${#warnings[@]})); then
  for w in "${warnings[@]}"; do warn_args+=("$w"); done
fi
act_args=()
if ((${#actions[@]})); then
  for a in "${actions[@]}"; do act_args+=("$a"); done
fi

py_args=("${ALERT_JSON}" "${ts}" "${level}" "${complete}" "${total}" "${pending}" "${run_tag}" "${running}" "${enabled}" "${tmp_use}" "${transcend_free}" "${stall_hours}" "${usb_temp:-}")
if ((${#warn_args[@]})); then py_args+=("${warn_args[@]}"); fi
py_args+=("--")
if ((${#act_args[@]})); then py_args+=("${act_args[@]}"); fi

python3 - "${py_args[@]}" <<'PY'
import json, sys
from pathlib import Path

args = sys.argv[1:]
if "--" in args:
    split = args.index("--")
    head, tail = args[:split], args[split + 1 :]
else:
    head, tail = args, []
(
    path, ts, level, complete, total, pending, run_tag,
    running, enabled, tmp_use, transcend_free, stall_hours, usb_temp,
) = head[:13]
warnings = head[13:] if len(head) > 13 else []
actions = tail

doc = {
    "generated_at": ts,
    "level": level,
    "complete_months": int(complete),
    "total_months": int(total),
    "pending_months": int(pending),
    "run_tag": run_tag,
    "workers_running": int(running),
    "workers_enabled": int(enabled),
    "tmp_use_pct": int(tmp_use),
    "transcend_free_gb": int(transcend_free),
    "stall_hours": float(stall_hours or 0),
    "usb_temp_c": float(usb_temp) if usb_temp not in ("", None) else None,
    "warnings": list(warnings),
    "actions_taken": list(actions),
    "status_cmd": "bash scripts/run_news_shock_gkg_expanded_fleet.sh status",
    "log_file": "logs/news_shock_taxonomy/expanded_work_steal/fleet_health_monitor.log",
}
Path(path).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
PY

notify_sig="${level}|${warnings[*]:-none}|${complete}/${total}"
case "${level}" in
  crit)
    desktop_notify critical "GDELT fleet CRITICAL" \
      "${complete}/${total} complete · ${running}/${enabled} workers · ${warnings[*]:-check log} · auto-ensure ran" \
      "${notify_sig}"
    ;;
  warn)
    desktop_notify normal "GDELT fleet warning" \
      "${complete}/${total} complete · stall ${stall_hours}h · ${warnings[*]:-see alert json}" \
      "${notify_sig}"
    ;;
  done)
    desktop_notify low "GDELT fleet complete" \
      "All ${total} months finished (${run_tag})" \
      "${notify_sig}"
    ;;
  ok)
    if [[ -f "${NOTIFY_DEDUP_FILE}" ]] && grep -qv '^done$' "${NOTIFY_DEDUP_FILE}" 2>/dev/null; then
      rm -f "${NOTIFY_DEDUP_FILE}"
    fi
    ;;
esac

if [[ "${level}" == "crit" ]]; then
  exit 2
fi
exit 0
