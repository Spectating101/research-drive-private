#!/usr/bin/env bash
# One-time: convert the served `dist` directory into a symlink onto
# releases/<public_sha>/, so promotion becomes an atomic, reversible act.
#
# Run once. Afterwards, build stages and promote_front_door.sh publishes.
#
# The currently-live bundle is preserved as a release directory first, so this
# changes how the bytes are addressed, never which bytes are served.
set -euo pipefail

public_root="${YZU_PUBLIC_REPO:?set YZU_PUBLIC_REPO to the public yzu-cluster checkout}"
public_root="$(cd "${public_root}" && pwd)"
releases_dir="${public_root}/releases"
live_link="${YZU_DESK_STATIC_DIR:-${public_root}/dist}"
probe_url="${YZU_DESK_PROBE_URL:-}"

if [[ -L "${live_link}" ]]; then
  echo "already migrated: ${live_link} -> $(readlink -f "${live_link}")"
  exit 0
fi
[[ -d "${live_link}" ]] || { echo "nothing to migrate: ${live_link} is not a directory" >&2; exit 1; }
[[ -f "${live_link}/index.html" ]] || { echo "refusing: ${live_link}/index.html missing" >&2; exit 1; }

identity="${live_link}/research-drive-build.json"
[[ -f "${identity}" ]] || { echo "refusing: no build identity in ${live_link}" >&2; exit 1; }
live_sha="$(python3 -c "import json;print(json.load(open('${identity}'))['public_sha'])")"
[[ -n "${live_sha}" ]] || { echo "refusing: build identity has no public_sha" >&2; exit 1; }

mkdir -p "${releases_dir}"
target="${releases_dir}/${live_sha}"
if [[ ! -d "${target}" ]]; then
  cp -a "${live_link}" "${target}"
  echo "preserved live bundle as ${target}"
fi
[[ -f "${target}/index.html" ]] || { echo "copy incomplete: ${target}" >&2; exit 1; }

backup="${live_link}.pre-symlink.$(date -u +%Y%m%dT%H%M%SZ)"
mv -T "${live_link}" "${backup}"
if ! ln -s "${target}" "${live_link}"; then
  mv -T "${backup}" "${live_link}"
  echo "symlink failed; restored the original directory" >&2
  exit 1
fi

# Prove the live site still serves before keeping the new arrangement.
if [[ -n "${probe_url}" ]]; then
  code="$(curl -s -m 15 -o /dev/null -w '%{http_code}' "${probe_url}" || echo 000)"
  if [[ "${code}" != "200" ]]; then
    rm -f "${live_link}"
    mv -T "${backup}" "${live_link}"
    echo "probe returned ${code}; reverted to the original directory" >&2
    exit 1
  fi
  echo "probe_ok=${code}"
fi

echo "migrated=${live_link} -> ${target}"
echo "kept_backup=${backup}"
echo "remove the backup once you are satisfied: rm -rf ${backup}"
