#!/usr/bin/env bash
# Install the Research Drive front door as a systemd user service.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
run_script="${repo_root}/drive/scripts/research_query_engine/run_optiplex_front_door.sh"
env_file="${YZU_FRONT_DOOR_ENV:-${HOME}/.config/research-drive/front-door.env}"
unit_dir="${HOME}/.config/systemd/user"
unit_file="${unit_dir}/research-drive-front-door.service"
start_now=0

if [[ "${1:-}" == "--start" ]]; then
  start_now=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--start]" >&2
  exit 2
fi

command -v systemctl >/dev/null 2>&1 || {
  echo "systemctl is required" >&2
  exit 2
}
command -v bash >/dev/null 2>&1 || {
  echo "bash is required" >&2
  exit 2
}
[[ -f "${env_file}" ]] || {
  echo "environment file missing: ${env_file}" >&2
  echo "copy drive/config/optiplex-front-door.env.example and fill secret values out of git" >&2
  exit 2
}
[[ -f "${run_script}" ]] || {
  echo "runtime launcher missing: ${run_script}" >&2
  exit 2
}

if command -v stat >/dev/null 2>&1; then
  env_mode="$(stat -c '%a' "${env_file}" 2>/dev/null || true)"
  if [[ -n "${env_mode}" && "${env_mode: -2}" != "00" ]]; then
    echo "environment file exposes secrets to group/other (mode ${env_mode}); run chmod 600 ${env_file}" >&2
    exit 2
  fi
fi

mkdir -p "${unit_dir}"
backup=""
if [[ -f "${unit_file}" ]]; then
  backup="${unit_file}.bak.$(date -u +%Y%m%dT%H%M%SZ)"
  cp "${unit_file}" "${backup}"
fi

cat > "${unit_file}" <<EOF
[Unit]
Description=Research Drive Tailscale-internal same-origin front door
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${repo_root}
EnvironmentFile=${env_file}
ExecStart=/usr/bin/env bash ${run_script}
Restart=on-failure
RestartSec=5
TimeoutStopSec=20
KillSignal=SIGTERM
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable research-drive-front-door.service
if [[ "${start_now}" == "1" ]]; then
  systemctl --user restart research-drive-front-door.service
fi

linger="unknown"
if command -v loginctl >/dev/null 2>&1; then
  linger="$(loginctl show-user "${USER}" -p Linger --value 2>/dev/null || printf unknown)"
fi

printf 'unit=%s\n' "${unit_file}"
printf 'environment=%s\n' "${env_file}"
printf 'user_linger=%s\n' "${linger}"
if [[ "${linger}" != "yes" ]]; then
  printf 'boot_persistence_warning=user service may not start before login; host operator should evaluate sudo loginctl enable-linger %s\n' "${USER}"
fi
if [[ -n "${backup}" ]]; then
  printf 'previous_unit_backup=%s\n' "${backup}"
fi
printf 'status=systemctl --user status research-drive-front-door.service\n'
printf 'logs=journalctl --user -u research-drive-front-door.service -n 200 --no-pager\n'
printf 'rollback=systemctl --user disable --now research-drive-front-door.service && restore the previous unit backup if one was reported\n'
