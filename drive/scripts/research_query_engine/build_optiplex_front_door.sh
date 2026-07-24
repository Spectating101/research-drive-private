#!/usr/bin/env bash
# Build the public yzu-cluster authority for the private same-origin desk server.
set -euo pipefail

private_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
public_root="${YZU_PUBLIC_REPO:-${1:-}}"
expected_sha="${YZU_PUBLIC_SHA:-}"
identity_only="${YZU_BUILD_IDENTITY_ONLY:-0}"

usage() {
  echo "usage: YZU_PUBLIC_REPO=/absolute/path/to/yzu-cluster $0 [--identity-only]" >&2
}

write_build_identity() {
  local static_dir="$1"
  local public_sha="$2"
  local private_sha="$3"
  local built_at
  local identity_path
  built_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  identity_path="${static_dir}/research-drive-build.json"
  cat > "${identity_path}" <<EOF
{
  "public_repo": "Spectating101/yzu-cluster",
  "public_sha": "${public_sha}",
  "private_repo": "Spectating101/research-drive-private",
  "private_sha": "${private_sha}",
  "built_at_utc": "${built_at}",
  "release_scope": "tailscale-internal-same-origin"
}
EOF
  validate_build_identity "${identity_path}" "${public_sha}" "${private_sha}"
  printf 'build_identity=%s\n' "${identity_path}"
}

validate_build_identity() {
  local identity_path="$1"
  local expected_public_sha="$2"
  local expected_private_sha="$3"
  local python_bin="${YZU_PYTHON_BIN:-python3}"
  [[ -f "${identity_path}" ]] || {
    echo "build identity missing after write: ${identity_path}" >&2
    exit 1
  }
  "${python_bin}" - "${identity_path}" "${expected_public_sha}" "${expected_private_sha}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected_public = sys.argv[2]
expected_private = sys.argv[3]
payload = json.loads(path.read_text(encoding="utf-8"))
public_sha = str(payload.get("public_sha") or "")
private_sha = str(payload.get("private_sha") or "")
if not public_sha or not private_sha:
    raise SystemExit(f"build identity incomplete: {path}")
if public_sha != expected_public:
    raise SystemExit(f"build identity public_sha mismatch: {public_sha} != {expected_public}")
if private_sha != expected_private:
    raise SystemExit(f"build identity private_sha mismatch: {private_sha} != {expected_private}")
print(f"build_identity_ok={path}")
PY
}

if [[ "${1:-}" == "--identity-only" ]]; then
  identity_only=1
  shift
fi
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 2
fi

if [[ -z "${public_root}" ]]; then
  usage
  exit 2
fi
public_root="$(cd "${public_root}" && pwd)"

for command in git; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "missing required command: ${command}" >&2
    exit 2
  }
done
if [[ "${identity_only}" != "1" ]]; then
  command -v npm >/dev/null 2>&1 || {
    echo "missing required command: npm" >&2
    exit 2
  }
fi

[[ -f "${public_root}/package.json" ]] || {
  echo "public authority package.json missing: ${public_root}" >&2
  exit 2
}
if [[ "${identity_only}" != "1" ]]; then
  [[ -f "${public_root}/package-lock.json" ]] || {
    echo "public authority package-lock.json missing: ${public_root}" >&2
    exit 2
  }
fi

actual_sha="$(git -C "${public_root}" rev-parse HEAD)"
if [[ -n "${expected_sha}" && "${actual_sha}" != "${expected_sha}" ]]; then
  echo "public authority mismatch: expected ${expected_sha}, got ${actual_sha}" >&2
  exit 1
fi
if [[ "${YZU_ALLOW_DIRTY_PUBLIC:-0}" != "1" ]] && [[ -n "$(git -C "${public_root}" status --porcelain --untracked-files=no)" ]]; then
  echo "public authority has tracked working-tree changes; refusing reproducibility claim" >&2
  exit 1
fi

static_dir="${YZU_DESK_STATIC_DIR:-${public_root}/dist}"

if [[ "${identity_only}" != "1" ]]; then
  (
    cd "${public_root}"
    npm ci
    YZU_PAGES=false npm run build
  )
fi

[[ -f "${static_dir}/index.html" ]] || {
  echo "Vite build did not create ${static_dir}/index.html" >&2
  if [[ "${identity_only}" == "1" ]]; then
    echo "run a full front-door build before --identity-only" >&2
  fi
  exit 1
}

private_sha="$(git -C "${private_root}" rev-parse HEAD 2>/dev/null || printf unknown)"
write_build_identity "${static_dir}" "${actual_sha}" "${private_sha}"

printf 'front_door_static_dir=%s\n' "${static_dir}"
printf 'public_sha=%s\n' "${actual_sha}"
printf 'private_sha=%s\n' "${private_sha}"
