#!/usr/bin/env bash
# Reverse-proxy the YZU research desk behind Caddy (TLS + optional access token).
set -euo pipefail

_script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/platform_env.sh
source "${_script_dir}/lib/platform_env.sh"
cd "${SR_DIR}"
repo_root="${SR_DIR}"
HOST="${YZU_DESK_HOST:-desk.yzu.local}"
UPSTREAM="${YZU_DESK_UPSTREAM:-127.0.0.1:8765}"
CONF="${YZU_CADDY_CONF:-/etc/caddy/Caddyfile.d/yzu-desk.caddy}"

cat <<EOF
# Install snippet to ${CONF} (requires root):

${HOST} {
    encode gzip
    reverse_proxy ${UPSTREAM}
    header {
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
    }
}

# On the controller before starting prod:
#   export YZU_DESK_ACCESS_TOKEN=\$(openssl rand -hex 24)
#   echo 'YZU_DESK_ACCESS_TOKEN=...' >> .env.local
#   scripts/run_yzu_cluster_prod.sh

# Faculty UI: sign-in gate + optional desk token when YZU_DESK_ACCESS_TOKEN is set.
EOF

if [[ "${1:-}" == "--write" && "$(id -u)" -eq 0 ]]; then
  mkdir -p "$(dirname "$CONF")"
  cat >"$CONF" <<CADDY
${HOST} {
    encode gzip
    reverse_proxy ${UPSTREAM}
    header {
        X-Frame-Options DENY
        Referrer-Policy strict-origin-when-cross-origin
    }
}
CADDY
  systemctl reload caddy 2>/dev/null || caddy reload --config /etc/caddy/Caddyfile
  echo "Wrote ${CONF} and reloaded Caddy."
fi
