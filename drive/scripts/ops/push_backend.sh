#!/usr/bin/env bash
# Push desk/backend commits to research-drive-private only.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
remote="origin"
if ! git remote get-url origin >/dev/null 2>&1; then
  if git remote get-url private >/dev/null 2>&1; then
    remote="private"
  else
    echo "error: need origin or private remote → research-drive-private" >&2
    exit 2
  fi
fi
url="$(git remote get-url "$remote")"
case "$url" in
  *research-drive-private*) ;;
  *)
    echo "error: $remote points at $url — expected research-drive-private" >&2
    exit 2
    ;;
esac
# Refuse accidental yzu-fe / yzu push target
for bad in yzu yzu-fe; do
  if [[ "${1:-}" == "$bad" ]]; then
    echo "error: refuse backend push to $bad (FE/Sol remote only). See drive/docs/REPO_AUTHORITY.md" >&2
    exit 2
  fi
done
echo "pushing HEAD to $remote ($url) — backend authority"
exec git push -u "$remote" HEAD "$@"
