#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_root="${repo_root}/data_lake/news_shock_taxonomy/derived/gdelt_crypto_overlay"
state_dir="${output_root}/queue_state"
old_root="gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/news/gdelt-asia/gdelt_gkg_asia_backfill_2018_2023/normalized/gdelt_gkg_asia_bulk"
new_root="gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/collection/news/gdelt-asia/normalized/gdelt_gkg_asia_bulk"
mkdir -p "$state_dir"

inventory="$(mktemp)"
queue="$(mktemp)"
trap 'rm -f "$inventory" "$queue"' EXIT

for root in "$old_root" "$new_root"; do
  rclone lsf "$root" --files-only --recursive --include "asia_gkg_window_*/asia_gkg_filtered.csv.gz" --format p |
    while IFS= read -r path; do
      window="${path%%/*}"
      if [[ "$window" =~ ^asia_gkg_window_([0-9]{8})_([0-9]{8})_ ]]; then
        printf '%s|%s|%s\n' "${BASH_REMATCH[1]}" "$root" "$window"
      fi
    done
done > "$inventory"

# Prefer the last archive occurrence for duplicate monthly ranges.
sort -t'|' -k1,1 -k3,3 "$inventory" | awk -F'|' '{ latest[$1]=$0 } END { for (k in latest) print latest[k] }' |
  sort -t'|' -k1,1 > "$queue"

total="$(wc -l < "$queue")"
printf '%s\n' "$total" > "$state_dir/total_months.txt"
completed=0

while IFS='|' read -r month root window; do
  summary="${output_root}/${window}/summary.json"
  if [[ -s "$summary" ]] && grep -q '"status": "complete"' "$summary"; then
    completed=$((completed + 1))
    continue
  fi

  printf '%s|%s|%s|%s\n' "$(date -Iseconds)" "$completed" "$total" "$window" > "$state_dir/current.txt"
  "${repo_root}/scripts/news_shock_taxonomy/run_gdelt_crypto_overlay_drive_month.sh" "$window" "$root"
  completed=$((completed + 1))
  printf '%s\n' "$completed" > "$state_dir/completed_months.txt"
done < "$queue"

printf '%s|%s|%s|complete\n' "$(date -Iseconds)" "$completed" "$total" > "$state_dir/current.txt"

