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
# Preserve an explicit candidate checkout before the service environment is
# sourced. The env file names the normal live checkout; preflight needs to be
# able to validate a clean, staged candidate without mutating that authority.
preflight_public_root="${YZU_PUBLIC_REPO:-}"
preflight_backend_root="${SHARPE_REPO_ROOT:-}"
JSON=0
[ "${1:-}" = "--json" ] && JSON=1

fail=0
notes=()
note() { notes+=("$1"); }
bad()  { notes+=("FAIL: $1"); fail=1; }

[ -f "$ENV_FILE" ] || { echo "no env file: $ENV_FILE" >&2; exit 2; }
# Sourcing under `set -u` aborts on any unbound expansion inside the env file, which is the
# same unsafe-env pattern this script exists to catch. Relax only for the source.
set +u
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
set -u

backend_root="${preflight_backend_root:-${SHARPE_REPO_ROOT:-}}"
[ -n "$backend_root" ] || backend_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
public_root="${preflight_public_root:-${YZU_PUBLIC_REPO:-}}"
# A promotion validates a staged candidate before changing the live dist link.
# The front-door env intentionally continues to name the live link, so use this
# separate, explicit override only for that read-only preflight.
static_dir="${PREFLIGHT_STATIC_DIR:-${YZU_DESK_STATIC_DIR:-}}"
python_bin="${YZU_PYTHON_BIN:-python3}"
registry="${SHARPE_REGISTRY_PATH:-config/research_query_registry.json}"

command -v git >/dev/null 2>&1 || bad "git missing"
command -v "$python_bin" >/dev/null 2>&1 || bad "python not executable: $python_bin"

backend_sha="$(git -C "$backend_root" rev-parse HEAD 2>/dev/null || echo unknown)"
[ "$backend_sha" = unknown ] && bad "backend is not a git checkout: $backend_root"

# The point of the gate is that the runtime IS the named commit. Checking only the UI let it
# return ready while backend source differed from the SHA it claimed to be deploying.
registry_rel="${SHARPE_REGISTRY_PATH:-config/research_query_registry.json}"
backend_dirty=0
backend_untracked=0
registry_typechange=0
if [ "$backend_sha" != unknown ]; then
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    code="${line:0:2}"
    path="${line:3}"
    case "$code" in
      '??') backend_untracked=$((backend_untracked+1)); continue ;;
    esac
    # The registry is a tracked regular file in Git and a symlink in the serving tree. That
    # is the unresolved ownership question, not an accidental edit, so name it separately.
    case "$path" in
      *"$registry_rel"|*research_query_registry.json)
        registry_typechange=1; continue ;;
    esac
    backend_dirty=$((backend_dirty+1))
    note "backend modified: $path"
  done < <(git -C "$backend_root" status --porcelain 2>/dev/null)
fi
note "backend_tracked_dirty=$backend_dirty backend_untracked=$backend_untracked"
[ "$backend_dirty" != "0" ] && bad "backend has $backend_dirty modified tracked path(s); the runtime is not $backend_sha"
[ "$backend_untracked" != "0" ] && note "WARN: $backend_untracked untracked backend path(s); they can change imports and test collection"

# Collections create registry rows at runtime.  With a runtime drive configured,
# it is the explicit mutable authority; Git is the validated baseline and CI
# contract.  Never accept an arbitrary symlink as an acknowledgement shortcut.
runtime_drive="${YZU_RUNTIME_DRIVE_ROOT:-}"
registry_authority="${RESEARCH_REGISTRY_AUTHORITY:-}"
[ -n "$registry_authority" ] || registry_authority=$([ -n "$runtime_drive" ] && echo runtime || echo git)
case "$registry_authority" in
  git|runtime) ;;
  *) bad "unknown RESEARCH_REGISTRY_AUTHORITY=$registry_authority (expected git or runtime)" ;;
esac
note "registry_authority=$registry_authority"

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

