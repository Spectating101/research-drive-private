#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs/news_shock_taxonomy

if [[ "${NEWS_SHOCK_DOC_AUTO_ENABLE:-0}" != "1" ]]; then
  echo "$(date -Is) NEWS_SHOCK_DOC_AUTO_ENABLE is not 1; skipping automatic GDELT DOC URL enrichment"
  echo "$(date -Is) Use the GKG pipeline or run this script with NEWS_SHOCK_DOC_AUTO_ENABLE=1 after confirming API budget"
  exit 0
fi

HEADLINE_SERVICE="news-shock-headline-backfill.service"

while true; do
  state="$(systemctl --user show "${HEADLINE_SERVICE}" -p ActiveState --value 2>/dev/null || echo inactive)"
  result="$(systemctl --user show "${HEADLINE_SERVICE}" -p Result --value 2>/dev/null || echo success)"
  if [[ "${state}" == "inactive" && "${result}" == "success" ]]; then
    break
  fi
  echo "$(date -Is) waiting for ${HEADLINE_SERVICE}: state=${state} result=${result}"
  sleep 900
done

python3 scripts/news_shock_taxonomy/enrich_gdelt_doc_urls_drive.py "$@" \
  2>&1 | tee -a logs/news_shock_taxonomy/gdelt_doc_url_enrichment.log
