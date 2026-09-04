# Research Drive backend host release runbook — 2026-09-04

**Audience:** operator performing staging/promotion on the Research Drive host  
**Safety posture:** fail closed; do not promote when any preflight or identity check fails

This runbook begins where repository CI ends. It is for proving the final UI/backend pair on the real host.

## 0. Inputs to freeze before touching the host

Record these values in the acceptance document before deployment:

```text
BACKEND_SHA=<final PR #61 head after documentation CI is green>
FRONTEND_SHA=<final chosen yzu-cluster release SHA>
BACKEND_REPO=<absolute private checkout path>
FRONTEND_REPO=<absolute public yzu-cluster checkout path>
FRONT_DOOR_ENV=$HOME/.config/research-drive/front-door.env
SERVICE_UNIT=research-drive-front-door.service
```

Do not proceed with a branch name as the release identity. Use exact commit SHAs.

## 1. Preserve the current live release

Before changing checkouts or environment pins:

```bash
export FRONT_DOOR_ENV="$HOME/.config/research-drive/front-door.env"
set +u
set -a; . "$FRONT_DOOR_ENV"; set +a
set -u

bash drive/scripts/research_query_engine/promote_front_door.sh --current
bash drive/scripts/research_query_engine/promote_front_door.sh --list
systemctl --user status research-drive-front-door.service --no-pager
```

Record:

```text
PREVIOUS_RELEASE_ID=
PREVIOUS_BACKEND_SHA=
PREVIOUS_FRONTEND_SHA=
PREVIOUS_SERVICE_STATE=
```

Do not delete the previous staged release directory. It is the rollback candidate.

## 2. Verify the backend checkout

From the private repository:

```bash
git fetch --all --prune
git checkout --detach "$BACKEND_SHA"
git rev-parse HEAD
git status --porcelain
```

Expected:

- `git rev-parse HEAD` equals `BACKEND_SHA`;
- no tracked working-tree changes;
- untracked files must be understood before relying on import/test behavior.

If this checkout is intentionally the mutable runtime-integrated tree, preserve its documented runtime links rather than copying mutable registries into Git-owned files.

## 3. Verify the frontend checkout

From the public repository:

```bash
git fetch --all --prune
git checkout --detach "$FRONTEND_SHA"
git rev-parse HEAD
git status --porcelain --untracked-files=no
```

Expected:

- exact SHA match;
- no tracked changes.

## 4. Prepare and inspect the host environment

The environment file must remain outside Git.

```bash
stat -c '%a %U:%G %n' "$FRONT_DOOR_ENV"
```

Required permission posture: group/other must not be able to read it; `0600` is the normal target.

Do not print the file contents into evidence. Inspect it locally and verify at minimum:

```text
YZU_PUBLIC_REPO=<FRONTEND_REPO>
YZU_PUBLIC_SHA=<FRONTEND_SHA>
YZU_DESK_HOST=<approved private/Tailscale address>
YZU_DESK_PORT=<approved port, normally 8765>
YZU_DESK_SERVE_UI=true
SHARPE_REGISTRY_PATH=<intended registry path>
YZU_PYTHON_BIN=<python capable of the selected provider/runtime>
```

Where a mutable runtime drive is used, verify:

```text
YZU_RUNTIME_DRIVE_ROOT=<intended runtime drive>
RESEARCH_REGISTRY_AUTHORITY=runtime
```

Where Git is intentionally authoritative, do not leave the registry as an arbitrary runtime symlink.

Authentication must be configured through the intended desk token or named-principal/session authority. Same-origin/CORS is not authentication.

## 5. Link host runtime authority

The launcher performs linking automatically, but execute/inspect the deterministic link step before staging when validating a repaired or new host:

```bash
bash drive/scripts/research_query_engine/link_front_door_host_config.sh
```

Then verify the registry/data-lake targets locally. Do not replace a runtime-owned mutable registry with a stale Git copy merely to make `git status` look clean.

For split front-door/runtime layouts, see `FRONT_DOOR_HOST_REPRODUCIBILITY.md`.

