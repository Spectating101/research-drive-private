#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
window="${1:?window directory name required}"
remote_root="${2:?Drive normalized root required}"
staging="${repo_root}/data_lake/news_shock_taxonomy/staging/gdelt_crypto_overlay/${window}"
source_file="${staging}/asia_gkg_filtered.csv.gz"
output_root="${repo_root}/data_lake/news_shock_taxonomy/derived/gdelt_crypto_overlay"

mkdir -p "$staging"
cleanup() { rm -rf "$staging"; }
trap cleanup EXIT

rclone copyto "${remote_root}/${window}/asia_gkg_filtered.csv.gz" "$source_file" --retries 5 --low-level-retries 10
gzip -t "$source_file"
nice -n 10 ionice -c3 python3 "${repo_root}/scripts/news_shock_taxonomy/build_gdelt_crypto_overlay.py" \
  --source-file "$source_file" \
  --window-name "$window" \
  --out-dir "$output_root"

