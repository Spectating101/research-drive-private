# Research Drive backend release handoff — 2026-09-04

**Audience:** release owner, host operator, backend maintainer, reviewer  
**Release line:** `integration/research-drive-backend-rc-refresh-20260904`  
**Last behavior-changing certified backend SHA:** `92cf9a417c778b228d91570d2b1a8654ca0dc251`  
**PR:** `#61` — refreshed Research Drive backend release candidate  
**Status:** repository-certified for staging; production acceptance remains host-bound

## 1. Purpose

This document is the entry point for taking the refreshed Research Drive backend from repository certification to the real Research Drive host.

The release is no longer in ordinary feature development. The code path represented by `92cf9a417c778b228d91570d2b1a8654ca0dc251` passed the three release-facing certification lanes on the same exact tree:

- Backend Release Proof — success;
- Research Drive backend release candidate — success;
- Private Runtime contract — success.

Subsequent commits that only add or revise documentation must still pass the release gates before the final PR head is treated as the checkout SHA for host staging.

## 2. What this release contains

The refreshed backend line composes the previously certified backend RC with the accepted Synthesis object-target seam and the release/retrieval fixes found during convergence review.

### Synthesis authority

- bounded measurement and bounded reads;
- multi-input evidence mapping;
- Preview as a non-materializing operation;
- explicit approval after a current Preview;
- execution authority separated from proposal authority;
- deterministic method export;
- typed object/activity targets for Ask receipts;
- stale/tampered preview rejection and execution binding.

### Discover / procurement authority

- procurement plan compilation into bounded capabilities/resources/shards/retries;
- durable submission lifecycle;
- server-owned idempotency;
- owner isolation;
- immutable job authority after submission;
- worker/runtime placement owned by the runtime rather than by model text.

### Library / research-object authority

- fail-closed source provenance;
- held-only authoritative retrieval boundary;
- semantic widening as secondary evidence rather than possession authority;
- explicit possession/readiness distinction;
- query-term evidence receipts;
- freshness/readiness/registration kept separate;
- physical storage paths excluded from semantic topic authority.

### Connected accounts and principal boundary

- principal-bound connected-account state;
- OAuth/PKCE integration for supported providers;
- multi-account separation;
- encrypted credential boundary;
- `/library/seed` principal seed path;
- role/session/token authorization enforced separately from Origin/CORS.

### Release and restart authority

- immutable staged release directories keyed by `<public_sha>--<private_sha>`;
- build identity in `research-drive-build.json`;
- read-only release preflight;
- restartability verification;
- atomic live-link promotion;
- fail-closed refusal on identity or restartability mismatch;
- rollback candidate preserved as a complete UI/backend pair.

## 3. What is certified in repository CI

Repository CI is allowed to claim only properties reproducible without the production machine. It currently proves:

- Python/configuration compilation and validation;
- backend and same-origin API contracts;
- Synthesis/Discover/Library authority contracts;
- job identity and manifest projection;
- connected-account security contracts;
- worker-control and remote-worker protocol contracts;
- retrieval ranking/evidence regressions;
- public/private interoperability contracts;
- front-door build/preflight/promote/restart script syntax;
- staged release promotion behavior in isolated temporary repositories;
- failure before live-link mutation when identity or restartability preflight is invalid.

It does **not** certify real machine state, real mounted holdings, real OAuth credentials, Tailscale reachability, systemd persistence, real remote workers, or a live promoted service.

## 4. Host-only acceptance boundary

The following facts must be established on the target Research Drive host and must not be replaced with mocked or CI evidence:

1. the intended backend and frontend commits are the commits actually checked out;
2. the front-door environment is host-local, protected, and pins the intended frontend;
3. runtime registry/data-lake ownership resolves to the intended mutable authority;
4. the public bundle is built into a complete immutable release directory;
5. `research-drive-build.json` names the same public/private pair being staged;
6. current-host preflight passes with restartability checking enabled;
7. the systemd user unit restarts and recovers under the real user/linger/network environment;
8. authenticated identity/session state survives restart;
9. configured OAuth/provider integrations are reachable with real credentials;
10. a real remote worker can join, claim, heartbeat, return an artifact, and reach materialization/registration;
11. Discover, Library, and Synthesis operate against real held research objects;
12. promotion changes the live pair atomically and the live identity reports the promoted pair;
13. rollback restores the previous complete pair and survives restart.

Any failure in those steps is host evidence against the exact staged pair. Do not weaken repository contracts to make a host-specific failure disappear.

## 5. Documentation set

Use these documents together:

- `BACKEND_RELEASE_HANDOFF_20260904.md` — scope, certification boundary, ownership and stop conditions;
- `BACKEND_ARCHITECTURE_20260904.md` — backend subsystem and authority model;
- `BACKEND_HOST_RELEASE_RUNBOOK_20260904.md` — staged deployment, preflight, restart, promotion, rollback;
- `BACKEND_HOST_ACCEPTANCE_20260904.md` — fillable evidence record for the real machine;
- `FRONT_DOOR_HOST_REPRODUCIBILITY.md` — established host layout/runtime-linking details;
- `RC2_FRONT_DOOR_CONTRACT.md` — historical same-origin front-door acceptance contract still relevant to the live host;
- `DESK_AUTH_BOUNDARY_20260803.md` and `MULTI_USER_AUTHORITY_20260803.md` — historical authorization boundaries.

## 6. Operator rules

- Never paste tokens, OAuth secrets, private credential-store contents, or full host environment files into tickets, PRs, screenshots, or AI chats.
- Record commit SHAs, build identity, sanitized endpoint results, service state, timings, IDs needed to prove lineage, and error text that does not contain secrets.
- Do not use `PROMOTE_SKIP_PREFLIGHT=1` as a convenience switch. It is an emergency override and a promotion performed with it is not accepted release evidence.
- Do not treat `registered`, `held`, `fresh`, `verified`, `query_ready`, and `materialized` as synonyms.
- Do not treat a successful model response as execution authority.
- Do not promote a frontend-only or backend-only change as a complete Research Drive rollback.
- Do not mutate the inherited `agents/finrobot` malformed gitlink merely to remove checkout noise; its intended remote cannot be recovered from repository history.

## 7. Stop conditions

Stop the release and preserve evidence if any of the following occurs:

- checkout SHA differs from the intended candidate;
- tracked working tree is dirty;
- build identity differs from the staged pair;
- runtime registry resolves to an unexpected file;
- release preflight returns non-zero;
- restartability check returns non-zero;
- service binds outside the approved private address boundary;
- protected APIs accept anonymous or invalid credentials;
- worker identity/manifest lineage is missing after a supposedly successful collection;
- a Library result claims local possession without local authoritative evidence;
- live identity differs from the promoted release;
- rollback cannot restore the previous complete pair.

The correct response is to keep the prior release live where possible, capture sanitized evidence, and repair the demonstrated defect against the exact candidate.
