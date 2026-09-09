# External member sign-in runbook

Research Drive has two deliberately different public states:

| Visitor | What they can do |
| --- | --- |
| Public guest | Browse the shared Library and Discover evidence. |
| Signed-in public member | Use Ask and keep private chat/Synthesis work. |

The public guest must never receive Copilot, saved research history, acquisition, or operator authority. A member must be authenticated by an identity provider; an email typed into the browser is not an identity proof.

## Supported external sign-in boundary

The release uses [Cloudflare Access application paths](https://developers.cloudflare.com/cloudflare-one/access-controls/policies/app-paths/) to protect **only**:

```text
https://<public-host>/library/desk/login
```

Keep the rest of the public host outside that Access application. This preserves public Library/Discover browsing while Cloudflare verifies a researcher only when they select **Sign in to Ask**.

After Access authenticates the user, the origin verifies Cloudflare's signed `Cf-Access-Jwt-Assertion`, creates an expiring, `HttpOnly`, `SameSite=Strict` Research Drive session, and redirects back to the same desk path. The session is always the restricted `public_member` role; Cloudflare identity can never mint local member or operator permissions.

## One-time Cloudflare configuration

1. In Cloudflare Zero Trust, enable Access and choose the identity provider researchers should use (Google, GitHub, Microsoft, or an institutional IdP).
2. Create a **Self-hosted** Access application for the actual public hostname and the exact path `/library/desk/login`.
3. Add an **Allow** policy for the intended launch audience. Do not use a bypass policy for this path.
4. Copy the application's **Audience (AUD) tag** and the Zero Trust team domain.
5. Add the following values to the private front-door environment file. Do not commit that file.

```bash
DESK_CLOUDFLARE_ACCESS_TEAM_DOMAIN=https://<team>.cloudflareaccess.com
DESK_CLOUDFLARE_ACCESS_AUD=<application-audience-tag>
DESK_PUBLIC_GUEST_HOSTS=<public-host>
YZU_DESK_RELEASE_SCOPE=external-public
```

The first two values are identity configuration, not browser secrets. Do not add a `DESK_ACCESS_TOKEN` to public client code or distribute operator/member tokens as a substitute for sign-in.

## Required staged proof

After reloading the staged service:

1. Open the public host in a clean browser context. It must become a `public_guest`, show shared Library/Discover, and show **Sign in to Ask**.
2. Select the sign-in action. Cloudflare should authenticate only `/library/desk/login` and return to the original desk location.
3. Confirm `/library/desk/capabilities` now reports `access: public_member`, `permissions.use_ask: true`, and no collection/approval/faculty/operations permission.
4. Send one read-only Ask request and reopen its saved history in the same session.
5. Confirm the public guest cannot call `/library/desk/warm`, `/library/chat/*`, `/library/advise/*`, or `/library/synthesis/threads/*`.
6. Sign out. The browser must return to a guest session that can browse but cannot Ask.

The release preflight intentionally refuses an `external-public` scope without the two Cloudflare Access values above. This prevents launching a public desk whose UI promises member Ask but has no secure identity path.
