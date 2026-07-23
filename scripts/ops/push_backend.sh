#!/usr/bin/env bash
exec bash "$(cd "$(dirname "$0")/../.." && pwd)/drive/scripts/ops/push_backend.sh" "$@"
