# Research Drive backend host acceptance record — 2026-09-04

Use this file as the release evidence record for the actual Research Drive host. Fill it from real host execution. Do not mark a host-only item green using CI, mocks, screenshots from another release, or an assumption.

## A. Release identity

```text
DATE_UTC:
OPERATOR:
HOST_ROLE:
BACKEND_REPO:
BACKEND_SHA:
FRONTEND_REPO:
FRONTEND_SHA:
RELEASE_ID: <FRONTEND_SHA>--<BACKEND_SHA>
PREVIOUS_RELEASE_ID:
RELEASE_SCOPE:
```

### Repository certification

```text
LAST_BEHAVIOR_CHANGING_CERTIFIED_BACKEND_SHA: 92cf9a417c778b228d91570d2b1a8654ca0dc251
FINAL_BACKEND_PR_HEAD:
BACKEND_RELEASE_PROOF_RUN:
BACKEND_RC_RUN:
PRIVATE_RUNTIME_RUN:
ALL_GREEN_ON_FINAL_HEAD: YES / NO
```

## B. Checkout integrity

### Backend

```text
EXPECTED_SHA:
OBSERVED_SHA:
TRACKED_DIRTY_COUNT:
UNTRACKED_PATHS_REVIEWED: YES / NO
RESULT: PASS / FAIL
NOTES:
```

### Frontend

```text
EXPECTED_SHA:
OBSERVED_SHA:
TRACKED_DIRTY_COUNT:
RESULT: PASS / FAIL
NOTES:
```

## C. Host environment boundary

Do not paste secrets or the complete environment file.

```text
ENV_PATH:
MODE:
OWNER_GROUP:
YZU_PUBLIC_REPO_SANITIZED:
YZU_PUBLIC_SHA:
YZU_DESK_HOST_SANITIZED:
YZU_DESK_PORT:
YZU_DESK_SERVE_UI:
REGISTRY_AUTHORITY: git / runtime
REGISTRY_PATH_SANITIZED:
RUNTIME_DRIVE_CONFIGURED: YES / NO
PYTHON_BIN_SANITIZED:
COMPOSER_PROVIDER:
NAMED_PRINCIPALS_ENABLED: YES / NO
SHARED_TOKEN_ENABLED: YES / NO
RESULT: PASS / FAIL
NOTES:
```

Required security statement:

```text
SECRET_VALUES_CAPTURED_IN_THIS_RECORD: NO
```

## D. Runtime authority and data roots

```text
REGISTRY_AUTHORITY_MODE:
REGISTRY_RESOLVED_PATH_SANITIZED:
REGISTRY_ROWS:
REGISTRY_SHA256_PREFIX:
RUNTIME_DRIVE_ROOT_SANITIZED:
RESEARCH_DATA_ROOTS_STATUS:
PROCURED_ROOT_STATUS:
YZU_CLUSTER_ROOT_STATUS:
RESULT: PASS / FAIL
NOTES:
```

Confirm explicitly:

- [ ] mutable runtime registry resolves to the expected authority when `runtime` mode is used;
- [ ] Git authority is a tracked regular registry when `git` mode is used;
- [ ] registry is non-empty;
- [ ] no stale copied registry is masquerading as runtime authority;
- [ ] expected data roots are mounted/readable by the service user.

## E. Staged build identity

```text
STAGED_RELEASE_DIR_SANITIZED:
BUILD_IDENTITY_PATH_SANITIZED:
BUILD_PUBLIC_SHA:
BUILD_PRIVATE_SHA:
BUILT_AT_UTC:
RELEASE_SCOPE:
BUILD_RESULT: PASS / FAIL
```

Confirm:

- [ ] staged directory exists under `<FRONTEND_REPO>/releases/`;
- [ ] `index.html` exists;
- [ ] `research-drive-build.json` exists;
- [ ] public SHA equals the intended frontend SHA;
- [ ] private SHA equals the intended backend SHA;
- [ ] build did not move the live release.

## F. Preflight

```text
COMMAND: PREFLIGHT_STATIC_DIR=<candidate> PREFLIGHT_CHECK_RESTARTABILITY=1 bash drive/scripts/research_query_engine/preflight_release.sh
EXIT_CODE:
READY:
BACKEND_SHA:
UI_SHA:
REGISTRY_ROWS:
REGISTRY_SHA256_PREFIX:
REGISTRY_MODE:
RESTARTABILITY_PRECHECK:
RESULT: PASS / FAIL
SANITIZED_OUTPUT:
```

If `RESULT=FAIL`, stop. Do not promote.

## G. Service / network boundary before promotion

```text
SERVICE_UNIT:
SERVICE_ENABLED:
SERVICE_ACTIVE:
RESTART_POLICY:
USER_LINGER:
BIND_ADDRESS_SANITIZED:
EXPECTED_PRIVATE_BIND_ONLY: YES / NO
HEALTHZ_STATUS:
RESULT: PASS / FAIL
NOTES:
```

