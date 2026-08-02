# Research Drive multi-user authority — 2026-08-03

## Boundary

Research Drive is upstream data infrastructure. Researchers, laboratories and
external analysis systems may consume governed Library assets; Research Drive
does not inspect or depend on their models, strategies, portfolios or results.

## Current implementation

The desk now has a provider-neutral principal contract:

- stable principal id, institutional email and display name;
- role: `viewer`, `researcher`, `steward` or `admin`;
- one or more workspace ids and an explicit default workspace;
- server-derived permissions returned by `/library/desk/capabilities`;
- `v3` signed browser sessions carrying only subject/workspace identifiers;
- optional `DESK_PRINCIPALS_FILE` entries authenticated by SHA-256 token digest;
- the legacy shared pilot token maps to one configurable admin principal;
- browser-supplied faculty email no longer overrides an authenticated user's
  institutional email.

Roles are enforced at the HTTP boundary. Read-only viewers cannot use Ask or
mutate the desk; researchers cannot approve jobs or access operations; stewards
can operate collection workflows; admins retain the pilot's complete authority.

## Honest readiness state

Identity and roles are necessary but not sufficient for multi-user service.
The capability document therefore reports:

```json
{
  "tenancy": {
    "identity_aware": true,
    "object_isolation": false,
    "multi_user_ready": false
  }
}
```

Do not enable external multi-user access while `object_isolation` is false.
Chat sessions, Discover intents, Synthesis threads, pins, campaigns and job
views still need persisted `owner_id` / `workspace_id` fields plus authorization
checks on every get, list and mutation operation.

## Required next slice

1. Choose the production identity provider (OIDC/SAML or an authenticated
   institutional reverse proxy). The token-digest file is a deployment-neutral
   bridge, not the final sign-in UX.
2. Add a workspace and membership store with immutable ids and role grants.
3. Migrate stateful records with `owner_id`, `workspace_id`, and sharing policy.
4. Enforce ownership in storage methods, not only frontend filters.
5. Separate shared catalog records from workspace Library possession.
6. Add cross-user negative tests proving that guessed object ids return 404/403.
7. Add audit events containing actor, workspace, action, object and decision.

## Scale model

The intended tenancy hierarchy is:

```text
institution
  └── workspace / laboratory
        ├── members + roles
        ├── Library possession and derived assets
        ├── Discover intents and acquisition decisions
        ├── Synthesis threads and approvals
        └── usage, quota and audit history
```

Catalog/source metadata may be globally readable after authentication. Library
possession, licensed entitlements, conversations, drafts, job authority and
derived outputs are workspace-scoped by default. Explicit sharing must be a
grant, never an inference from knowing an object id.
