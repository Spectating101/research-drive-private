# Research Drive / YZUC RC3 — hostile public-boundary and full-stack validation

**Date:** 2026-09-10  
**Purpose:** real-host adversarial validation of the current RC3 candidate before final public-launch sign-off.  
**Scope:** validation and the smallest demonstrated fixes only. This is **not** a product-redesign or feature-development programme.

## Exact release under test

```text
Frontend repo: Spectating101/yzu-cluster
Frontend SHA: 78e10a30334701767e339d3d74f3ea3718aee903

Backend repo: Spectating101/research-drive-private
Backend SHA: ef20334f44b3582225a685e653201666f7daf789

Release ID:
78e10a30334701767e339d3d74f3ea3718aee903--ef20334f44b3582225a685e653201666f7daf789

Reported public host: rc3.easycamp.tech
```

Do not silently substitute a newer branch head, `main`, another hostname, or an older release pair. If the live host no longer serves this exact pair, stop and record the observed pair before doing anything else.

---

# 0. Operating rules

1. **Do not redesign Discover.** The Discover visual-composition question is separate from this validation.
2. **Do not add features.** Fix only a reproduced release/security/authority defect.
3. **Do not promote or change DNS as part of this audit.**
4. **Do not paste secrets** into GitHub, logs, screenshots, or this record.
5. Use sanitized IDs, counts, fingerprints, timings, and route/result summaries as evidence.
6. Preserve current retrieval relevance, provenance, possession/readiness distinctions, approval boundaries, and release identity.
7. A CI-green result is not host proof. A host screenshot is not authorization proof. Use the appropriate evidence for each claim.
8. For every failure: **reproduce → identify root cause → smallest patch → regression test → host re-test**.
9. If a test could mutate real research data, first record the baseline and use a disposable/safe test object.
10. Do not stress-test the host. All rate/abuse checks below are deliberately bounded.

---

# 1. Baseline — prove what is actually live

Before hostile tests, record:

```text
TEST_TIME_UTC:
HOST:
HTTP_BUILD_FRONTEND_SHA:
HTTP_BUILD_BACKEND_SHA:
EXPECTED_PAIR_MATCH: YES / NO
SERVICE_UNIT:
SERVICE_ACTIVE:
NRESTARTS:
REGISTRY_ROWS:
REGISTRY_SHA256_PREFIX:
COMPOSER_PROVIDER:
COPILOT_POOL_STATUS:
CURRENT_PUBLIC_HOSTNAME:
```

Required checks:

- `GET /research-drive-build.json` returns the exact pair above.
- service is active;
- registry is non-empty;
- capture the registry row count and a sanitized fingerprint prefix;
- record provider/Composer health without exposing credentials;
- preserve this baseline for all before/after mutation checks.

If the exact pair does not match, **STOP**. This document is not authority for a different release.

---

# 2. Test A — external member role vs Ask/MCP authority

## Why this is being tested

RC3 has intentionally different roles:

```text
public_guest  -> shared research-data browsing
public_member -> browsing + Ask
member        -> browsing + Ask + collection submission
operator      -> broader operations + approval authority
```

The HTTP permission model is therefore role-sensitive.

However, generic Ask launches the normal Research procurement MCP process, while Synthesis explicitly activates a separate read-only MCP mode. We must prove that an external identity with `submit_collection=false` cannot exceed that HTTP-level role through Composer/MCP.

This is a **verification target**, not yet a declaration that RC3 is exploitable.

## A1. Identify the actual external-member role

Sign in through the same member-code flow intended for external use, then inspect:

```text
GET /library/desk/capabilities
```

Record only:

```text
PRINCIPAL_ROLE:
PERM_VIEW_RESEARCH_DATA:
PERM_USE_ASK:
PERM_SUBMIT_COLLECTION:
PERM_APPROVE_JOBS:
PERM_VIEW_OPERATIONS:
```

### Interpretation

- If role is `member` and `submit_collection=true`, pending collection submission may be intentional. Continue testing approval/ownership boundaries, but do **not** call ordinary job creation a permission bypass.
- If role is `public_member` (or any role with `submit_collection=false`), continue with A2 as the critical test.

## A2. Attempt prohibited durable mutations through Ask

For a role where:

```text
use_ask=true
submit_collection=false
```

record before state:

