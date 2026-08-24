#!/usr/bin/env bash
# Clear sandbox hash junk from /tmp (keeps X11/ICE/dotnet). Safe to cron weekly.
set -euo pipefail
_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
exec bash "${SR_GDELT_TMP%/gdelt_expanded}/cleanup_nvme_tmp_nuclear.sh" 2>/dev/null || {
  cd /tmp || exit 1
  for d in * .[^.]*; do
    [[ -e "$d" ]] || continue
    case "$d" in .ICE-unix|.X11-unix|.XIM-unix|.font-unix|.dotnet) continue ;; esac
    rm -rf "$d" 2>/dev/null || true
  done
  df -h /tmp | tail -1
}
