#!/usr/bin/env bash
# Promote a staged front-door release to live.
#
# Building no longer publishes. build_optiplex_front_door.sh writes a complete
# release into releases/<public_sha>--<private_sha>/ and stops. This script is the only thing
# that changes what users see, by re-pointing the `dist` symlink.
#
# The swap is atomic (mv -T over a symlink), so there is no window where the
# served bundle is half-old and half-new. A rollback must restore the staged
# UI/backend pair's matching checkout and environment pins, promote it, and
# restart the service; flipping only the static link is not a complete rollback.
#
#   promote_front_door.sh <release_id>     promote that UI/backend pair
#   promote_front_door.sh --list           show staged releases and which is live
#   promote_front_door.sh --current        print the live sha
set -euo pipefail

public_root="${YZU_PUBLIC_REPO:?set YZU_PUBLIC_REPO to the public yzu-cluster checkout}"
public_root="$(cd "${public_root}" && pwd)"
releases_dir="${public_root}/releases"
live_link="${YZU_DESK_STATIC_DIR:-${public_root}/dist}"

current_sha() {
  [[ -L "${live_link}" ]] || { printf 'unlinked\n'; return; }
  basename "$(readlink -f "${live_link}")"
}

case "${1:-}" in
  --current)
    current_sha
    exit 0
    ;;
  --list)
    live="$(current_sha)"
    if [[ ! -d "${releases_dir}" ]]; then
      echo "no releases staged yet: ${releases_dir}" >&2
      exit 1
    fi
    for d in "${releases_dir}"/*/; do
      [[ -d "${d}" ]] || continue
      sha="$(basename "${d}")"
      built="$(python3 -c "
import json,sys
try: print(json.load(open('${d}research-drive-build.json'))['built_at_utc'])
except Exception: print('?')" 2>/dev/null || echo '?')"
      marker="        "
      [[ "${sha}" == "${live}" ]] && marker=" << LIVE"
      printf '  %s  %s%s\n' "${sha:0:12}" "${built}" "${marker}"
    done
    exit 0
    ;;
  "")
    echo "usage: promote_front_door.sh <release_id> | --list | --current" >&2
    exit 2
    ;;
esac

target_ref="$1"
target_dir="${releases_dir}/${target_ref}"
if [[ ! -d "${target_dir}" ]]; then
  matches=("${releases_dir}/${target_ref}"--*)
  if [[ ${#matches[@]} -eq 1 && -d "${matches[0]}" ]]; then
    target_dir="${matches[0]}"
  elif [[ ${#matches[@]} -gt 1 ]]; then
    echo "multiple UI/backend pairs match ${target_ref}; use the full release_id from --list" >&2
    exit 1
  fi
fi
target_id="$(basename "${target_dir}")"

[[ -d "${target_dir}" ]] || {
  echo "no staged release for ${target_ref}" >&2
  echo "stage one first with build_optiplex_front_door.sh" >&2
  exit 1
}
[[ -f "${target_dir}/index.html" ]] || {
  echo "staged release is incomplete (no index.html): ${target_dir}" >&2
  exit 1
}
[[ -f "${target_dir}/research-drive-build.json" ]] || {
  echo "staged release has no build identity: ${target_dir}" >&2
  exit 1
}

# The identity must describe the release it sits in, or the desk server's own
# SHA gate will reject it after promotion.
python3 - "${target_dir}/research-drive-build.json" "${target_id}" <<'PY'
import json, sys
payload = json.loads(open(sys.argv[1], encoding="utf-8").read())
public_sha = str(payload.get("public_sha") or "")
private_sha = str(payload.get("private_sha") or "")
expected_id = f"{public_sha}--{private_sha}"
if sys.argv[2] != expected_id and sys.argv[2] != public_sha:
    raise SystemExit(
        f"staged identity pair {expected_id} != release dir {sys.argv[2]}"
    )
print("staged_identity_ok")
PY

previous="$(current_sha)"

# A promotion that is not preflighted is how the desk went down twice on 2026-08-18: the
# run script enforces its guards after systemd has already stopped the old process, so a
# mismatch becomes a restart loop instead of a refusal. Gate here, before the swap.
preflight="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/preflight_release.sh"
if [[ "${PROMOTE_SKIP_PREFLIGHT:-0}" == "1" ]]; then
  echo "preflight=skipped (PROMOTE_SKIP_PREFLIGHT=1)" >&2
elif [[ -x "${preflight}" || -f "${preflight}" ]]; then
  if PREFLIGHT_STATIC_DIR="${target_dir}" bash "${preflight}" >/tmp/promote_preflight.$$ 2>&1; then
    echo "preflight=ready"
  else
    echo "preflight refused this release; not swapping the live link" >&2
    sed 's/^/  /' /tmp/promote_preflight.$$ >&2
    rm -f /tmp/promote_preflight.$$
    echo "override with PROMOTE_SKIP_PREFLIGHT=1 only when you know why" >&2
    exit 1
  fi
  rm -f /tmp/promote_preflight.$$
else
  echo "preflight script absent at ${preflight}; refusing to promote blind" >&2
  exit 1
fi

if [[ -e "${live_link}" && ! -L "${live_link}" ]]; then
  echo "refusing to replace a real directory at ${live_link}" >&2
  echo "run migrate_front_door_releases.sh once to convert it to a symlink" >&2
  exit 1
fi

# Atomic: build the new link beside the old one, then rename over it.
tmp_link="${live_link}.promoting.$$"
ln -s "${target_dir}" "${tmp_link}"
mv -Tf "${tmp_link}" "${live_link}"

printf 'promoted=%s\n' "${target_id}"
printf 'previous=%s\n' "${previous}"
if [[ "${previous}" != "unlinked" ]]; then
  printf 'rollback_candidate=%s\n' "${previous}"
  printf 'rollback_note=restore this candidate matching UI/backend checkout and environment pins, run preflight, promote, then restart the service\n'
fi
