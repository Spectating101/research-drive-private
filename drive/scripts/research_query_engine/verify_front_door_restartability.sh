#!/usr/bin/env bash
# Prove that the Research Drive front door can survive a process restart.
#
# --check     read-only: unit/env/linger/live HTTP/session contract
# --exercise  restart the unit, then prove identity, state continuity, and the
#             first authenticated Discover query. Use after promotion.
set -euo pipefail

mode="${1:---check}"
case "$mode" in
  --check|--exercise) ;;
  *) echo "usage: $0 [--check|--exercise]" >&2; exit 2 ;;
esac

env_file="${FRONT_DOOR_ENV:-$HOME/.config/research-drive/front-door.env}"
unit="${FRONT_DOOR_SERVICE_UNIT:-research-drive-front-door.service}"
max_wait="${RESTARTABILITY_MAX_WAIT_SECONDS:-45}"
max_search="${RESTARTABILITY_COLD_SEARCH_MAX_SECONDS:-8}"

for command in systemctl loginctl curl python3 git stat sha256sum; do
  command -v "$command" >/dev/null 2>&1 || { echo "missing command: $command" >&2; exit 2; }
done
[ -f "$env_file" ] || { echo "front-door env missing: $env_file" >&2; exit 2; }

mode_bits="$(stat -c '%a' "$env_file")"
case "$mode_bits" in
  *00) ;;
  *) echo "front-door env must not be readable by group/other (mode $mode_bits)" >&2; exit 1 ;;
esac

set +u
# shellcheck disable=SC1090
set -a; . "$env_file"; set +a
set -u

