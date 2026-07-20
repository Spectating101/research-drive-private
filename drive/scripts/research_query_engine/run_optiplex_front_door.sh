#!/usr/bin/env bash
# Run the Tailscale-internal same-origin Research Drive front door.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
: "${YZU_PUBLIC_REPO:?set YZU_PUBLIC_REPO to the public yzu-cluster checkout}"
: "${YZU_PUBLIC_SHA:?set YZU_PUBLIC_SHA to the approved public authority commit}"
: "${YZU_DESK_HOST:?set YZU_DESK_HOST to the Optiplex Tailscale IP}"
: "${YZU_DESK_ACCESS_TOKEN:?set YZU_DESK_ACCESS_TOKEN to protect material desk writes}"

case "${YZU_DESK_HOST}" in
  0.0.0.0|::|"[::]")
    echo "refusing broad bind for the Tailscale-internal release: ${YZU_DESK_HOST}" >&2
    exit 2
    ;;
esac

public_root="$(cd "${YZU_PUBLIC_REPO}" && pwd)"
static_dir="${YZU_DESK_STATIC_DIR:-${public_root}/dist}"
port="${YZU_DESK_PORT:-8765}"
registry="${SHARPE_REGISTRY_PATH:-${YZU_REGISTRY_PATH:-config/research_query_registry.json}}"
python_bin="${YZU_PYTHON_BIN:-python3}"
build_identity="${static_dir}/research-drive-build.json"

for command in git "${python_bin}"; do
  command -v "${command}" >/dev/null 2>&1 || {
    echo "required runtime command missing: ${command}" >&2
    exit 2
  }
done
[[ -f "${static_dir}/index.html" ]] || {
  echo "front-door build missing: ${static_dir}/index.html" >&2
  echo "run drive/scripts/research_query_engine/build_optiplex_front_door.sh first" >&2
  exit 1
}
[[ -f "${build_identity}" ]] || {
  echo "front-door build identity missing: ${build_identity}" >&2
  exit 1
}

actual_public_sha="$(git -C "${public_root}" rev-parse HEAD)"
actual_private_sha="$(git -C "${repo_root}" rev-parse HEAD)"
mapfile -t built_shas < <(
  "${python_bin}" - "${build_identity}" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(str(payload.get("public_sha") or ""))
print(str(payload.get("private_sha") or ""))
PY
)
built_public_sha="${built_shas[0]:-}"
built_private_sha="${built_shas[1]:-}"

if [[ "${actual_public_sha}" != "${YZU_PUBLIC_SHA}" ]]; then
  echo "public checkout authority mismatch: expected ${YZU_PUBLIC_SHA}, got ${actual_public_sha}" >&2
  exit 1
fi
if [[ "${built_public_sha}" != "${actual_public_sha}" ]]; then
  echo "served UI was built from ${built_public_sha:-unknown}, public checkout is ${actual_public_sha}" >&2
  exit 1
fi
if [[ "${built_private_sha}" != "${actual_private_sha}" ]]; then
  echo "served UI metadata names private ${built_private_sha:-unknown}, checkout is ${actual_private_sha}; rebuild before start" >&2
  exit 1
fi

cd "${repo_root}"
export SHARPE_REPO_ROOT="${SHARPE_REPO_ROOT:-${repo_root}}"
export PYTHONPATH="${repo_root}:${repo_root}/kernel:${repo_root}/drive${PYTHONPATH:+:${PYTHONPATH}}"
export YZU_DESK_SERVE_UI=true
export YZU_DESK_STATIC_DIR="${static_dir}"

exec "${python_bin}" drive/scripts/research_query_engine/server.py \
  --host "${YZU_DESK_HOST}" \
  --port "${port}" \
  --registry "${registry}" \
  --static-dir "${static_dir}" \
  --serve-ui
