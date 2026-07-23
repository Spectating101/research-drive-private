#!/usr/bin/env bash
exec bash "$(cd "$(dirname "$0")/../.." && pwd)/drive/scripts/ops/repo_authority_check.sh" "$@"
