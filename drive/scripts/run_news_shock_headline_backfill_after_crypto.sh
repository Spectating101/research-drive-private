#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs/news_shock_taxonomy

if [[ "${NEWS_SHOCK_DOC_AUTO_ENABLE:-0}" != "1" ]]; then
  echo "$(date -Is) NEWS_SHOCK_DOC_AUTO_ENABLE is not 1; skipping automatic GDELT DOC headline backfill"
  echo "$(date -Is) Use the GKG pipeline or run this script with NEWS_SHOCK_DOC_AUTO_ENABLE=1 after confirming API budget"
  exit 0
fi

CRYPTO_SERVICE="crypto-landscape-history-backfill.service"

while true; do
  state="$(systemctl --user show "${CRYPTO_SERVICE}" -p ActiveState --value 2>/dev/null || echo inactive)"
  result="$(systemctl --user show "${CRYPTO_SERVICE}" -p Result --value 2>/dev/null || echo success)"
  if [[ "${state}" == "inactive" && "${result}" == "success" ]]; then
    break
  fi
  echo "$(date -Is) waiting for ${CRYPTO_SERVICE}: state=${state} result=${result}"
  sleep 900
done

python3 scripts/news_shock_taxonomy/backfill_gdelt_doc_headlines_drive.py "$@" \
  2>&1 | tee -a logs/news_shock_taxonomy/gdelt_doc_headline_backfill.log
