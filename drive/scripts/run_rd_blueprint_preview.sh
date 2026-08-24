#!/usr/bin/env bash
# Research Drive UI blueprint — CLI wireframe preview (stdlib Python).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${SCRIPT_DIR}/.."
exec python3 scripts/rd_desk_blueprint_preview.py "$@"
