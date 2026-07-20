#!/usr/bin/env bash
# Link drive/config authority files into repo-root config/ for the Optiplex front door.
#
# Clean private tips keep registry/queue JSON under drive/config/, but several desk
# paths still open config/<name>.json from the repo root. This helper makes that
# host layout explicit instead of ad-hoc operator recovery.
#
# Also preserve (do not overwrite) a host-local data_lake/yzu_cluster job-store
# symlink when present — that points at the production job queue, not drive/config.
#
# Usage:
#   bash drive/scripts/research_query_engine/link_front_door_host_config.sh
#   bash drive/scripts/research_query_engine/link_front_door_host_config.sh --dry-run
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
dry_run=0
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=1
elif [[ -n "${1:-}" ]]; then
  echo "usage: $0 [--dry-run]" >&2
  exit 2
fi

# Code-referenced config/*.json that must resolve at repo-root config/.
CONFIG_LINKS=(
  collection_partitions.json
  collection_semantic.json
  databank_access_scope.json
  databank_coverage_proxies.json
  databank_source_map.json
  data_collection_queue.json
  desk_demo_catalog.json
  desk_sources.json
  procurement_governance.json
  procurement_magic.json
  procurement_registry_map.json
  research_query_registry.json
  storage_tiers.json
  synthesis_profiles.json
  yzu_cluster.json
)

mkdir -p "${repo_root}/config"
linked=0
skipped=0
missing=0

for name in "${CONFIG_LINKS[@]}"; do
  src="${repo_root}/drive/config/${name}"
  dst="${repo_root}/config/${name}"
  if [[ ! -e "${src}" ]]; then
    printf 'missing_source=%s\n' "${src}"
    missing=$((missing + 1))
    continue
  fi
  if [[ -L "${dst}" ]]; then
    current="$(readlink "${dst}")"
    if [[ "${current}" == "../drive/config/${name}" || "${current}" == "${src}" ]]; then
      printf 'ok_link=%s\n' "${name}"
      skipped=$((skipped + 1))
      continue
    fi
  elif [[ -e "${dst}" ]]; then
    printf 'skip_existing_file=%s\n' "${name}"
    skipped=$((skipped + 1))
    continue
  fi
  if [[ "${dry_run}" == "1" ]]; then
    printf 'would_link=%s -> ../drive/config/%s\n' "${name}" "${name}"
  else
    ln -sfn "../drive/config/${name}" "${dst}"
    printf 'linked=%s\n' "${name}"
  fi
  linked=$((linked + 1))
done

# Optional: bind front-door checkout to the runtime-integration authority store.
# Worker promotions write registry + procured bytes there; without this link the
# desk serves a stale registry (receipt_only) even after a successful collect.
runtime_drive="${YZU_RUNTIME_DRIVE_ROOT:-}"
runtime_linked=0
runtime_skipped=0
if [[ -n "${runtime_drive}" ]]; then
  runtime_drive="$(cd "${runtime_drive}" && pwd)"
  declare -a RUNTIME_BINDS=(
    "config/research_query_registry.json:drive/config/research_query_registry.json"
    "data_lake/procured:data_lake/procured"
    "data_lake/yzu_cluster:data_lake/yzu_cluster"
  )
  mkdir -p "${repo_root}/drive/config" "${repo_root}/data_lake"
  for spec in "${RUNTIME_BINDS[@]}"; do
    rel_src="${spec%%:*}"
    rel_dst="${spec##*:}"
    src="${runtime_drive}/${rel_src}"
    dst="${repo_root}/${rel_dst}"
    if [[ ! -e "${src}" ]]; then
      printf 'runtime_missing_source=%s\n' "${src}"
      missing=$((missing + 1))
      continue
    fi
    mkdir -p "$(dirname "${dst}")"
    if [[ -L "${dst}" ]]; then
      current="$(readlink "${dst}")"
      if [[ "${current}" == "${src}" ]]; then
        printf 'ok_runtime_link=%s\n' "${rel_dst}"
        runtime_skipped=$((runtime_skipped + 1))
        continue
      fi
    elif [[ -e "${dst}" && ! -L "${dst}" ]]; then
      # Replace regular registry file with authority symlink; leave other dirs alone.
      if [[ "${rel_dst}" == "drive/config/research_query_registry.json" ]]; then
        if [[ "${dry_run}" == "1" ]]; then
          printf 'would_replace_runtime_link=%s -> %s\n' "${rel_dst}" "${src}"
        else
          rm -f "${dst}"
          ln -sfn "${src}" "${dst}"
          printf 'runtime_replaced=%s\n' "${rel_dst}"
        fi
        runtime_linked=$((runtime_linked + 1))
        continue
      fi
      printf 'skip_runtime_existing=%s\n' "${rel_dst}"
      runtime_skipped=$((runtime_skipped + 1))
      continue
    fi
    if [[ "${dry_run}" == "1" ]]; then
      printf 'would_runtime_link=%s -> %s\n' "${rel_dst}" "${src}"
    else
      ln -sfn "${src}" "${dst}"
      printf 'runtime_linked=%s\n' "${rel_dst}"
    fi
    runtime_linked=$((runtime_linked + 1))
  done
fi

printf 'repo_root=%s\n' "${repo_root}"
printf 'linked=%s skipped=%s missing_source=%s dry_run=%s\n' "${linked}" "${skipped}" "${missing}" "${dry_run}"
printf 'runtime_linked=%s runtime_skipped=%s runtime_drive=%s\n' "${runtime_linked}" "${runtime_skipped}" "${runtime_drive:-unset}"
if [[ "${missing}" -gt 0 ]]; then
  exit 1
fi
