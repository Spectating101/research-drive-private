# Account creation implementation — 2026-09-12

Base candidate: `dc2cc59f4f778e52732fe718cba5a5b222b04689`

Review branch: `review/public-member-closure-20260912`

This patch closes the backend half of general researcher onboarding without changing the live RC3 service.

## Implemented

- verified identity remains Cloudflare / configured principal authority;
- no local password database or self-service role creation;
- `public_member`, `member`, and `operator` receive `manage_research_profile`;
- guest does not;
- principal-scoped `GET /library/profile` and `POST /library/profile`;
- lazy empty profile for first-time researchers;
- user-confirmed academic stage, discipline, current project, topics, methods and data interests;
- account identity, role and permissions are rejected if supplied to the profile API;
- personal profile storage keyed by a hash of authenticated `principal_id`;
- personal context compiles into the existing research-profile shape used by Ask;
- research seed now supports `public_member` cold starts without faculty records or connected storage;
- public-member seed explicitly reports no collection authority;
- external-public preflight now calls the same strict Cloudflare `configured_access()` validator as runtime;
- tests cover A/B profile isolation, identity immutability, cold start, and permission separation.

## Deliberately not implemented

- local password signup;
- self-service promotion to `member` or `operator`;
- collection/worker/approval rights for public members;
- automatic cloud-account connection;
- full account deletion across all private object stores;
- live deployment or Cloudflare Access configuration.

## Host acceptance still required

1. Configure Cloudflare Access only for `/library/desk/login` on a candidate host.
2. Researcher A signs in, saves profile context, uses Ask/Synthesis, signs out.
3. Researcher B signs in and cannot read A profile or private research work.
4. Restart services and repeat isolation reads.
5. Verify registry/archive identity and count are unchanged.
6. Run exact-head tests and record command, collected count, passes/skips and skip reasons.

Do not promote this branch solely because repository tests pass; the identity-provider and persistence checks are host authority.
