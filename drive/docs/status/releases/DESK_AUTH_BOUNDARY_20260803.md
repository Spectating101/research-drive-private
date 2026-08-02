# Desk authorization boundary — 2026-08-03

## Incident

The deployed desk treated a same-origin browser request as authentication.
Every anonymous visitor to a public desk is same-origin, so the session endpoint
minted a privileged deterministic cookie. A browser without credentials reached
protected GETs and executed the safe-approval sweep.

Public tunnels were stopped and disabled. The Tailscale front door remained
available while the corrected boundary was built on a clean convergence branch.

## Boundary

Public:

- static UI files;
- `/healthz`;
- `/library/desk/session` (minting has its own gate);
- `/library/desk/capabilities` (booleans only; no identity or infrastructure).

Authenticated:

- `/health`, `/datasets`, `/query`;
- every `/library/*` route not listed above;
- every `/yzu/*` route;
- all mutations and downloads.

Browser sessions are `v2.<issued_at>.<nonce>.<signature>`. Validation checks the
signature and lifetime on the server. Deterministic `v1` cookies are rejected.
Rotating `YZU_DESK_ACCESS_TOKEN` revokes every outstanding session.

`DESK_SESSION_BOOTSTRAP_HOSTS` is a Tailscale network-trust convenience, not a
public authentication mechanism. `DESK_PUBLIC_ORIGINS` is ignored for authority.

## Frontend contract

The UI reads `/library/desk/capabilities` before presenting the desk. A trusted
internal browser bootstraps once and retries a protected request. A browser that
cannot authenticate receives a locked shell with no research data or write
controls and may provide a reviewer/operator token explicitly.

Backend authorization remains authoritative; frontend gating is not a security
control by itself.

## Deployment acceptance

Record status codes only; never place tokens or response bodies containing PII
in evidence.

```text
anonymous GET /library/desk/capabilities  -> 200, authenticated=false
anonymous GET /library/faculty/profile    -> 401
anonymous GET /library/credentials/profiles -> 401
anonymous GET /yzu/workers                -> 401
anonymous GET /datasets                   -> 401
trusted POST /library/desk/session        -> 200
session GET /library/desk/capabilities    -> 200, authenticated=true
session GET /datasets                     -> 200
legacy v1 cookie GET /datasets            -> 401
```

Before restarting:

1. keep every public tunnel unit disabled;
2. rotate the desk token and synchronize its compatibility mirror;
3. set the exact Tailscale host in `DESK_SESSION_BOOTSTRAP_HOSTS`;
4. build UI and backend identity from the exact release SHAs;
5. preserve the prior unit and environment files for rollback.

Public exposure requires a separate reviewer surface and a new security review.