## H. Promotion

```text
PROMOTION_COMMAND:
PROMOTED_RELEASE_ID:
PREVIOUS_RELEASE_ID_REPORTED:
ROLLBACK_CANDIDATE_REPORTED:
PREFLIGHT_SKIPPED: NO
RESULT: PASS / FAIL
SANITIZED_OUTPUT:
```

A promotion with `PROMOTE_SKIP_PREFLIGHT=1` is not accepted evidence.

## I. Restartability exercise

```text
COMMAND: bash drive/scripts/research_query_engine/verify_front_door_restartability.sh --exercise
RESTARTABILITY:
SERVICE_ACTIVE_AFTER_RESTART:
OBSERVED_IDENTITY:
DATASET_COUNT_BEFORE:
DATASET_COUNT_AFTER:
REGISTRY_SHA_BEFORE_PREFIX:
REGISTRY_SHA_AFTER_PREFIX:
COLD_DISCOVER_SECONDS:
COLD_DISCOVER_LIMIT_SECONDS:
RESULT: PASS / FAIL
SANITIZED_OUTPUT:
```

Confirm:

- [ ] systemd restart succeeds;
- [ ] service returns healthy within the configured bound;
- [ ] authenticated session can be opened after restart;
- [ ] dataset count remains stable across restart;
- [ ] registry fingerprint remains stable across restart;
- [ ] observed frontend/backend identity equals the promoted pair;
- [ ] cold Discover returns real evidence within the configured bound.

## J. Same-origin/API acceptance

| Check | Expected | Observed | Result |
|---|---|---|---|
| `GET /` | real UI | | PASS / FAIL |
| `GET /research-drive-build.json` | exact pair | | PASS / FAIL |
| `GET /health` | healthy | | PASS / FAIL |
| `GET /health?live=1` | live dependencies reported | | PASS / FAIL |
| `GET /datasets` | authenticated dataset response | | PASS / FAIL |
| `GET /library/desk/resources?live=1` | real resources | | PASS / FAIL |
| `GET /library/live-identity?...` | real identity | | PASS / FAIL |
| `POST /library/chat/stream` | authenticated stream | | PASS / FAIL |
| anonymous protected GET | `401` | | PASS / FAIL |
| invalid-token protected GET | `401` | | PASS / FAIL |
| invalid-token protected POST | `401` | | PASS / FAIL |
| legacy `v1` session | `401` | | PASS / FAIL |

```text
SAME_ORIGIN_CONFIRMED: YES / NO
CLIENT_REQUESTS_ESCAPE_TO_MOCK_OR_LOCALHOST: YES / NO
RESULT: PASS / FAIL
NOTES:
```

## K. Real research-object truth

Choose at least one real object. Use additional copies of this section for more objects.

```text
OBJECT_LABEL_SANITIZED:
DATASET_ID:
REGISTRY_ID:
MANIFEST_ID:
JOB_ID:
RUN_ID:
ATTEMPT:
WORKER_ID:
REGISTERED:
POSSESSION/HELD_STATE:
STORAGE/HOLDING_STATE_SANITIZED:
PROVENANCE_STATE:
FRESHNESS_STATE:
VERIFICATION_STATE:
QUERY_READY:
QUERY_ATTEMPT_RESULT:
RESULT: PASS / FAIL
NOTES:
```

Truth checks:

- [ ] registration is not used as proof of query readiness;
- [ ] provenance is not used as proof of possession;
- [ ] storage path is not used as semantic topic authority;
- [ ] stale state can coexist with possession;
- [ ] query-ready is supported by an actual successful readiness/query path.

## L. Connected accounts

For each configured provider:

```text
PROVIDER:
CONFIGURED: YES / NO
PRINCIPAL_SANITIZED:
OAUTH_PKCE_FLOW: PASS / FAIL / NOT TESTED
CALLBACK_ORIGIN: PASS / FAIL / NOT TESTED
ACCOUNT_VERIFICATION: PASS / FAIL / NOT TESTED
PRINCIPAL_ISOLATION: PASS / FAIL / NOT TESTED
SEED_STATE: PASS / FAIL / NOT TESTED
DISCONNECT_RECONNECT: PASS / FAIL / NOT TESTED
RESULT: PASS / FAIL / NOT CONFIGURED
NOTES:
```

Providers not configured must be recorded as `NOT CONFIGURED`, not `PASS`.

## M. Real remote worker

```text
WORKER_LABEL_SANITIZED:
CONTROLLER_BIND_SANITIZED:
JOIN: PASS / FAIL
CLAIM: PASS / FAIL
HEARTBEAT: PASS / FAIL
EXECUTION_OR_ACQUISITION: PASS / FAIL
ARTIFACT_RETURN: PASS / FAIL
MANIFEST_IDENTITY: PASS / FAIL
MATERIALIZATION: PASS / FAIL
REGISTRATION: PASS / FAIL
LIBRARY_VISIBILITY: PASS / FAIL
FINAL_READINESS:
RESULT: PASS / FAIL
IDS_SANITIZED:
NOTES:
```

