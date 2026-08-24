#!/usr/bin/env bash
# Summarize SMART health for system NVMe + USB bulk HDD (Transcend).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/platform_env.sh
source "${SCRIPT_DIR}/../lib/platform_env.sh"

OUT_JSON="${DISK_HEALTH_JSON:-docs/status/generated/disk_health.json}"
CACHE_SEC="${DISK_HEALTH_CACHE_SEC:-0}"
USB_DEV="${DISK_HEALTH_USB_DEV:-/dev/sda}"
NVME_DEV="${DISK_HEALTH_NVME_DEV:-/dev/nvme0n1}"

usage() {
  echo "usage: $0 [--json] [--force]" >&2
  exit 2
}

want_json=0
force=0
for arg in "$@"; do
  case "${arg}" in
    --json) want_json=1 ;;
    --force) force=1 ;;
    -h|--help) usage ;;
  esac
done

if (( force == 0 && CACHE_SEC > 0 )) && [[ -f "${SR_DIR}/${OUT_JSON}" ]]; then
  if age="$(python3 - "${SR_DIR}/${OUT_JSON}" "${CACHE_SEC}" <<'PY'
import json, sys, time
from pathlib import Path
p, max_age = Path(sys.argv[1]), int(sys.argv[2])
d = json.loads(p.read_text(encoding="utf-8"))
age = time.time() - d.get("epoch", 0)
print(int(age))
raise SystemExit(0 if age < max_age else 1)
PY
  )" 2>/dev/null; then
    if (( want_json == 1 )); then
      cat "${SR_DIR}/${OUT_JSON}"
    else
      python3 - "${SR_DIR}/${OUT_JSON}" <<'PY'
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(f"disk_health (cached): level={d.get('level')} usb_temp={d.get('usb_temp_c')}C nvme_temp={d.get('nvme_temp_c')}C")
for note in d.get("notes") or []:
    print(f"  - {note}")
PY
    fi
    exit 0
  fi
fi

cd "${SR_DIR}"
mkdir -p "$(dirname "${OUT_JSON}")"

python3 - "${USB_DEV}" "${NVME_DEV}" "${OUT_JSON}" <<'PY'
import json
import re
import subprocess
import sys
import time
from pathlib import Path

usb_dev, nvme_dev, out_rel = sys.argv[1:4]
ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
epoch = time.time()

def smartctl(*args: str) -> str:
    for cmd in (["sudo", "-n", "smartctl", *args], ["smartctl", *args]):
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if p.returncode in (0, 4):
            return p.stdout
    return ""


def parse_hdd(text: str) -> dict:
    out = {
        "smart_passed": None,
        "temp_c": None,
        "temp_max_c": None,
        "reallocated": None,
        "pending": None,
        "uncorrectable": None,
        "udma_crc": None,
        "power_on_hours": None,
        "load_cycle_count": None,
    }
    m = re.search(r"SMART overall-health self-assessment test result:\s+(\w+)", text)
    if m:
        out["smart_passed"] = m.group(1) == "PASSED"
    for line in text.splitlines():
        if "Temperature_Celsius" in line or "Airflow_Temperature_Cel" in line:
            nums = re.findall(r"(\d+)\s*\(", line)
            if nums and out["temp_c"] is None:
                out["temp_c"] = int(nums[0])
            span = re.search(r"Min/Max\s+(\d+)/(\d+)", line)
            if span:
                out["temp_max_c"] = int(span.group(2))
        if "Reallocated_Sector_Ct" in line:
            out["reallocated"] = int(line.split()[-1])
        if "Current_Pending_Sector" in line:
            out["pending"] = int(line.split()[-1])
        if "Offline_Uncorrectable" in line:
            out["uncorrectable"] = int(line.split()[-1])
        if "UDMA_CRC_Error_Count" in line:
            out["udma_crc"] = int(line.split()[-1])
        if "Power_On_Hours" in line:
            raw = line.split()[-1]
            out["power_on_hours"] = int(re.match(r"(\d+)", raw).group(1))
        if "Load_Cycle_Count" in line:
            raw = line.split()[-1]
            out["load_cycle_count"] = int(re.match(r"(\d+)", raw).group(1))
    return out


