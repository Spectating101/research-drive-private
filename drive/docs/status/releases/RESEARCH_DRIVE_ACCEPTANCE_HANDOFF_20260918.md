# Research Drive acceptance and release handoff — 2026-09-18

**Audience:** next agent, release operator, reviewer  
**Document branch:** `handoff/research-drive-acceptance-20260918`  
**Application status:** candidate accepted for staging; **not yet promoted**  
**Authority rule:** deploy the exact application SHAs below, not this documentation commit

## 1. Read this first

This document consolidates the current Research Drive state after live browser,
model, storage, acquisition, retry/recovery, cleanup, and backend-suite testing.
It is the current handoff authority for the next release operation.

The documentation branch deliberately does not advance either application
candidate. A Research Drive release is always the exact pair:

```text
frontend 347be3e24de44cd3099ed77cab98512f77ad79f2
backend  50584dc8a3153cf1f728ecc40badfe28a6d892a1
```

Do not replace either SHA with a branch head or with this handoff commit.

## 2. Release identities

| Role | Frontend | Backend | State |
| --- | --- | --- | --- |
| Currently serving RC3 | `347be3e24de44cd3099ed77cab98512f77ad79f2` | `580d501478de6c7c0f94f74aa3ce9a19892a7c34` | Live at `https://rc3.easycamp.tech` |
| Next candidate | `347be3e24de44cd3099ed77cab98512f77ad79f2` | `50584dc8a3153cf1f728ecc40badfe28a6d892a1` | Accepted for staging; not deployed |
| Older rollback/control | See the existing immutable 8765 release manifest | See the existing immutable 8765 release manifest | Keep untouched; do not infer identity from current branches |

Candidate repositories/checkouts used during acceptance:

```text
frontend checkout
/home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/yzu-cluster-profile-memory-workflow-20260917
branch: feature/research-profile-auto-memory-20260915

backend checkout
/home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/research-drive-release-20260917r-backend
application branch: fix/controller-retry-parity-20260918
application SHA: 50584dc8a3153cf1f728ecc40badfe28a6d892a1
```

The backend candidate commit is pushed to `origin` with message:

```text
Fix controller retry parity for acquisition jobs
```

## 3. What was actually exercised

### Public and member research flow

- public guest Library and Discover browsing;
- guest Ask remains permission-gated and does not prewarm the model;
- disposable public-member sign-in;
- real grounded Copilot Ask response (approximately 27.7 seconds in the tested turn);
- sign-out restoring guest authority;
- Discover searches for stablecoin and wildfire/economic evidence;
- responsive checks at workstation, 1180-pixel, and 390-pixel widths;
- cockpit suppression below its intended workstation breakpoint;
- isolated new-user profile-memory and Synthesis persistence;
- trusted-member acquisition-review surface;
- non-operator frontend no longer calls operator-only `/yzu/acquisitions`.

### Default platform storage

The service-managed estate is available independently of optional user OAuth
storage:

- canonical Google Drive archive reported ready;
- Transcend bulk tier mounted with approximately 631 GB free during acceptance;
- NVMe had approximately 52.8 GB free, above the 40 GB operational gate;
- real scoped GDrive write, SHA readback, exact delete, and cleanup passed.

The verified temporary remote path was under:

```text
gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/
  __research_drive_acceptance__/codex-write-read-delete-20260918/
```

The uploaded object was deleted and the local source remained intact.

### Full acquisition lifecycle

An isolated real collection traversed:

```text
pending approval
  -> approved
  -> assigned
  -> running
  -> validating
  -> archiving
  -> registering
  -> registered
```

Acceptance dataset:

```text
acceptance_state_population_20260918_fqeujz
```

It produced a CSV and manifest, archived to the scoped GDrive acceptance area,
registered as query-ready, and returned five real query rows. A deliberate 404
source failed and did not create a registered dataset.

All temporary local and remote acceptance artifacts were removed afterward.

### Retry and recovery defect closed