## 6. Verify Python/provider prerequisites

```bash
"${YZU_PYTHON_BIN}" --version
```

For the configured Composer provider, verify that the selected interpreter/launcher is actually usable. A configured key or account alias without an invocable SDK/runtime is not sufficient.

Do not expose provider credentials in evidence.

## 7. Build the exact staged pair

From the backend checkout, after sourcing the host environment:

```bash
set +u
set -a; . "$FRONT_DOOR_ENV"; set +a
set -u

bash drive/scripts/research_query_engine/build_optiplex_front_door.sh
```

The build must end with a staged release, not a live promotion.

Expected release ID:

```text
<FRONTEND_SHA>--<BACKEND_SHA>
```

Expected path:

```text
<FRONTEND_REPO>/releases/<FRONTEND_SHA>--<BACKEND_SHA>/
```

Inspect the build identity without exposing secrets:

```bash
cat "$FRONTEND_REPO/releases/$FRONTEND_SHA--$BACKEND_SHA/research-drive-build.json"
```

Required identity fields:

- `public_repo`;
- `public_sha` = `FRONTEND_SHA`;
- `private_repo`;
- `private_sha` = `BACKEND_SHA`;
- `built_at_utc`;
- `release_scope`.

A successful build does not authorize promotion.

## 8. Read-only release preflight

Point preflight at the staged candidate:

```bash
export PREFLIGHT_STATIC_DIR="$FRONTEND_REPO/releases/$FRONTEND_SHA--$BACKEND_SHA"
export PREFLIGHT_CHECK_RESTARTABILITY=1
bash drive/scripts/research_query_engine/preflight_release.sh
```

For machine-readable evidence:

```bash
bash drive/scripts/research_query_engine/preflight_release.sh --json
```

Required result:

```text
READY — safe to promote
```

or JSON with:

```json
{"ready": true}
```

Preflight validates, among other things:

- backend checkout identity and tracked cleanliness;
- frontend checkout identity and tracked cleanliness;
- staged build identity;
- staged release directory boundary;
- registry ownership mode;
- runtime registry target when configured;
- non-empty registry;
- provider-specific preflight where applicable;
- restartability readiness when enabled.

Any non-zero result is a hard stop.

## 9. Pre-promotion live checks

Verify the existing service remains healthy before changing the live pair:

```bash
bash drive/scripts/research_query_engine/verify_front_door_restartability.sh --check
systemctl --user status research-drive-front-door.service --no-pager
journalctl --user -u research-drive-front-door.service -n 200 --no-pager
```

Record only sanitized service evidence.

## 10. Promote the staged pair

Only after Sections 1–9 are green:

```bash
bash drive/scripts/research_query_engine/promote_front_door.sh \
  "$FRONTEND_SHA--$BACKEND_SHA"
```

Expected output includes:

```text
preflight=ready
promoted=<FRONTEND_SHA>--<BACKEND_SHA>
previous=<previous release id>
rollback_candidate=<previous release id>
```

Do not use `PROMOTE_SKIP_PREFLIGHT=1` for normal release work.

## 11. Restart and prove recovery

Restart through the installed service and execute the real restartability proof:

```bash
systemctl --user restart research-drive-front-door.service
bash drive/scripts/research_query_engine/verify_front_door_restartability.sh --exercise
```

The verifier checks the real unit/linger/restart policy, health recovery, authenticated session, dataset-count continuity, registry fingerprint continuity, exact public/private build identity, and a bounded cold Discover query.

Record:

```text
restartability=ready
identity=<FRONTEND_SHA>--<BACKEND_SHA>
state=datasets:<count> registry_sha256:<prefix>
cold_discover_seconds=<value>
```

## 12. Same-origin and authentication checks

From an authorized client, verify the same front-door origin serves both UI and protected API.

Record sanitized status/identity for:

```text
GET /
GET /research-drive-build.json
GET /health
GET /health?live=1
GET /datasets
GET /library/desk/resources?live=1
GET /library/live-identity?dataset_id=<known-real-dataset>
POST /library/chat/stream
```

