#!/usr/bin/env bash
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
branch="$(git branch --show-current)"
upstream="$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)"

remote_url() {
  git remote get-url "$1" 2>/dev/null || true
}

private_remote=""
public_remote=""
for remote in $(git remote); do
  url="$(remote_url "$remote")"
  case "$url" in
    *research-drive-private*) private_remote="$remote" ;;
    *yzu-cluster*) public_remote="$remote" ;;
  esac
done

echo "discover_topology_check"
echo "  root=$root"
echo "  branch=${branch:-detached}"
echo "  upstream=${upstream:-none}"
echo "  private_remote=${private_remote:-absent}"
echo "  public_remote=${public_remote:-absent}"

fail=0
case "$branch" in
  *discover-evidence-verdict-cdf*|*discover*frontend*|*discover*ui*)
    if [[ -z "$public_remote" || "$upstream" != "$public_remote/"* ]]; then
      echo "FAIL  frontend Discover branch must track the yzu-cluster remote"
      fail=1
    else
      echo "OK    frontend branch tracks yzu-cluster"
    fi
    ;;
  *discover-evidence-verdict|reconcile/discover-evidence-main)
    if [[ -z "$private_remote" || "$upstream" != "$private_remote/"* ]]; then
      echo "FAIL  backend Discover branch must track research-drive-private"
      fail=1
    else
      echo "OK    backend branch tracks research-drive-private"
    fi
    ;;
esac

if [[ -n "$private_remote" && -n "$public_remote" ]] \
  && git show-ref --verify --quiet "refs/remotes/$private_remote/main" \
  && git show-ref --verify --quiet "refs/remotes/$public_remote/main"; then
  if git merge-base "$private_remote/main" "$public_remote/main" >/dev/null 2>&1; then
    echo "WARN  public and private mains now share ancestry; re-audit the repository boundary"
  else
    echo "OK    public and private repositories remain independent histories"
  fi
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "WARN  worktree is dirty; do not use it as a release merge source"
else
  echo "OK    worktree is clean"
fi

if [[ "$fail" -ne 0 ]]; then
  echo "discover_topology_check: FAILED"
  exit 1
fi
echo "discover_topology_check: PASSED"
