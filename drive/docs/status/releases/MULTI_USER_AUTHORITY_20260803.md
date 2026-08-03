# Research Drive multi-user authority — 2026-08-03

## Boundary

Research Drive is upstream data infrastructure. Researchers and
external analysis systems may consume governed Library assets; Research Drive
does not inspect or depend on their models, strategies, portfolios or results.

## Current implementation

The desk now has a provider-neutral principal contract:

- stable principal id, institutional email and display name;
- role: `member` or `operator`;
- server-derived permissions returned by `/library/desk/capabilities`;
- `v3` signed browser sessions carrying only the subject identifier;
- optional `DESK_PRINCIPALS_FILE` entries authenticated by SHA-256 token digest;
- the legacy shared pilot token maps to one configurable operator principal;
- browser-supplied faculty email no longer overrides an authenticated user's
  institutional email.

Roles are enforced at the HTTP boundary. Members can research, use Ask and
submit collection requests, but cannot inspect operations or approve jobs.
Operators retain the pilot's operational authority.

## Honest readiness state

The lean multi-user boundary is now complete for private researcher work. The
capability document reports:

```json
{
  "tenancy": {
    "mode": "personal-work",
    "identity_aware": true,
    "personal_work_isolated": true,
    "multi_user_ready": true
  }
}
```

Ask sessions, Discover intents and Synthesis threads persist `owner_id` and
enforce it on every get, list and mutation operation. A guessed id is treated as
not found. Legacy ownerless records remain visible only to operators. Catalog,
Library and worker capacity remain shared platform objects.

## Required next slice

1. Replace token-digest sign-in with an identity provider when the pilot needs
   self-service accounts. The persisted principal id remains the ownership key.
2. Add explicit sharing only when real use requires collaboration on a private
   Ask session, Discover intent or Synthesis thread.
3. Add per-user audit views if operational review shows the existing platform
   activity stream is insufficient.

## Scale model

The intended scale model is deliberately small:

```text
Research Drive
  ├── shared source catalog + Library + worker capacity
  └── authenticated person
        ├── private Ask sessions
        ├── private Discover intents + collection requests
        └── private Synthesis threads
```

Catalog/source metadata and registered Library assets are shared after
authentication. Conversations and drafts are private by default. Job approval
is an operator action. Future sharing must be an explicit grant, never an
inference from knowing an object id.
