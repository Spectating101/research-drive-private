#!/usr/bin/env bash
# Delegate to repo-root launcher (loads platform_env + CURSOR_* from .env.local).
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/scripts/run_yzu_cluster.sh" "$@"
