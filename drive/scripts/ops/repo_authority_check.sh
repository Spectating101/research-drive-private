#!/usr/bin/env bash
# Fail if critical desk backend files diverge across local authority trees.
# See drive/docs/REPO_AUTHORITY.md
set -euo pipefail

MOLINA_ROOT="${MOLINA_ROOT:-$(cd "$(dirname "$0")/../../../../.." && pwd)}"
# When invoked from front-door/drive/scripts/ops, ../../../../.. is Molina-Optiplex
# When copied under Sharpe/drive/scripts/ops, same depth → Molina-Optiplex
if [[ ! -d "$MOLINA_ROOT/research-drive-private-front-door" ]]; then
  # fallback: walk up looking for front-door sibling
  here="$(cd "$(dirname "$0")" && pwd)"
  for _ in 1 2 3 4 5 6 7 8; do
    if [[ -d "$here/research-drive-private-front-door" ]]; then
      MOLINA_ROOT="$here"
      break
    fi
    here="$(dirname "$here")"
  done
fi

FD="${REPO_AUTHORITY_FD:-$MOLINA_ROOT/research-drive-private-front-door}"
SR="${REPO_AUTHORITY_SR:-$MOLINA_ROOT/Sharpe-Renaissance}"
RI="${REPO_AUTHORITY_RI:-$MOLINA_ROOT/Sharpe-Renaissance-runtime-integration}"

CRITICAL=(
  drive/scripts/research_data_mcp/craft_collect.py
  drive/scripts/research_data_mcp/scrape_plan.py
  drive/scripts/research_data_mcp/tool_handlers.py
  drive/scripts/research_data_mcp/gateway.py
  drive/scripts/research_data_mcp/http_router.py
  drive/scripts/yzu_cluster/acquisitions.py
  drive/scripts/yzu_cluster/spectator_engine.py
  drive/scripts/yzu_cluster/runtime_adapter.py
  drive/scripts/research_query_engine/engine.py
  drive/docs/REPO_AUTHORITY.md
  drive/docs/SOL_REMOTE_HANDOFF.md
)

sha256_file() {
  local p="$1"
  if [[ ! -f "$p" ]]; then
    echo "MISSING"
    return 0
  fi
  sha256sum "$p" | awk '{print $1}'
}

echo "repo_authority_check"
echo "  FD=$FD"
echo "  SR=$SR"
echo "  RI=$RI"

fail=0
for rel in "${CRITICAL[@]}"; do
  h_fd="$(sha256_file "$FD/$rel")"
  h_sr="$(sha256_file "$SR/$rel")"
  h_ri="$(sha256_file "$RI/$rel")"
  # Config may be absent on RI (data bind) — only require FD==SR always;
  # RI must match when the file exists there OR when it's a Python script under drive/scripts.
  ok=1
  if [[ "$h_fd" == "MISSING" ]]; then
    echo "FAIL  $rel  front-door missing"
    fail=1
    continue
  fi
  if [[ "$h_fd" != "$h_sr" ]]; then
    echo "FAIL  $rel  FD!=SR  fd=${h_fd:0:12} sr=${h_sr:0:12}"
    ok=0
    fail=1
  fi
  case "$rel" in
    drive/scripts/*)
      if [[ "$h_ri" != "MISSING" && "$h_ri" != "$h_fd" ]]; then
        echo "FAIL  $rel  FD!=RI  fd=${h_fd:0:12} ri=${h_ri:0:12}"
        ok=0
        fail=1
      elif [[ "$h_ri" == "MISSING" ]]; then
        echo "WARN  $rel  RI missing (will sync in align step)"
      fi
      ;;
    drive/docs/*)
      # docs optional on RI
      ;;
  esac
  if [[ "$ok" -eq 1 ]]; then
    echo "OK    $rel  ${h_fd:0:12}"
  fi
done

# Remote sanity: Sharpe origin must be research-drive-private; yzu-fe is FE-only
if [[ -d "$SR/.git" ]]; then
  origin_url="$(git -C "$SR" remote get-url origin 2>/dev/null || true)"
  case "$origin_url" in
    *research-drive-private*)
      echo "OK    Sharpe origin → research-drive-private"
      ;;
    "")
      echo "WARN  Sharpe has no origin remote"
      ;;
    *)
      echo "FAIL  Sharpe origin is $origin_url (expected research-drive-private)"
      fail=1
      ;;
  esac
  yzu_url="$(git -C "$SR" remote get-url yzu-fe 2>/dev/null || git -C "$SR" remote get-url yzu 2>/dev/null || true)"
  case "$yzu_url" in
    *yzu-cluster*)
      echo "OK    Sharpe yzu-fe → yzu-cluster (FE only)"
      ;;
    "")
      echo "WARN  Sharpe has no yzu-fe/yzu remote (FE Sols may use another checkout)"
      ;;
    *)
      echo "WARN  Sharpe FE remote unexpected: $yzu_url"
      ;;
  esac
fi

if [[ "$fail" -ne 0 ]]; then
  echo "repo_authority_check: FAILED"
  exit 1
fi
echo "repo_authority_check: PASSED"
exit 0