## N. Discover golden path

```text
RESEARCH_NEED_SANITIZED:
DISCOVER_EVIDENCE: PASS / FAIL
MISSING_EVIDENCE_IDENTIFIED: PASS / FAIL
BOUNDED_PROCUREMENT_COMPILED: PASS / FAIL
SUBMISSION_DURABLE: PASS / FAIL
APPROVAL_STATE: PASS / FAIL / NOT REQUIRED
WORKER_EXECUTION: PASS / FAIL
ARTIFACT: PASS / FAIL
MATERIALIZATION_REGISTRATION: PASS / FAIL
LIBRARY_VISIBILITY: PASS / FAIL
IDEMPOTENCY_OBSERVED: PASS / FAIL / NOT EXERCISED
RESULT: PASS / FAIL
IDS_SANITIZED:
NOTES:
```

## O. Library golden path

```text
OBJECT_ID_SANITIZED:
PROVENANCE_RECEIPT: PASS / FAIL
POSSESSION/HOLDINGS: PASS / FAIL
FRESHNESS_STATE: PASS / FAIL
VERIFICATION_STATE: PASS / FAIL
READINESS_STATE: PASS / FAIL
PREVIEW_OR_QUERY: PASS / FAIL
STATE_COLLAPSE_OBSERVED: NO / YES
RESULT: PASS / FAIL
NOTES:
```

## P. Synthesis golden path

```text
OBJECTIVE_SANITIZED:
OBJECT_EVIDENCE_MAPPING: PASS / FAIL
BOUNDED_MEASUREMENT: PASS / FAIL
PREVIEW: PASS / FAIL
PREVIEW_MATERIALIZED_OUTPUT: NO / YES
APPROVAL: PASS / FAIL
EXECUTION_BOUND_TO_APPROVED_PREVIEW: PASS / FAIL
OUTPUT_ARTIFACT: PASS / FAIL
MATERIALIZATION_REGISTRATION: PASS / FAIL
LINEAGE: PASS / FAIL
DETERMINISTIC_METHOD_EXPORT: PASS / FAIL
RESULT: PASS / FAIL
NOTES:
```

## Q. Live identity after journeys

```text
PROMOTE_CURRENT_OUTPUT:
HTTP_BUILD_PUBLIC_SHA:
HTTP_BUILD_PRIVATE_SHA:
SERVICE_ACTIVE:
EXPECTED_PAIR_MATCH: YES / NO
RESULT: PASS / FAIL
```

## R. Rollback exercise

```text
ROLLBACK_REQUIRED: YES / NO
ROLLBACK_CANDIDATE:
PREVIOUS_FRONTEND_SHA:
PREVIOUS_BACKEND_SHA:
PREVIOUS_ENV_PINS_RESTORED: YES / NO
ROLLBACK_PREFLIGHT: PASS / FAIL / NOT TESTED
ROLLBACK_PROMOTION: PASS / FAIL / NOT TESTED
ROLLBACK_RESTARTABILITY: PASS / FAIL / NOT TESTED
ROLLBACK_LIVE_IDENTITY: PASS / FAIL / NOT TESTED
NEW_RELEASE_REPROMOTED_AFTER_TEST: YES / NO / N/A
RESULT: PASS / FAIL / DEFERRED
DEFERRED_REASON:
NOTES:
```

## S. Known nonblocking repository hygiene

```text
agents/finrobot malformed inherited gitlink observed: YES / NO
checkout cleanup warning only: YES / NO
runtime/release impact observed: YES / NO
```

Do not invent a submodule URL to silence the warning. Its intended remote is not recoverable from current repository history.

## T. Final decision

```text
RELEASE_DECISION: ACCEPTED / REJECTED / PARTIAL
DECISION_TIME_UTC:
FINAL_LIVE_RELEASE_ID:
FINAL_LIVE_FRONTEND_SHA:
FINAL_LIVE_BACKEND_SHA:
ROLLBACK_CANDIDATE_PRESERVED: YES / NO
UNTESTED_OPTIONAL_PATHS:
KNOWN_FAILURES:
FOLLOW_UP_ISSUES:
```

### Acceptance rule

`ACCEPTED` means the required real-host invariants passed for the exact live UI/backend pair. It does not mean every optional external provider exists or every possible dataset has been exercised.

`REJECTED` means at least one required host invariant failed. Preserve the exact failing pair and sanitized evidence.

`PARTIAL` is appropriate only when the core desk/release path passes but an explicitly optional provider/worker path cannot be tested. It must not be used to conceal a failure in identity, auth, registry authority, restartability, promotion, real-data truth, or rollback.