def parse_nvme(text: str) -> dict:
    out = {
        "smart_passed": None,
        "temp_c": None,
        "percent_used": None,
        "media_errors": None,
        "critical_warning": None,
        "unsafe_shutdowns": None,
    }
    m = re.search(r"SMART overall-health self-assessment test result:\s+(\w+)", text)
    if m:
        out["smart_passed"] = m.group(1) == "PASSED"
    for line in text.splitlines():
        if line.strip().startswith("Temperature:"):
            out["temp_c"] = int(re.search(r"(\d+)", line).group(1))
        if line.strip().startswith("Percentage Used:"):
            out["percent_used"] = int(re.search(r"(\d+)", line).group(1))
        if "Media and Data Integrity Errors:" in line:
            out["media_errors"] = int(line.split(":")[-1].strip())
        if line.strip().startswith("Critical Warning:"):
            out["critical_warning"] = line.split(":")[-1].strip()
        if "Unsafe Shutdowns:" in line:
            out["unsafe_shutdowns"] = int(line.split(":")[-1].strip())
    return out


usb = parse_hdd(smartctl("-H", "-A", usb_dev))
nvme = parse_nvme(smartctl("-H", "-a", nvme_dev))

notes = []
level = "ok"

if usb.get("smart_passed") is False or nvme.get("smart_passed") is False:
    level = "crit"
    notes.append("smart_failed")
for label, val in (
    ("usb_reallocated", usb.get("reallocated")),
    ("usb_pending", usb.get("pending")),
    ("usb_uncorrectable", usb.get("uncorrectable")),
):
    if val not in (None, 0):
        level = "crit"
        notes.append(f"{label}={val}")
if nvme.get("media_errors") not in (None, 0):
    level = "crit"
    notes.append(f"nvme_media_errors={nvme.get('media_errors')}")

usb_temp = usb.get("temp_c")
if usb_temp is not None:
    if usb_temp >= 58:
        level = "crit" if level != "crit" else level
        notes.append(f"usb_hot_{usb_temp}C")
    elif usb_temp >= 52:
        if level == "ok":
            level = "warn"
        notes.append(f"usb_warm_{usb_temp}C")

nvme_pct = nvme.get("percent_used")
if nvme_pct is not None and nvme_pct >= 80:
    if level == "ok":
        level = "warn"
    notes.append(f"nvme_wear_{nvme_pct}pct")

doc = {
    "generated_at": ts,
    "epoch": epoch,
    "level": level,
    "usb_dev": usb_dev,
    "nvme_dev": nvme_dev,
    "usb_temp_c": usb_temp,
    "usb_temp_max_lifetime_c": usb.get("temp_max_c"),
    "nvme_temp_c": nvme.get("temp_c"),
    "usb": usb,
    "nvme": nvme,
    "notes": notes,
    "guard_cmd": "bash scripts/ops/desk_io_guard.sh",
    "fleet_stop_cmd": "bash scripts/run_news_shock_gkg_expanded_fleet.sh stop",
}
Path(out_rel).write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
print(json.dumps(doc, indent=2))
PY

if (( want_json == 0 )); then
  python3 - "${OUT_JSON}" <<'PY'
import json, sys
from pathlib import Path
d = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(
    f"disk_health: level={d['level']} "
    f"usb={d.get('usb_temp_c')}C (lifetime max {d.get('usb_temp_max_lifetime_c')}C) "
    f"nvme={d.get('nvme_temp_c')}C wear={d.get('nvme', {}).get('percent_used')}%"
)
for note in d.get("notes") or []:
    print(f"  note: {note}")
if d["level"] == "ok":
    print("  no SMART damage indicators")
PY
fi

if python3 - "${OUT_JSON}" <<'PY'; then
import json, sys
from pathlib import Path
raise SystemExit(0 if json.loads(Path(sys.argv[1]).read_text())["level"] != "crit" else 1)
PY
  exit 0
fi
exit 1
