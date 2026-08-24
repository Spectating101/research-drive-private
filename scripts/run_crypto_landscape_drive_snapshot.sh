#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs

python3 scripts/fetch_crypto_landscape_drive.py "$@" 2>&1 | tee -a logs/crypto_landscape_drive_daily.log
