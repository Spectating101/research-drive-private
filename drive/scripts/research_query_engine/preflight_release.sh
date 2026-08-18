#!/usr/bin/env bash
# Validate a complete release BEFORE the live service is touched. Read-only.
#
# Every guard here is one the run script already enforces at boot. The difference is
# timing: run_optiplex_front_door.sh enforces them after systemd has stopped the old
# process, so a mismatch becomes an outage and a restart loop. Checking first turns the
# same mismatch into a refusal to start the deploy.
#
# Both outages on 2026-08-18 would have been caught here: a UI checkout that had moved to
# another branch under a hardcoded expected SHA, and a checkout whose dist symlink had no
# releases/<sha>/ behind it.
#
#   bash preflight_release.sh              # uses the service env file
#   bash preflight_release.sh --json
#
# Exit 0 only when the release is coherent. Non-zero means do not deploy.
set -u -o pipefail

ENV_FILE="${FRONT_DOOR_ENV:-$HOME/.config/research-drive/front-door.env}"
JSON=0
[ "${1:-}" = "--json" ] && JSON=1

fail=0
notes=()
note() { notes+=("$1"); }
bad()  { notes+=("FAIL: $1"); fail=1; }

[ -f "$ENV_FILE" ] || { echo "no env file: $ENV_FILE" >&2; exit 2; }
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a

backend_root="${SHARPE_REPO_ROOT:-}"
[ -n "$backend_root" ] || backend_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
public_root="${YZU_PUBLIC_REPO:-}"
static_dir="${YZU_DESK_STATIC_DIR:-}"
python_bin="${YZU_PYTHON_BIN:-python3}"
registry="${SHARPE_REGISTRY_PATH:-config/research_query_registry.json}"

command -v git >/dev/null 2>&1 || bad "git missing"
[ -x "$python_bin" ] || bad "python missing: $python_bin"

backend_sha="$(git -C "$backend_root" rev-parse HEAD 2>/dev/null || echo unknown)"
[ "$backend_sha" = unknown ] && bad "backend is not a git checkout: $backend_root"

[ -n "$public_root" ] || bad "YZU_PUBLIC_REPO unset"
ui_sha="unknown"
if [ -n "$public_root" ] && [ -d "$public_root" ]; then
  ui_sha="$(git -C "$public_root" rev-parse HEAD 2>/dev/null || echo unknown)"
  [ "$ui_sha" = unknown ] && bad "UI checkout is not a git checkout: $public_root"
  ui_branch="$(git -C "$public_root" rev-parse --abbrev-ref HEAD 2>/dev/null || echo detached)"
  ui_dirty="$(git -C "$public_root" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"
  note "ui_branch=$ui_branch ui_tracked_dirty=$ui_dirty"
  [ "$ui_dirty" != "0" ] && bad "UI checkout has tracked changes; the build would not be reproducible"
else
  bad "UI checkout absent: ${public_root:-<unset>}"
fi

[ -n "${YZU_PUBLIC_SHA:-}" ] || bad "YZU_PUBLIC_SHA unset"
if [ -n "${YZU_PUBLIC_SHA:-}" ] && [ "$ui_sha" != unknown ] && [ "$ui_sha" != "$YZU_PUBLIC_SHA" ]; then
  bad "UI checkout $ui_sha != expected $YZU_PUBLIC_SHA (someone moved the tree, or the env is stale)"
fi

[ -f "$static_dir/index.html" ] || bad "no built UI at $static_dir/index.html"
identity="$static_dir/research-drive-build.json"
built_public=""; built_private=""
if [ -f "$identity" ]; then
  built_public="$("$python_bin" -c "import json,sys;print(json.load(open(sys.argv[1])).get('public_sha',''))" "$identity" 2>/dev/null)"
  built_private="$("$python_bin" -c "import json,sys;print(json.load(open(sys.argv[1])).get('private_sha',''))" "$identity" 2>/dev/null)"
  [ "$built_public" = "$ui_sha" ] || bad "build was made from UI $built_public, checkout is $ui_sha"
  [ "$built_private" = "$backend_sha" ] || bad "build names backend $built_private, checkout is $backend_sha (regenerate the identity)"
else
  bad "no build identity at $identity"
fi

# A releases/<sha>/ must sit behind the dist link, or --identity-only cannot write.
if [ -n "$public_root" ] && [ -n "${YZU_PUBLIC_SHA:-}" ]; then
  [ -f "$public_root/releases/$YZU_PUBLIC_SHA/index.html" ] \
    || bad "no releases/$YZU_PUBLIC_SHA/index.html under $public_root; identity regeneration will fail"
fi

reg_abs="$registry"; case "$reg_abs" in /*) ;; *) reg_abs="$backend_root/$registry";; esac
reg_hash="absent"; reg_rows="0"
if [ -f "$reg_abs" ]; then
  reg_hash="$(sha256sum "$(readlink -f "$reg_abs")" 2>/dev/null | cut -c1-16)"
  reg_rows="$("$python_bin" -c "import json,sys;print(len(json.load(open(sys.argv[1])).get('datasets') or []))" "$reg_abs" 2>/dev/null || echo 0)"
  [ "$reg_rows" = "0" ] && bad "registry parsed to 0 datasets: $reg_abs"
else
  bad "registry absent: $reg_abs"
fi

roots="${RESEARCH_DATA_ROOTS:-<unset>}"
[ "$roots" = "<unset>" ] && note "WARN: RESEARCH_DATA_ROOTS unset; holdings counts will read as absent"

if [ "$JSON" = "1" ]; then
  "$python_bin" - "$backend_sha" "$ui_sha" "$reg_hash" "$reg_rows" "$roots" "$fail" <<'PY'
import json,sys
b,u,h,r,roots,fail=sys.argv[1:7]
print(json.dumps({"ready": fail=="0","backend_sha":b,"ui_sha":u,
                  "registry_sha256_16":h,"registry_rows":int(r),"data_roots":roots}, indent=2))
PY
else
  echo "backend_sha   $backend_sha"
  echo "ui_sha        $ui_sha"
  echo "registry      $reg_rows rows, sha256:$reg_hash"
  echo "data_roots    $roots"
  for n in "${notes[@]:-}"; do [ -n "$n" ] && echo "  $n"; done
  [ "$fail" = "0" ] && echo "READY — safe to promote" || echo "NOT READY — do not touch the live service"
fi
exit "$fail"
