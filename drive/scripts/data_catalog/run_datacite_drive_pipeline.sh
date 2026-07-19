#!/usr/bin/env bash
set -u

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${repo_root}"

while true; do
  if ! "${repo_root}/scripts/data_catalog/upload_datacite_local_to_drive.sh"; then
    printf '%s stage=backlog_upload status=failed retry_seconds=60\n' "$(date -Iseconds)" >&2
    sleep 60
    continue
  fi

  printf '%s stage=continuous_pull status=starting\n' "$(date -Iseconds)"
  "${repo_root}/scripts/data_catalog/pull_datacite_cluster_shards.sh"
  exit_code=$?
  printf '%s stage=continuous_pull status=stopped exit=%s retry_seconds=60\n' \
    "$(date -Iseconds)" "${exit_code}" >&2
  sleep 60
done
