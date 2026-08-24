#!/usr/bin/env bash
# Full desk hardening prove — unit + SHA + live hostile (when desk up).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT:$ROOT/kernel:$ROOT/drive${PYTHONPATH:+:$PYTHONPATH}"

echo "== unit =="
RESEARCH_DRIVE_SKIP_SHA_GATE=1 /usr/bin/python3 -m pytest -q \
  drive/tests/test_craft_collect.py \
  drive/tests/test_network_policy.py \
  drive/tests/test_faculty_profile_regressions.py \
  drive/tests/test_hardening_gates.py \
  drive/tests/test_invariant_inventory.py \
  tests/test_desk_auth_session.py \
  tests/test_acquisition_manifest.py

echo "== sha =="
bash drive/scripts/research_query_engine/prove_front_door_sha.sh

HOST="${YZU_DESK_HOST:-100.127.141.44}"
PORT="${YZU_DESK_PORT:-8765}"
BASE="http://${HOST}:${PORT}"
TOKEN_FILE="${YZU_DESK_TOKEN_FILE:-$HOME/.config/research-drive/front-door.desk-token}"
if [[ ! -f "$TOKEN_FILE" ]]; then
  echo "SKIP live: no token file"
  exit 0
fi
TOKEN="$(cat "$TOKEN_FILE")"
AUTH="Authorization: Bearer ${TOKEN}"

echo "== live health =="
curl -fsS "$BASE/healthz" >/dev/null

echo "== live unauth write =="
code="$(curl -sS -o /tmp/rd_unauth.json -w "%{http_code}" -X POST "$BASE/library/jobs" \
  -H "Content-Type: application/json" -d '{"title":"x","plan":{"job_type":"http_manifest"}}' || true)"
[[ "$code" == "401" ]] || { echo "FAIL expected 401 got $code"; cat /tmp/rd_unauth.json; exit 1; }

echo "== live cgnat =="
code="$(curl -sS -o /tmp/rd_cgnat.json -w "%{http_code}" -X POST "$BASE/library/jobs" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"cgnat","plan":{"job_type":"http_manifest","url":"http://100.64.0.1/x","items":[{"url":"http://100.64.0.1/x"}],"destination":"data_lake/procured/x","launchable":true}}')"
[[ "$code" == "400" ]] || { echo "FAIL cgnat $code"; cat /tmp/rd_cgnat.json; exit 1; }

echo "== live auto_approve force pending =="
code="$(curl -sS -o /tmp/rd_aa.json -w "%{http_code}" -X POST "$BASE/library/jobs" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"aa","auto_approve":true,"plan":{"job_type":"http_manifest","url":"https://api.github.com/zen","items":[{"url":"https://api.github.com/zen","filename":"zen.txt"}],"destination":"data_lake/procured/aa_prove","dataset_id":"aa_prove","launchable":true}}')"
[[ "$code" == "200" ]] || { echo "FAIL aa $code"; cat /tmp/rd_aa.json; exit 1; }
status="$(/usr/bin/python3 -c 'import json;print((json.load(open("/tmp/rd_aa.json")).get("job") or {}).get("status"))')"
jid="$(/usr/bin/python3 -c 'import json;print((json.load(open("/tmp/rd_aa.json")).get("job") or {}).get("id") or "")')"
[[ "$status" == "pending_approval" ]] || { echo "FAIL status=$status"; exit 1; }
[[ -n "$jid" ]] && curl -fsS -X POST "$BASE/library/jobs/$jid/cancel" -H "$AUTH" >/dev/null || true

echo "OK hardening prove complete"
