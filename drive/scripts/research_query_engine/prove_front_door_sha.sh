#!/usr/bin/env bash
# Prove deployed front-door UI stamp matches private/main HEAD.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
BUILD="${RESEARCH_DRIVE_BUILD_JSON:-$HOME/.cache/research-drive/front-door-ui/current/research-drive-build.json}"
HEAD="$(git -C "$ROOT" rev-parse HEAD)"
if [[ ! -f "$BUILD" ]]; then
  echo "FAIL: missing build json: $BUILD" >&2
  exit 2
fi
STAMP="$(python3 -c "import json; d=json.load(open('$BUILD')); print((d.get('private_sha') or d.get('backend_sha') or '').strip())")"
if [[ -z "$STAMP" ]]; then
  echo "FAIL: build json has no private_sha/backend_sha" >&2
  exit 2
fi
if [[ "$STAMP" != "$HEAD" && "$STAMP" != "${HEAD:0:12}"* && "$HEAD" != "${STAMP:0:12}"* ]]; then
  echo "FAIL: stamped=$STAMP head=$HEAD" >&2
  exit 1
fi
echo "OK private_sha=$STAMP head=$HEAD"
