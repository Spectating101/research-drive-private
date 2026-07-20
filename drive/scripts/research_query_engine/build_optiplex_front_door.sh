#!/usr/bin/env bash
# Build the public yzu-cluster authority for the private same-origin desk server.
set -euo pipefail

private_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
public_root="${YZU_PUBLIC_REPO:-${1:-}}"
expected_sha="${YZU_PUBLIC_SHA:-}"

if [[ -z "${public_root}" ]]; then
  echo "usage: YZU_PUBLIC_REPO=/absolute/path/to/yzu-cluster $0" >&2
  exit 2
fi
public_root="$(cd "${public_root}" && pwd)"

for command in git npm; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "missing required command: ${command}" >&2
    exit 2
  }
done

[[ -f "${public_root}/package.json" ]] || {
  echo "public authority package.json missing: ${public_root}" >&2
  exit 2
}
[[ -f "${public_root}/package-lock.json" ]] || {
  echo "public authority package-lock.json missing: ${public_root}" >&2
  exit 2
}

actual_sha="$(git -C "${public_root}" rev-parse HEAD)"
if [[ -n "${expected_sha}" && "${actual_sha}" != "${expected_sha}" ]]; then
  echo "public authority mismatch: expected ${expected_sha}, got ${actual_sha}" >&2
  exit 1
fi
if [[ "${YZU_ALLOW_DIRTY_PUBLIC:-0}" != "1" ]] && [[ -n "$(git -C "${public_root}" status --porcelain --untracked-files=no)" ]]; then
  echo "public authority has tracked working-tree changes; refusing reproducibility claim" >&2
  exit 1
fi

(
  cd "${public_root}"
  npm ci
  YZU_PAGES=false npm run build
)

static_dir="${public_root}/dist"
[[ -f "${static_dir}/index.html" ]] || {
  echo "Vite build did not create ${static_dir}/index.html" >&2
  exit 1
}

private_sha="$(git -C "${private_root}" rev-parse HEAD 2>/dev/null || printf unknown)"
built_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
cat > "${static_dir}/research-drive-build.json" <<EOF
{
  "public_repo": "Spectating101/yzu-cluster",
  "public_sha": "${actual_sha}",
  "private_repo": "Spectating101/research-drive-private",
  "private_sha": "${private_sha}",
  "built_at_utc": "${built_at}",
  "release_scope": "tailscale-internal-same-origin"
}
EOF

printf 'front_door_static_dir=%s\n' "${static_dir}"
printf 'public_sha=%s\n' "${actual_sha}"
printf 'private_sha=%s\n' "${private_sha}"