host="${YZU_DESK_HOST:?YZU_DESK_HOST is required}"
port="${YZU_DESK_PORT:-8765}"
base="http://${host}:${port}"
backend_root="${SHARPE_REPO_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)}"
registry="${SHARPE_REGISTRY_PATH:-config/research_query_registry.json}"
case "$registry" in /*) registry_abs="$registry" ;; *) registry_abs="$backend_root/$registry" ;; esac

enabled="$(systemctl --user is-enabled "$unit" 2>/dev/null || true)"
[ "$enabled" = "enabled" ] || { echo "unit is not enabled: $unit ($enabled)" >&2; exit 1; }
restart_policy="$(systemctl --user show "$unit" -p Restart --value)"
case "$restart_policy" in on-failure|always|on-abnormal|on-watchdog) ;; *)
  echo "unit has no recovery restart policy: $restart_policy" >&2; exit 1 ;;
esac
linger="$(loginctl show-user "$USER" -p Linger --value 2>/dev/null || printf unknown)"
[ "$linger" = "yes" ] || { echo "user linger is not enabled: $linger" >&2; exit 1; }

cookie_jar="$(mktemp)"
body_file="$(mktemp)"
trap 'rm -f "$cookie_jar" "$body_file"' EXIT

wait_for_health() {
  local elapsed=0
  while [ "$elapsed" -lt "$max_wait" ]; do
    if curl -fsS --max-time 2 "$base/healthz" >"$body_file" 2>/dev/null &&
       python3 - "$body_file" <<'PY' >/dev/null 2>&1
import json,sys
assert json.load(open(sys.argv[1])).get("status") == "ok"
PY
    then return 0; fi
    sleep 1
    elapsed=$((elapsed+1))
  done
  echo "healthz did not recover within ${max_wait}s" >&2
  return 1
}

open_session() {
  : >"$cookie_jar"
  curl -fsS --max-time 8 \
    -c "$cookie_jar" \
    -H "Origin: $base" \
    -H "Referer: $base/" \
    -H "Content-Type: application/json" \
    -d '{}' "$base/library/desk/session" >"$body_file"
  python3 - "$body_file" <<'PY' >/dev/null
import json,sys
p=json.load(open(sys.argv[1]))
assert p.get("authorized") is True, p
PY
}

dataset_count() {
  curl -fsS --max-time 15 -b "$cookie_jar" "$base/datasets" >"$body_file"
  python3 - "$body_file" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
rows=p.get("datasets") if isinstance(p,dict) else None
assert isinstance(rows,list), p
print(len(rows))
PY
}

registry_fingerprint() {
  [ -f "$registry_abs" ] || { echo absent; return; }
  sha256sum "$(readlink -f "$registry_abs")" | awk '{print $1}'
}

wait_for_health
open_session
before_count="$(dataset_count)"
before_registry="$(registry_fingerprint)"

if [ "$mode" = "--exercise" ]; then
  systemctl --user restart "$unit"
  wait_for_health
  open_session
fi

observed_ui=""
observed_backend=""
identity_available=0
# A legacy serving release may predate immutable build identities, in which
# case the SPA returns index.html for this path.  That must not prevent a
# read-only pre-promotion health check of a staged, identified candidate.  A
# real restart exercise remains strict: once promoted, the running release
# must prove its pair identity.
identity_lines=""
if curl -fsS --max-time 8 "$base/research-drive-build.json" >"$body_file" 2>/dev/null &&
  identity_lines="$(python3 - "$body_file" 2>/dev/null <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
public=str(p.get("public_sha") or "")
private=str(p.get("private_sha") or "")
if not public or not private:
    raise SystemExit(1)
print(public)
print(private)
PY
 )"; then
  mapfile -t observed_shas <<<"$identity_lines"
  observed_ui="${observed_shas[0]:-}"
  observed_backend="${observed_shas[1]:-}"
  if [ -n "$observed_ui" ] && [ -n "$observed_backend" ]; then
    identity_available=1
  fi
fi
if [ "$mode" = "--exercise" ] && [ "$identity_available" != "1" ]; then
  echo "restarted release did not expose a complete build identity" >&2
  exit 1
fi

after_count="$(dataset_count)"
after_registry="$(registry_fingerprint)"
[ "$after_count" = "$before_count" ] || {
  echo "dataset count changed across restart: $before_count -> $after_count" >&2; exit 1;
}
[ "$after_registry" = "$before_registry" ] || {
  echo "registry fingerprint changed across restart" >&2; exit 1;
}

search_metrics="$(curl -fsS --max-time "$((max_search + 4))" -b "$cookie_jar" \
  -G --data-urlencode 'q=stablecoin' --data-urlencode 'limit=3' \
  -o "$body_file" -w '%{time_total} %{http_code}' "$base/library/discover")"
search_seconds="${search_metrics%% *}"
search_code="${search_metrics##* }"
[ "$search_code" = "200" ] || { echo "cold Discover returned HTTP $search_code" >&2; exit 1; }
python3 - "$body_file" <<'PY' >/dev/null
import json,sys
p=json.load(open(sys.argv[1]))
rows=[]
for section in p.get("sections") or []:
    rows.extend(section.get("rows") or [])
rows = rows or p.get("results") or p.get("hits") or []
assert rows, "cold Discover returned no stablecoin evidence"
PY
python3 - "$search_seconds" "$max_search" <<'PY'
import sys
actual=float(sys.argv[1]); limit=float(sys.argv[2])
assert actual <= limit, f"cold Discover took {actual:.3f}s (limit {limit:.3f}s)"
PY

if [ "$mode" = "--exercise" ]; then
  expected_ui="${YZU_PUBLIC_SHA:-}"
  expected_backend="$(git -C "$backend_root" rev-parse HEAD)"
  [ "$observed_ui" = "$expected_ui" ] || {
    echo "restarted UI $observed_ui != expected $expected_ui" >&2; exit 1;
  }
  [ "$observed_backend" = "$expected_backend" ] || {
    echo "restarted backend $observed_backend != checkout $expected_backend" >&2; exit 1;
  }
fi

active="$(systemctl --user is-active "$unit" 2>/dev/null || true)"
[ "$active" = "active" ] || { echo "unit is not active after verification: $active" >&2; exit 1; }
nrestarts="$(systemctl --user show "$unit" -p NRestarts --value)"

echo "restartability=ready mode=${mode#--}"
echo "unit=$unit enabled=$enabled active=$active restart_policy=$restart_policy linger=$linger nrestarts=$nrestarts"
if [ "$identity_available" = "1" ]; then
  echo "identity=${observed_ui}--${observed_backend}"
else
  echo "identity=legacy-unavailable (acceptable only before promotion)"
fi
echo "state=datasets:$after_count registry_sha256:${after_registry:0:16}"
printf 'cold_discover_seconds=%.3f limit=%s\n' "$search_seconds" "$max_search"
