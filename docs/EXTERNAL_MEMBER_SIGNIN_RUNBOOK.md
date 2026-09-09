# External member sign-in runbook

Research Drive has two deliberately different public states:

| Visitor | What they can do |
| --- | --- |
| Public guest | Browse the shared Library and Discover evidence. |
| Signed-in public member | Use Ask and keep private chat/Synthesis work. |

The public guest must never receive Copilot, saved research history, acquisition, or operator authority. A member must present either an individually issued code or verified provider identity; an email typed into the browser is not an identity proof.

## Supported external sign-in boundaries

The launch can use either secure member upgrade:

1. **Individual member access code** — an operator issues a distinct code to a named principal whose SHA-256 digest is held only in `DESK_PRINCIPALS_FILE`. The browser exchanges it once for a short-lived `HttpOnly` desk session and immediately discards the raw code. This is the practical route for an invite-based external launch with bounded Copilot capacity.
2. **Cloudflare Access** — the smoother SSO path for a larger launch. It can be enabled in parallel; it is not required when individual member codes are already configured.

Both resolve to the same restricted member role. Neither grants collection, approval, faculty-profile, or operator access.

### Issuing an invite code

Run this **on the host** as the operator account; it only stores a digest in the
private registry and prints the raw code once to that terminal. Deliver that
code through a private channel, never in a URL, source file, or support ticket.

```bash
python3 drive/scripts/research_query_engine/issue_desk_member_code.py \
  --file "$DESK_PRINCIPALS_FILE" \
  --principal-id researcher-001 \
  --display-name "Researcher" \
  --email researcher@example.edu \
  --write
```

The resulting role is `public_member`: it can use Ask and preserve its own
research trail, but cannot collect, approve, inspect faculty data, or operate
the desk. Run without `--write` first for a no-change validation.

## Cloudflare Access boundary

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

The release preflight intentionally refuses an `external-public` scope unless it finds Cloudflare Access configuration **or** at least one well-formed non-operator member access-code digest. This prevents launching a public desk whose UI promises member Ask but has no secure identity path.
