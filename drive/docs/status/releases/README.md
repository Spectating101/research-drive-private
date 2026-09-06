# Research Drive release documentation

This directory contains both **current release handoff material** and **historical release records**. Do not assume the newest-looking filename or an old RC number is the current deployment authority.

## Current backend release line — 2026-09-04

Start here:

1. [`BACKEND_RELEASE_HANDOFF_20260904.md`](./BACKEND_RELEASE_HANDOFF_20260904.md) — current scope, repository certification boundary, host-only acceptance, operator rules and stop conditions.
2. [`BACKEND_ARCHITECTURE_20260904.md`](./BACKEND_ARCHITECTURE_20260904.md) — subsystem architecture and authority model for Library, Discover, Synthesis, connected accounts, workers, identity, and release mechanics.
3. [`BACKEND_HOST_RELEASE_RUNBOOK_20260904.md`](./BACKEND_HOST_RELEASE_RUNBOOK_20260904.md) — exact staged build, preflight, promotion, restart, golden-path, and rollback procedure for the real host.
4. [`BACKEND_HOST_ACCEPTANCE_20260904.md`](./BACKEND_HOST_ACCEPTANCE_20260904.md) — fillable evidence record for real-machine acceptance.

The last behavior-changing backend SHA certified before this documentation pass is:

```text
92cf9a417c778b228d91570d2b1a8654ca0dc251
```

The **actual host checkout SHA must be the final PR #61 head after all documentation commits also pass the release gates**. Do not deploy the SHA above merely because it is written here if PR #61 has moved to a later green descendant.

## Current supporting operational contracts

These older documents still contain live operational details used by the current release process:

- [`FRONT_DOOR_HOST_REPRODUCIBILITY.md`](./FRONT_DOOR_HOST_REPRODUCIBILITY.md) — host/runtime-store linking, registry ownership, procured hydration, provider/runtime prerequisites.
- [`RC2_FRONT_DOOR_CONTRACT.md`](./RC2_FRONT_DOOR_CONTRACT.md) — same-origin front-door security and acceptance contract. Treat its pinned release identities as historical; use the current release runbook for the new pair.
- [`RC2_LIVE_IDENTITY_CONTRACT.md`](./RC2_LIVE_IDENTITY_CONTRACT.md) — historical identity contract that remains useful when interpreting live object identity.
- [`DESK_AUTH_BOUNDARY_20260803.md`](./DESK_AUTH_BOUNDARY_20260803.md) — desk authorization boundary.
- [`MULTI_USER_AUTHORITY_20260803.md`](./MULTI_USER_AUTHORITY_20260803.md) — multi-user authority model.

## Historical release records

The following are provenance/history, not current deployment instructions:

- `RC1_CLOSEOUT.md`
- `RC1_LIVE_PAYLOAD_IDENTITY.json`
- `DAY2_AND_RC2_ROADMAP.md`
- RC1/RC2-specific SHA pins inside older documents

Historical records should not be rewritten to pretend they described the current release. If a historical operational rule remains valid, reference it from a current document and explicitly separate the old release identity from the current candidate.

## Release identity rule

A Research Drive release is a **pair**:

```text
<frontend_sha>--<backend_sha>
```

The release directory, `research-drive-build.json`, environment pins, live service, and rollback procedure must all agree on that pair.

Branch names, PR titles, screenshots, or "latest" are not release identity.

## Evidence rule

Repository CI may certify code/configuration/release mechanics. Only the actual Research Drive host may certify:

- systemd/linger/restart behavior;
- private network binding;
- real environment permissions;
- mounted runtime registry/data roots;
- real OAuth/provider reachability;
- real remote worker operation;
- real held-data Discover/Library/Synthesis journeys;
- live promotion and rollback.

Use `BACKEND_HOST_ACCEPTANCE_20260904.md` for those claims.

## Secret-handling rule

Never commit or paste:

- access tokens;
- OAuth client secrets/refresh tokens;
- full private environment files;
- credential-store contents;
- private provider launcher state.

Release evidence should contain exact commit/build identities, sanitized host/service state, timings, lineage IDs needed to prove the workflow, and non-secret error output.