# The candidate static directory must be a complete release.  Its directory
# name is intentionally not just the UI SHA: one UI commit may be staged with
# multiple backend commits, and those pair identities must never overwrite one
# another (including the currently-live release).
if [ -n "$public_root" ] && [ -n "$static_dir" ]; then
  candidate_static="$(readlink -f "$static_dir" 2>/dev/null || true)"
  [ -f "$candidate_static/index.html" ] || bad "candidate static release is incomplete: ${candidate_static:-$static_dir}"
  case "$candidate_static" in
    "$public_root"/releases/*) ;;
    *) bad "candidate static release is outside $public_root/releases: ${candidate_static:-$static_dir}" ;;
  esac
fi

reg_abs="$registry"; case "$reg_abs" in /*) ;; *) reg_abs="$backend_root/$registry";; esac
if [ "$registry_authority" = "runtime" ]; then
  [ -n "$runtime_drive" ] || bad "runtime registry authority requires YZU_RUNTIME_DRIVE_ROOT"
  expected_runtime_registry="$(readlink -f "$runtime_drive/config/research_query_registry.json" 2>/dev/null || true)"
  actual_runtime_registry="$(readlink -f "$reg_abs" 2>/dev/null || true)"
  [ -n "$expected_runtime_registry" ] || bad "runtime registry missing: $runtime_drive/config/research_query_registry.json"
  [ "$actual_runtime_registry" = "$expected_runtime_registry" ] || bad "runtime registry target mismatch: expected $expected_runtime_registry, got ${actual_runtime_registry:-absent}"
  [ -L "$reg_abs" ] || bad "runtime registry must be linked, not copied: $reg_abs"
elif [ "$registry_typechange" = "1" ] || [ -L "$reg_abs" ]; then
  bad "Git registry authority requires a regular tracked registry, not a symlink: $reg_abs"
fi
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

composer_provider="${DESK_COMPOSER_PROVIDER:-auto}"
if [ "$composer_provider" = "copilot" ] || [ "$composer_provider" = "github_copilot" ] || [ "$composer_provider" = "copilot_composer" ]; then
  copilot_probe="$backend_root/drive/scripts/research_data_mcp/copilot_pool_preflight.py"
  if [ ! -f "$copilot_probe" ]; then
    bad "Copilot pool preflight is missing: $copilot_probe"
  elif copilot_result="$(PYTHONPATH="$backend_root:$backend_root/kernel:$backend_root/drive:$backend_root/alpha" "$python_bin" "$copilot_probe" 2>&1)"; then
    while IFS= read -r line; do note "copilot: $line"; done <<<"$copilot_result"
  else
    bad "Copilot provider preflight failed"
    while IFS= read -r line; do note "copilot: $line"; done <<<"$copilot_result"
  fi
fi

if [ "${PREFLIGHT_CHECK_RESTARTABILITY:-0}" = "1" ]; then
  restart_probe="${PREFLIGHT_RESTARTABILITY_SCRIPT:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/verify_front_door_restartability.sh}"
  if [ ! -f "$restart_probe" ]; then
    bad "restartability probe missing: $restart_probe"
  elif FRONT_DOOR_ENV="$ENV_FILE" bash "$restart_probe" --check >/tmp/restartability_preflight.$$ 2>&1; then
    note "restartability=ready"
  else
    bad "restartability preflight failed"
    while IFS= read -r line; do note "restartability: $line"; done </tmp/restartability_preflight.$$
  fi
  rm -f /tmp/restartability_preflight.$$
fi

if [ "$JSON" = "1" ]; then
  "$python_bin" - "$backend_sha" "$ui_sha" "$reg_hash" "$reg_rows" "$roots" "$fail" "$registry_authority" <<'PY'
import json,sys
b,u,h,r,roots,fail,authority=sys.argv[1:8]
print(json.dumps({"ready": fail=="0","backend_sha":b,"ui_sha":u,
                  "registry_sha256_16":h,"registry_rows":int(r),"data_roots":roots,
                  "registry_authority":authority}, indent=2))
PY
else
  echo "backend_sha   $backend_sha"
  echo "ui_sha        $ui_sha"
  echo "registry      $reg_rows rows, sha256:$reg_hash"
  echo "registry_mode $registry_authority"
  echo "data_roots    $roots"
  for n in "${notes[@]:-}"; do [ -n "$n" ] && echo "  $n"; done
  [ "$fail" = "0" ] && echo "READY — safe to promote" || echo "NOT READY — do not touch the live service"
fi
exit "$fail"