The acceptance run found a real controller/local execution bug: a retryable
failure was marked terminal after attempt one even though remote WorkerControl
already requeued the same class of failure correctly.

Backend `50584dc8a3153cf1f728ecc40badfe28a6d892a1` fixes the parity in:

```text
drive/scripts/yzu_cluster/orchestrator.py
tests/test_orchestrator_runtime.py
tests/test_scheduler_windows_lane.py
```

Recovery proof:

1. attempt one received an injected transient failure;
2. runtime became `retrying` and legacy status returned to queued;
3. attempt two performed the real HTTP collection;
4. the result archived to GDrive;
5. registration completed;
6. a query returned three rows;
7. a separate permanent failure never registered.

## 4. Test evidence

Focused runtime/worker and regression runs passed, culminating in:

```text
55 passed
```

The full backend suite passed with only the old 8765 deployed-identity invariant
excluded because it probes the rollback deployment rather than RC3:

```text
1640 passed, 9 skipped, 5 deselected in 120.35s
```

The full run used:

```text
RESEARCH_DRIVE_SKIP_SHA_GATE=1
```

This is acceptable only for source-suite certification against this checkout.
It is not permission to bypass staged-release identity checks.

Two test-environment findings were resolved during the run:

- one Parquet subprocess abort did not reproduce in isolation;
- a scheduler unit test depended on live `www.sec.gov` DNS and was changed to
  the suite's deterministic `example.test` host because the contract under test
  is queue routing, not SEC availability.

## 5. Runtime integrity and cleanup proof

The runtime registry is an intentional symlink to the integration authority:

```text
drive/config/research_query_registry.json
  -> /home/phyrexian/Downloads/llm_automation/project_portfolio/
     Molina-Optiplex/Sharpe-Renaissance-runtime-integration/
     drive/config/research_query_registry.json
```

An early isolated-run setup accidentally preserved this symlink and appended two
acceptance rows to the live registry. Cleanup was exact:

- only the two acceptance IDs were removed;
- current content was compared against the saved pre-acceptance registry;
- the only difference was `updated_at`;
- the exact saved bytes were restored atomically;
- final SHA-256 returned to
  `eaa5864cc50f7c62f16a84d192b52b67827a4b1e6f1472d09406c22d02b9dcf0`;
- final counts were 168 internal entries and 139 researcher-facing assets;
- zero acceptance IDs remain.

The live RC3 service remained active with zero restarts and `/api/healthz`
reported healthy after cleanup.

The backend checkout may show this pre-existing type change:

```text
 T drive/config/research_query_registry.json
```

Do not stage it. It represents host runtime topology, not candidate source work.

## 6. Optional connected-account boundary

Personal connected-storage OAuth was not executable on this host because the
provider environment is not configured:

```text
Google Drive OAuth configured: false
Dropbox OAuth configured: false
OneDrive OAuth configured: false
rclone available: true
encrypted credential password source configured: false
YZU_CONNECTED_ACCOUNTS_PUBLIC_BASE_URL: unset
```

A guest request to `/api/library/accounts` correctly returned 403. Do not claim
that provider OAuth consent/callback/read/write isolation was accepted.

This does not make the default Library empty and does not invalidate the
service-managed storage proof. The canonical GDrive archive and Transcend tier
are platform storage; user-connected accounts are optional principal-owned
augmentation.

To certify optional connected accounts later, configure real OAuth applications,
the public callback base URL, and an encrypted rclone password source, then run
interactive consent, root-scoped read/write, cross-principal isolation, and
disconnect/revocation tests.

## 7. Inference boundary

Real Copilot reasoning worked for the tested named member. Anonymous guests are
not authorized for Ask or model prewarm. That closes the obvious anonymous
quota-amplification path.

The present host account pool is suitable for controlled acceptance and a
bounded invited launch. Do not describe pooled personal Copilot identities as a
permanent arbitrary-public inference billing model. Before materially scaling
authenticated usage, choose an organization/server-to-server entitlement,
per-user entitlement, or a separately governed provider/BYOK path.

