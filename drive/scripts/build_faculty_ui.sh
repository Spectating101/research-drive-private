#!/usr/bin/env bash
# Production UI = Vite React desk (dist/). Legacy one-file UI kept as research_data_library.html only.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ROOT"
npm run build
echo "faculty UI → dist/ (Vite React desk)"
