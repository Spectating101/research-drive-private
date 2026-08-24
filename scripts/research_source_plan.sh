#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -lt 1 ]]; then
  echo "usage: $0 <research question or construct> [limit]" >&2
  exit 2
fi
q="$1"
limit="${2:-25}"
exec python3 scripts/research_query_engine_cli.py query research_source_plan q="$q" limit="$limit"