## 8. Shell and host traps

These are operational requirements, not folklore:

1. Begin shell commands with `rtk` in this environment.
2. `rtk cp` may summarize or truncate large text/JSON. For an exact copy, use
   `rtk /bin/cp` and compare hashes.
3. Do not redirect wrapper-compressed `rtk jq` stdout into an authority file.
4. `cp -a` preserves symlinks. Never use it to create an isolated registry copy
   unless the resolved target is deliberately replaced with ordinary bytes.
5. Use `/usr/bin/find`; a shell interception has previously returned empty
   results for bare `find`.
6. Never leave the serving checkout HEAD inconsistent with its environment pin
   and build manifest.
7. Building in a serving clone can overwrite the live release through `dist`
   symlinks. Build an immutable staged release instead.
8. Browser tests against the deployed URL do not prove unbuilt local changes.
9. A mutation test is evidence only after proving the intended mutation occurred.
10. The 8765 rollback deployment has its own identity contract. Do not use its
    expected SHA as evidence against the RC3 candidate.

## 9. Promotion sequence

Do not resume product redesign from this handoff. The next operation is release
commissioning for the exact pair.

1. Confirm the frontend checkout is exactly
   `347be3e24de44cd3099ed77cab98512f77ad79f2`.
2. Confirm the backend application checkout/branch resolves exactly to
   `50584dc8a3153cf1f728ecc40badfe28a6d892a1`.
3. Confirm tracked source is clean while excluding the intentional runtime
   registry type change and untracked immutable release outputs.
4. Build an immutable release named by the exact pair.
5. Confirm `research-drive-build.json` contains both exact SHAs.
6. Run the normal read-only release preflight without bypass switches.
7. Exercise real service restartability and re-check dataset count, registry
   fingerprint, authenticated session, Discover evidence, and build identity.
8. Stage the pair side by side with the current live pair.
9. Smoke as guest: Home/Library/Discover visible; Ask and prewarm unavailable.
10. Smoke as named member: sign in, Ask, saved History, Synthesis resume, and
    sign out.
11. Run one bounded acquisition success and one permanent-failure proof using a
    unique acceptance prefix; clean both local and remote artifacts.
12. Promote atomically only after all checks are green.
13. Record the final live manifest, systemd state, registry fingerprint, and
    complete rollback pair.

## 10. Stop conditions

Stop and keep the existing release live if any of these occurs:

- either application SHA differs from the candidate pair;
- an unexpected tracked change is present;
- manifest, environment pins, checkout identities, and release directory differ;
- registry count/fingerprint changes without an explained operation;
- restartability fails or the service loops;
- guest can invoke Ask/prewarm or read saved private reasoning;
- member/operator authority is broadened unexpectedly;
- a failed acquisition registers a dataset;
- a retryable acquisition becomes terminal before exhausting its policy;
- an acceptance object cannot be deleted exactly from local and remote storage;
- the prior coherent rollback pair cannot be identified.

## 11. First commands for the next agent

Run read-only identity checks before changing anything:

```bash
rtk git -C /home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/yzu-cluster-profile-memory-workflow-20260917 status --short
rtk git -C /home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/yzu-cluster-profile-memory-workflow-20260917 rev-parse HEAD

rtk git -C /home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/research-drive-release-20260917r-backend status --short
rtk git -C /home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/research-drive-release-20260917r-backend rev-parse fix/controller-retry-parity-20260918

rtk systemctl --user status research-drive-candidate-memory.service --no-pager
```

Then use the existing host release runbook. Do not infer deployment state from
this document branch.

## 12. Bottom line

The read/reasoning path, service-managed storage, real acquisition happy path,
permanent-failure behavior, retry recovery, registration, query readback, and
cleanup have all been exercised. The single code defect found in that operation
is fixed and regression-tested at backend `50584dc8...`.

The next candidate is coherent and ready for an exact-pair staged deployment.
It is not yet the live backend, and optional user-connected OAuth remains
environment-unconfigured rather than falsely certified.
