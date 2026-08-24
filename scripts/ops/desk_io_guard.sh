#!/usr/bin/env bash
# Deprioritize local GDELT / gzip I/O so the Research Desk stays responsive.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/platform_env.sh
source "${SCRIPT_DIR}/../lib/platform_env.sh"

RENICE="${DESK_IO_GUARD_NICE:-15}"
IONICE_CLASS="${DESK_IO_GUARD_IONICE_CLASS:-3}"
IONICE_PRIO="${DESK_IO_GUARD_IONICE_PRIO:-7}"

patterns=(
  'gdelt_gkg_expanded'
  'build_gdelt_crypto'
  'news_shock_gkg_expanded'
  'gzip -t'
  'expand_gdelt_entity'
)

adjusted=0
for pat in "${patterns[@]}"; do
  while read -r pid; do
    [[ -n "${pid}" ]] || continue
    renice -n "${RENICE}" -p "${pid}" >/dev/null 2>&1 || true
    if [[ "${IONICE_CLASS}" == "3" ]]; then
      ionice -c3 -p "${pid}" >/dev/null 2>&1 || true
    else
      ionice -c "${IONICE_CLASS}" -n "${IONICE_PRIO}" -p "${pid}" >/dev/null 2>&1 || true
    fi
    adjusted=$((adjusted + 1))
  done < <(pgrep -f "${pat}" 2>/dev/null || true)
done

if [[ "${1:-}" == "--json" ]]; then
  python3 - <<PY
import json
print(json.dumps({"adjusted_pids": ${adjusted}, "nice": ${RENICE}, "ionice_class": ${IONICE_CLASS}}, indent=2))
PY
else
  echo "desk_io_guard: adjusted ${adjusted} process(es) nice=${RENICE} ionice=${IONICE_CLASS}"
fi
