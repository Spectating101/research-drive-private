#!/usr/bin/env bash
# Rebuild ChatGPT upload zips from existing screenshots + markdown (no Playwright).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$ROOT"

SHOT_DIR="docs/screenshots-review"
if [[ ! -f "${SHOT_DIR}/manifest.json" ]]; then
  echo "Missing ${SHOT_DIR}/manifest.json — run: npm run desk:capture:live" >&2
  exit 1
fi

rm -f research-drive-screenshots.zip research-drive-chatgpt-packet.zip
zip -qr research-drive-screenshots.zip "${SHOT_DIR}"

ENTRIES=("${SHOT_DIR}")
for doc in \
  docs/DISCOVER_ACQUISITION.md \
  docs/status/generated/CHATGPT_REVIEW_PACKET.md \
  docs/status/generated/professor_demo_report.md \
  docs/status/generated/professor_demo_report.json \
  docs/PROFESSOR_DEMO_SCRIPT.md; do
  [[ -f "$doc" ]] && ENTRIES+=("$doc")
done
zip -qr research-drive-chatgpt-packet.zip "${ENTRIES[@]}"

echo "Wrote research-drive-screenshots.zip ($(du -h research-drive-screenshots.zip | cut -f1))"
echo "Wrote research-drive-chatgpt-packet.zip ($(du -h research-drive-chatgpt-packet.zip | cut -f1))"
echo ""
echo "Upload to ChatGPT: research-drive-chatgpt-packet.zip"
unzip -l research-drive-chatgpt-packet.zip | grep -E 'discover-acquire|discover-probe|discover-ask|CHATGPT|DISCOVER|professor_demo' | head -15
