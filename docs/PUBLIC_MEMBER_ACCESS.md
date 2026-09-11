# Research Drive public member access

Public browsing and personal research are deliberately separate authorities.

| Visitor | Library / Discover | Ask / saved work | Collection / approval |
| --- | --- | --- | --- |
| Guest | yes | no | no |
| Public member | yes | yes | no |
| Member / operator | yes | yes | role-gated |

## Launch identity path

The public launch should use the existing Cloudflare Access bridge on only
`/library/desk/login`. Configure an Access application for that path with an
email one-time-pin or another approved identity provider, then set:

```text
DESK_CLOUDFLARE_ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com
DESK_CLOUDFLARE_ACCESS_AUD=<application-audience>
```

The backend verifies the Access JWT issuer, audience, signature, expiry,
subject, and email. A successful login becomes an expiring, restricted
`public_member` session. The email does not need to appear in the faculty
profile registry; an unknown researcher receives a valid thin/cold-start
profile rather than another faculty member's identity.

The rest of the site must remain outside the Access application so guests can
browse the shared Library and Discover estate.

## Invite-code fallback

Individually issued member codes remain useful for a private pilot. They are
not self-service onboarding. A public release without Cloudflare Access now
fails preflight unless the operator explicitly sets:

```text
DESK_ALLOW_INVITE_ONLY_PUBLIC_LAUNCH=1
```

That acknowledgement documents an intentionally invite-only launch; it does
not weaken runtime authorization.

## Required acceptance

1. Open the public hostname without a session: Library and Discover work.
2. Choose **Sign in** and complete verified email login.
3. Confirm the returning session is `public_member` and can use Ask/Synthesis.
4. Confirm the same session cannot submit collection, approve jobs, view
   operations, or retrieve faculty-only state.
5. Sign out and confirm the browser returns to guest browsing.
6. Sign in with a second email and prove saved Ask/Synthesis state is isolated.

## Inference provider

Identity and inference are independent. Production currently selects GitHub
Copilot explicitly through `DESK_COMPOSER_PROVIDER=copilot`; configured
Copilot account aliases are selected stickily per research session. A present
Cursor implementation or credential does not receive traffic while the
provider is explicitly set to Copilot.

