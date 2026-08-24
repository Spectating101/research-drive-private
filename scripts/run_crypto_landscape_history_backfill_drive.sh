#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs/crypto_landscape_history_backfill

python3 scripts/backfill_crypto_landscape_history_drive.py "$@" \
  2>&1 | tee -a logs/crypto_landscape_history_backfill/backfill.log
