#!/usr/bin/env bash
# Run the Tailscale-internal same-origin Research Drive front door.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
: "${YZU_PUBLIC_REPO:?set YZU_PUBLIC_REPO to the public yzu-cluster checkout}"
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

[[ -f "${static_dir}/index.html" ]] || {
  echo "front-door build missing: ${static_dir}/index.html" >&2
  echo "run drive/scripts/research_query_engine/build_optiplex_front_door.sh first" >&2
  exit 1
}
command -v "${python_bin}" >/dev/null 2>&1 || {
  echo "python runtime missing: ${python_bin}" >&2
  exit 2
}

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
