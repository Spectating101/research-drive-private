# Research Drive public account model

This document defines the account boundary for researchers who are not present in the YZU faculty registry.

## Core rule

**Authentication is not a faculty-registry operation.**

A public Research Drive account is created dynamically from a verified identity provider session (currently the Cloudflare Access bridge). Research Drive does not create or store a local password, and a new account does not require a row in `yzu_cm_faculty_registry.json`.

The identity provider establishes:

- stable principal id;
- verified email;
- display name when supplied;
- the fixed restricted role `public_member`.

Research Drive then issues its own expiring HttpOnly desk session for that principal.

## Three separate authorities

| Authority | Meaning | Who may change it |
| --- | --- | --- |
| Account identity | principal id, verified email, display name | identity provider / authenticated session only |
| Research profile | user-confirmed research context | that authenticated researcher |
| Role / permissions | public_member, member, operator | server/operator configuration only |

A personal profile update can never change account email, principal id, role, or permissions.

## First sign-in

A first-time verified researcher requires no provisioning step inside Research Drive.

```text
verified email login
  -> stable public_member principal
  -> empty principal-scoped research profile
  -> generic cold-start prompts
  -> private Ask / Synthesis trail
```

The profile is stored only when the researcher chooses to save research context. An empty profile is a valid state, not an error and not a reason to substitute a faculty example.

## Personal research profile

Endpoint:

```text
GET  /library/profile
POST /library/profile
```

Allowed user-confirmed fields:

- academic stage;
- discipline;
- current project;
- research topics;
- methods;
- data interests.

The storage key is derived from the authenticated `principal_id`, not from a browser-supplied email. Two researchers therefore receive different profile records even when they use the same browser at different times.

On a production host with `YZU_RUNTIME_DRIVE_ROOT` configured, the profile is stored under the release-independent runtime authority:

```text
$YZU_RUNTIME_DRIVE_ROOT/data_lake/research_drive/profiles/<sha256(principal_id)>.json
```

A repo-local `data_lake/research_drive/profiles/` location is used only as the development/test fallback when no runtime drive is configured. Promoting an immutable backend checkout therefore must not strand or reset production profiles.

The file contains research context only. It is not an authentication database.

## Cold start and personalization

The personal profile compiles into the existing Research Drive research-context shape so Ask can use user-confirmed topics, methods and projects without inventing a faculty record.

Seed modes are:

- `personal_profile` — user has saved research context;
- `faculty_profile` — a real same-email faculty record exists and no personal override is needed;
- `yzu_profile_fallback` — verified YZU identity with little or no recorded context;
- `generic_cold_start` — any other verified researcher with no saved context.

A public member does not need a connected cloud account. Connected storage remains a stronger member/operator capability.

## Public-member authority

A normal self-service researcher may:

- browse shared Library and Discover evidence;
- use Ask;
- keep private Ask / Synthesis state;
- read and update only their own research profile;
- run the bounded, non-materializing Synthesis Preview for an accepted method revision.

A normal self-service researcher may **not** gain, through account creation or profile editing:

- collection submission;
- materializing a Synthesis output or creating its execution job;
- job approval;
- worker or operational controls;
- connected-storage authority reserved for lab members;
- operator access;
- another researcher's private work.

Role elevation is an administrative decision outside the profile API.

## Synthesis authority split

Synthesis reasoning and bounded Preview are personal research work. The dedicated Preview path runs an accepted deterministic recipe only on bounded input bytes and creates no collection job, dataset, registry row, or approval.

Full execution remains a separate authority boundary. A `public_member` can preserve the thread and Preview receipt but must become a lab `member` before Research Drive may create the materializing execution/approval job.

## Faculty registry

The faculty registry remains an optional evidence source for known faculty. It may enrich a same-email researcher's profile with recorded scholarly context, but it is neither the account directory nor the authority for login.

No unknown user may inherit the example/pilot faculty identity. Example identity is demonstration-only and must require explicit demo intent.

## Sign-out, profile clearing, and account deletion

Signing out clears the local desk session; it does not delete the researcher's saved profile or private research trail.

`POST /library/profile` with:

```json
{"clear_profile": true}
```

clears user-confirmed research context only. It does not delete the verified identity or change role.

A future full account-deletion workflow would need to enumerate all principal-owned objects (profile, Ask sessions, Discover intents, Synthesis threads, connected-account metadata where applicable) and should be implemented as a distinct destructive operation. This release does **not** silently equate “clear profile” with “delete all my data.”

## Release acceptance

Before promoting this account model:

1. Researcher A signs in and receives `public_member`.
2. A's empty profile is honest and usable.
3. A saves research context and Ask sees that context.
4. A can run bounded Synthesis Preview but cannot create a materializing execution/collection job or approve jobs.
5. A signs out.
6. Researcher B signs in and cannot see A's profile, Ask history, Discover intents, or Synthesis threads.
7. Restart the service and repeat A/B reads; A's profile must survive from the runtime drive authority.
8. Shared registry/archive identity remains unchanged.

Account creation is complete only when identity, profile isolation, private-work isolation, runtime persistence, and the Synthesis authority split all pass on the exact release pair.
