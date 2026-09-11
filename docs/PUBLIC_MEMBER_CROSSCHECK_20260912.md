# Research Drive public-member closure cross-check — 2026-09-12

This document reviews the unpublished public-member candidate only. It does not authorize deployment.

## Candidate under review

Frontend: `Spectating101/yzu-cluster` @ `56caa25f415795c99132e905c34bf21bb600c175`

Backend: `Spectating101/research-drive-private` @ `dc2cc59f4f778e52732fe718cba5a5b222b04689`

Live RC3 remains separate until an explicit host promotion.

## What is already correct

- `/library/desk/login` is the narrow Cloudflare Access upgrade path.
- Cloudflare identities are JWT-verified and mint restricted `public_member` sessions.
- `public_member` has shared evidence + Ask/private-work authority, not collection/approval/operations authority.
- Non-operator HTTP personalization is bound to the authenticated principal email; browser-supplied email cannot replace it.
- Invitation codes remain a pilot fallback rather than self-service onboarding.
- The frontend makes verified email sign-in primary when the backend advertises it.

## Closure findings

### A. Signed-in thin Profile is not yet fully true

A Cloudflare `public_member` does not have `view_faculty_profile`, so current `App.reloadProfile()` returns `{unknown: true}` without a personal identity record. `ProfilePage` then renders a sign-in-oriented empty state even though the researcher is already signed in.

Required behavior:

- a signed-in `public_member` must see their authenticated display name/email;
- absence of scraped faculty research facts must render as `research context not set`, not `sign in`;
- no faculty record is required to use Ask/Synthesis/private saved work;
- do not grant collection/operations authority to solve a presentation problem.

Recommended implementation: construct an honest thin client profile from the authenticated principal when faculty-profile authority is absent. Do not broaden `/library/faculty/profile` unless separately justified.

### B. Pilot/Kong fallback must be explicit-demo only

The frontend still contains automatic fallback from an unknown full `member` profile to `PILOT_PREVIEW_EMAIL`. That is acceptable only for an explicit showcase mode.

Required behavior:

- unknown named users stay unknown/thin;
- never replace their identity with another faculty record;
- `PILOT_PREVIEW_EMAIL` may be used only behind explicit demo intent such as `?demo=1` / `Use EXAMPLE`.

### C. Synthesis UI must match `public_member` authority

Current auth permits normal Synthesis thread work through `use_ask`, but `/library/synthesis/threads/.../execute` and `/collect-missing` require the stronger collection boundary. `SynthesisPage` currently treats `canUseAsk` as sufficient to expose the whole studio and automatically requests bounded Preview after proposal acceptance.

Required behavior for `public_member`:

- create/read/update private Synthesis threads: allowed;
- Ask/reasoning/evidence mapping/reviewable proposal: allowed;
- collection, job creation, full execution, materialisation and approvals: denied unless the principal has the corresponding stronger permission;
- UI must not present an enabled action that is guaranteed to 403;
- accepting a proposal must not automatically invoke `/execute` when execution authority is absent.

Recommended frontend contract: pass an explicit `executionAllowed`/`canSubmitCollection` capability into Synthesis; keep reasoning available while disabling/annotating Preview/Build actions that require collection authority.

### D. Public-release preflight must reuse runtime Cloudflare validation

The new preflight currently considers Cloudflare configured when both environment strings are non-empty. Runtime `configured_access()` is stricter and rejects malformed/non-Cloudflare team domains.

Required behavior:

- preflight must call/reuse `scripts.research_data_mcp.cloudflare_access.configured_access()` (or an exactly shared validator), not duplicate a weaker shell approximation;
- malformed team-domain/audience configuration must fail external-public preflight;
- PyJWT availability must still be checked before declaring verified-email login ready.

### E. Exact release evidence is still required

The box reported local counts, but GitHub currently has no exact-head check runs on these candidate SHAs. Also reconcile the previously reported `1,571 passed` backend run with the candidate report `1,366 passed, 9 skipped` by recording the exact pytest command, collection count and skip reasons.

The frontend candidate is eight commits beyond live `f76e2bfb...`, not an auth-only delta. Certify the entire candidate, including its Discover/visual/boot fixes, under one exact release identity.

## Acceptance matrix

### Guest
- shared Library/Discover work;
- cannot Ask, create Synthesis private work, collect, approve or inspect operations.

### Public member (verified email)
- identity survives logout/login and restart;
- Profile shows own authenticated identity and an honest thin research-context state;
- Ask works and saved sessions are owner-isolated;
- Synthesis reasoning/private threads work;
- execution/materialisation/collection controls are absent or explicitly locked;
- cannot submit collection, approve jobs, inspect operations or retrieve another user's private state.

### Full member
- same personal identity guarantees;
- collection according to existing role;
- an unknown profile never inherits the pilot professor.

### Operator
- existing operational authority preserved;
- explicit demo preview remains possible only through deliberate demo controls.

## Two-account host acceptance

After code closure and Cloudflare configuration on a candidate host:

1. guest browse check;
2. researcher A email login;
3. verify `public_member` capabilities;
4. create Ask and Synthesis private state;
5. verify prohibited mutation/action boundaries;
6. sign out;
7. researcher B email login;
8. prove A's Ask/Synthesis/profile state is not visible;
9. restart service;
10. repeat principal/session/private-state checks;
11. confirm registry rows/fingerprint and canonical archive remain stable;
12. only then consider promotion.

## Division of responsibility

ChatGPT/repository review can own code/contract review, regression criteria, exact-SHA comparison and review branches.

The OptiPlex/box is required for Cloudflare secrets/policy configuration, live environment inspection, host-only browser tests, systemd/restart checks, exact test commands on the candidate checkout, promotion and DNS/deployment actions.

Do not reopen general YZUC product development from this document.