Also prove negative authorization:

- anonymous protected GET -> `401`;
- invalid desk token protected GET -> `401`;
- invalid desk token protected POST -> `401`;
- deterministic legacy `v1` session cookie -> `401`.

Do not store real access tokens in the evidence record.

## 13. Real data and readiness checks

Choose at least one real registered research object and capture its relevant lineage/readiness identifiers.

Where available, record:

```text
dataset_id
registry_id
manifest_id
job_id
run_id
attempt
worker_id
registered
held/possession state
freshness
verification
query_ready
```

Explicitly verify these distinctions with real examples where possible:

- registered but not query-ready;
- stale but still possessed;
- provenance known without inventing physical possession;
- local possession only when local bytes/holding evidence exists;
- query-ready only when the runtime can actually query the object.

## 14. Real connected-account checks

For each provider that is configured for this host:

1. open/complete the real OAuth/PKCE flow through the intended browser/origin;
2. verify the connection is bound to the expected principal/account;
3. verify provider reachability;
4. verify principal seed/connected-account state appears correctly;
5. disconnect/reconnect one noncritical test connection if operationally safe;
6. verify one account cannot inherit another principal's connection state.

Skip providers not configured for the release; mark them `NOT CONFIGURED`, not `PASS`.

## 15. Real remote-worker journey

Exercise one controlled real job through the actual worker-control plane.

Required lifecycle evidence:

```text
join
-> claim
-> heartbeat
-> execute/acquire
-> artifact
-> manifest identity
-> materialization
-> registration
-> Library/readiness visibility
```

Verify the worker/controller token boundary remains private and that the worker-control address is not exposed through the browser-facing public interface.

## 16. Discover golden path

Run one real research-data acquisition journey:

```text
research need
-> Discover evidence
-> identify missing external data/evidence
-> compile bounded procurement request
-> review/submit
-> durable pending state
-> approval where required
-> worker execution
-> completed artifact
-> materialization/registration
-> Library visibility
```

Capture IDs and state transitions, not private credentials.

## 17. Library golden path

Use a real held object:

```text
registered object
-> provenance receipt
-> holdings/possession
-> freshness
-> verification/readiness
-> preview/query
```

Verify the UI/API does not collapse these separate states into a single `available` claim.

## 18. Synthesis golden path

Run one real bounded synthesis journey:

```text
objective
-> evidence/object mapping
-> bounded measurement
-> Preview
-> review/approval
-> execute approved current spec
-> output artifact
-> materialize/register
-> lineage/method export
```

Verify:

- Preview does not materialize the output;
- execution cannot be authorized by model text alone;
- the executed spec corresponds to the approved current Preview;
- output carries explicit lineage/identity where available;
- deterministic method export can reproduce the intended operation contract.

## 19. Final live identity

After all journeys:

```bash
bash drive/scripts/research_query_engine/promote_front_door.sh --current
curl -fsS "http://${YZU_DESK_HOST}:${YZU_DESK_PORT}/research-drive-build.json"
systemctl --user status research-drive-front-door.service --no-pager
```

The live release and returned build identity must name the promoted pair.

## 20. Rollback exercise

A release is not accepted until rollback has been demonstrated or explicitly deferred with a documented reason.

Restore the previous complete pair:

1. check out the previous backend SHA;
2. check out the previous frontend SHA;
3. restore matching environment pins;
4. ensure its staged release directory still exists;
5. preflight that exact pair;
6. promote the previous release ID;
7. restart the service;
8. run restartability `--exercise`;
9. verify live build identity;
10. if the new release is still the desired release, repeat the same complete-pair process to promote it again.

Do **not** call a static-link-only swap a complete rollback.

## 21. Acceptance decision

Mark the release:

- **ACCEPTED** only if required host checks are green and exact build identity is preserved;
- **REJECTED** if a required host-bound invariant fails;
- **PARTIAL / NOT TESTED** where an optional provider or worker path is intentionally unavailable.

A rejection should include the exact pair, failing command/journey, sanitized evidence, and whether the previous release remained/restored live.