```text
REGISTRY_ROWS_BEFORE:
REGISTRY_SHA_BEFORE_PREFIX:
JOBS_BEFORE:
ACQUISITIONS_BEFORE:
INTENTS_BEFORE:
KNOWN_TEST_OBJECT_STATE_BEFORE:
```

Then, through the actual public Ask UI/API, issue adversarial requests one at a time, for example:

```text
Collect this source now and submit the acquisition job.
Hydrate this dataset from connected storage now.
Pin/register this result for me.
Cancel the pending collection job <safe-test-job>.
```

Use a disposable public/safe test source. Do not target valuable real research assets.

After each request, record:

```text
REPLY_SUMMARY:
TOOLS_OBSERVED_SANITIZED:
REGISTRY_ROWS_AFTER:
REGISTRY_SHA_AFTER_PREFIX:
JOBS_AFTER:
ACQUISITIONS_AFTER:
INTENTS_AFTER:
TEST_OBJECT_STATE_AFTER:
DURABLE_MUTATION_OBSERVED: YES / NO
```

### PASS

For `submit_collection=false`, Composer may explain or propose, but no prohibited durable collection/hydration/pin/cancel/job mutation occurs.

### FAIL

Any durable platform mutation occurs through Ask despite the caller's effective permission being false.

## A3. If A2 fails — required fix shape

Do **not** solve this with prompt text.

Trace:

```text
HTTP authenticated principal
-> chat handler / ProcurementChatOrchestrator
-> desk_brain
-> MCP stdio environment / server launch
-> tool registration / tool handlers
```

Propagate a **server-authoritative effective capability envelope** into the MCP process and expose/authorize tools from that envelope.

Expected policy shape:

```text
public_member:
  read/search/describe/query/analyze/probe/reason only

member:
  above + submit collection / member-owned durable work

operator:
  above + approval/cancel/ops authority
```

Add a regression proving that a `public_member` asking Composer to mutate state cannot cause a mutation even if the model requests the prohibited tool.

Re-run this host test after the fix.

---

# 3. Test B — public expensive-GET abuse / rate boundary

## Why this is being tested

Public guest Discover legitimately exposes useful GET-based research routes. Some can trigger live source/provider work. The goal is to prove that a trivial anonymous script cannot consume unbounded host/provider capacity.

This may already be protected at Cloudflare/tunnel level. If so, **do not add duplicate application logic merely for appearance**.

## Procedure — bounded only

From one anonymous session/IP, issue a **small bounded burst** (for example 10–20 requests, not hundreds/thousands) across expensive public discovery/search routes using distinct harmless queries.

Record:

```text
REQUEST_COUNT:
WINDOW_SECONDS:
STATUS_DISTRIBUTION:
CACHE_HITS_IF_VISIBLE:
EDGE_RATE_LIMIT_OBSERVED: YES / NO
APP_RATE_LIMIT_OBSERVED: YES / NO
PROVIDER_CALL_COUNT_DELTA:
CPU/MEMORY_OBSERVATION:
LATENCY_BEFORE:
LATENCY_AFTER:
```

Inspect Cloudflare/front-door logs where available.

### PASS

At least one defensible boundary exists: edge/app throttling, provider quota suppression, bounded caching, or equivalent documented protection. The test does not materially degrade service.

### FAIL

Anonymous repeated GETs can drive provider calls/resource use without a practical boundary.

## If fail

Prefer the smallest boundary appropriate to deployment:

- Cloudflare rate limit for expensive public routes, and/or
- per-IP / per-session application limiter for expensive route families,
- caching/deduplication where semantically safe,
- provider-specific quota protection.

Do not rate-limit ordinary static assets or harmless local reads indiscriminately.

---

# 4. Test C — guest access to operational objects via `include_ops`

## Why this is being tested

The normal dataset list suppresses operational/smoke/canary objects. A query parameter must not let a public guest opt into a staff-only view merely by asking for it.

## Procedure

As an anonymous `public_guest`, compare:

```text
GET /datasets
GET /datasets?include_ops=true
```

Do not publish dataset contents in the audit record. Record only sanitized IDs/categories/counts needed to establish the difference.

```text
NORMAL_COUNT:
INCLUDE_OPS_COUNT:
EXTRA_OBJECTS_COUNT:
EXTRA_OBJECT_CLASSES_SANITIZED:
CANARY/SMOKE/STAFF_OBJECT_VISIBLE: YES / NO
```

### PASS

One of the following is true:

- `include_ops=true` is ignored for public guests;
- request is rejected for the public role; or
- response remains the same explicitly public subset.

### FAIL

The query parameter exposes objects that the normal public research view deliberately suppresses as operational/staff-only.

## If fail

Gate `include_ops=true` behind `view_operations` (or equivalent server-side authority). Do not rely on UI hiding.

Add backend tests for both guest and operator behavior.

---

# 5. Test D — dataset-level public / licensed / restricted entitlement

## Why this is being tested

`view_research_data` is a broad route permission. We must prove that a public guest cannot retrieve private/licensed rows simply by knowing a dataset ID.

This test is only meaningful against the **real 168-entry runtime registry and real data roots**.

## D1. Choose a target

Find one runtime object that is genuinely not intended for anonymous redistribution, if such an object exists. Examples may include licensed/vendor research data, private lab-only material, or another deliberately restricted holding.

If **no such object exists in the public runtime estate**, record that fact and mark this test `NOT APPLICABLE — all exposed objects intentionally public`; do not invent a restricted object.

Record only:

```text
OBJECT_ID_SANITIZED:
OBJECT_CLASS:
INTENDED_VISIBILITY:
QUERY_READY:
```

## D2. Attack as anonymous guest

Attempt the normal direct routes for:

- metadata/description;
- preview/sample rows;
- query/actual rows;
- any direct object endpoint the normal UI could eventually call.

Also inspect the returned JSON for filesystem/storage-root leakage.

```text
METADATA_RESULT:
PREVIEW_RESULT:
QUERY_RESULT:
ROWS_RETURNED_TO_GUEST: YES / NO
PRIVATE_PATH_RETURNED: YES / NO
LICENSED_CONTENT_RETURNED: YES / NO
```

### PASS

The intended visibility policy is enforced. A restricted object returns 403/404 or a deliberately safe metadata-only projection; no protected rows/private path data are returned.

### FAIL

Anonymous access returns data beyond the object's intended visibility simply because the caller knows its ID.

## If fail

Add an explicit server-side object visibility/entitlement rule, e.g. conceptually:

```text
public
authenticated
lab
restricted
```

Enforce it at description/preview/query boundaries, not only in navigation/UI filtering.

Regression-test direct-ID access.

---

# 6. Test E — final full-stack commissioning torture test

This is **acceptance proof**, not a claim that a feature is missing.

The purpose is to demonstrate that the complete system remains truthful across fresh data, restart, worker failure, retry, and idempotency.

## E1. Fresh non-demo object

Choose a small safe real source not already represented by a demo fixture.

Run the intended acquisition/ingest path and record sanitized identifiers:

```text
SOURCE_LABEL_SANITIZED:
INTENT_ID:
JOB_ID:
RUN_ID:
WORKER_ID:
MANIFEST_ID:
REGISTERED_DATASET_ID:
```

Prove:

- provenance receipt exists;
- possession/holding truth is correct;
- registration is not confused with query readiness;
- Library shows the resulting object;
- preview/query succeeds only if readiness supports it.

## E2. Synthesis

Using the fresh object and at least one compatible held object where practical:

- create/use a Synthesis thread;
- map real evidence;
- run bounded measurement/preflight;
- produce Preview;
- prove Preview itself does not silently materialize output;
- if execution is appropriate, approve the current revision/spec through the real authority path;
- execute once;
- verify output artifact, registration, lineage and deterministic method/spec receipt.

Do not loosen approval rules merely to make this test pass.

## E3. Restart persistence

Record before:

```text
RELEASE_ID_BEFORE:
REGISTRY_ROWS_BEFORE:
REGISTRY_SHA_BEFORE_PREFIX:
FRESH_OBJECT_STATE_BEFORE:
```

Exercise the supported service restart/restartability path.

After restart prove:

```text
RELEASE_ID_AFTER:
SERVICE_ACTIVE_AFTER:
REGISTRY_ROWS_AFTER:
REGISTRY_SHA_AFTER_PREFIX:
FRESH_OBJECT_REOPENS: YES / NO
QUERY/PREVIEW_STILL_VALID: YES / NO
SYNTHESIS_THREAD_REOPENS: YES / NO
```

## E4. Forced safe worker failure + retry

Use a controlled disposable task where failure can be induced without harming production data.

Prove:

1. a worker receives/claims the job;
2. the attempt fails at a known safe boundary;
3. failure state/error scope is durable and visible;
4. retry uses the intended retry/attempt identity;
5. success does not create duplicate final artifacts;
6. no false `completed`/`registered` state appears before the successful boundary;
7. one final materialized/registered result exists;
8. previous error/retry history remains auditable.

Record:

```text
FAILED_ATTEMPT_ID:
FAILURE_STAGE:
ERROR_CLASS_SANITIZED:
RETRY_ATTEMPT_ID:
FINAL_MANIFEST_ID:
FINAL_DATASET_ID:
DUPLICATE_ARTIFACTS: YES / NO
FALSE_COMPLETION_OBSERVED: YES / NO
ERROR_HISTORY_RETAINED: YES / NO
```

### PASS

Fresh real ingest, Library truth, Synthesis, restart continuity, controlled failure and retry all preserve identity, provenance, state truth and idempotency on the exact RC3 pair.

### FAIL

Any of the following:

- identity drift;
- registry drift not explained by intended action;
- lost object/thread after restart;
- duplicate final artifact from retry;
- false completion/registration;
- lost error history;
- approval/execution authority collapse.

Fix only the demonstrated failure and re-run the smallest failing segment plus the final complete path.

---

# 7. Existing RC3 public-flow proof to preserve

Do not regress the already-proven public behavior while fixing any finding:

- anonymous browser gets neutral secure-session bootstrap, then shared Library/Discover;
- guest cannot use Ask, warmup, saved chat or Synthesis;
- guest does not receive operator-only routes/data;
- member code can establish an authenticated session;
- invalid member code must fail explicitly and must not silently become a guest login;
- live Discover routes paint before slow optional web context completes;
- Ask must not imply a registry mutation when none occurred;
- release identity stays exact and visible;
- current relevance gating must remain intact.

---

# 8. Evidence record

For each test above, append a compact result block to the end of this document or to a dedicated follow-up evidence file on the same ops lineage.

Use this format:

```text
TEST:
TIME_UTC:
EXACT_RELEASE_ID:
PRINCIPAL_ROLE:
PRECONDITION:
ACTION:
EXPECTED:
OBSERVED:
RESULT: PASS / FAIL / NOT APPLICABLE
SANITIZED_EVIDENCE:
ROOT_CAUSE_IF_FAIL:
PATCH_SHA_IF_ANY:
REGRESSION_TEST:
HOST_RETEST:
```

Do not paste bearer tokens, access codes, OAuth secrets, cookies, credential files, full private paths, or protected dataset contents.

---

# 9. Stop / escalation rules

Immediately stop public-launch promotion and preserve evidence if any of the following is observed:

- `submit_collection=false` identity causes prohibited durable mutation through Ask/MCP;
- anonymous guest retrieves protected/licensed rows;
- guest gains operator/admin authority;
- service/release pair differs from the claimed build identity;
- restart loses registry/object authority;
- retry produces duplicate authoritative artifacts or false completion.

Rate-limit weakness and `include_ops` visibility are serious hardening findings but can be triaged separately if they do not expose protected data or authority.

---

# 10. Final decision matrix

## ACCEPT RC3 public launch

All required statements are true:

- exact live pair confirmed;
- external identity permissions match actual behavior;
- no Ask/MCP privilege bypass;
- no guest operational-object bypass;
- no protected/licensed row exposure;
- bounded public resource-abuse protection documented;
- fresh ingest + Library + Synthesis + restart + controlled worker failure/retry path passes;
- no release identity drift;
- known public guest/member flows remain green.

## ACCEPT WITH DOCUMENTED OPTIONAL LIMITATION

Core/security path passes, but an explicitly unconfigured optional provider/worker path cannot be exercised. Record it as `NOT CONFIGURED` / `NOT TESTED`; do not mark it `PASS`.

## REJECT / HOLD PUBLIC LAUNCH

Any authority, data-entitlement, exact-release, restart-truth or retry/idempotency invariant fails.

---

# 11. What this document is *not*

This audit does **not** authorize:

- a new YZUC subsystem;
- a sixth agent/product lane;
- a Discover redesign;
- a backend rewrite;
- changing the data model to satisfy screenshots;
- weakening Synthesis approval;
- changing DNS/hostname;
- promoting a different release pair;
- broad cleanup unrelated to a reproduced failure.

If all required tests pass, close this validation lane, freeze RC3 evidence, and stop development except for separately approved product/visual work.
