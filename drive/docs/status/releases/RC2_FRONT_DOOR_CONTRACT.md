# RC2 front door — Tailscale-internal same-origin contract

**Release posture:** internal only  
**Public UI authority:** `Spectating101/yzu-cluster@794c1f3035e0a158e4f9b401e0686609cab1c6b3`  
**Private runtime authority:** merge commit of this change  
**Out of scope:** public gateway, faculty SSO, query-ready promotion, Synthesis expansion, RC1 redesign

## Architecture

```text
authorized browser
→ Optiplex Tailscale IP:8765
→ private research query server
   ├─ non-API GET: public yzu-cluster dist/
   ├─ /health, /datasets, /library, /query, /yzu, /agent: private desk API
   └─ /library/chat/stream: Composer/MCP NDJSON stream
→ existing controller :8780
→ Windows worker
```

The public repository remains the researcher-facing UI authority. The private repository remains the API, Composer/MCP, controller, registry, archive and secret authority. The front door does not copy public source into private; it serves the built public `dist/` directory through the private server.

## Security posture

- Bind `:8765` to the Optiplex Tailscale IP, never `0.0.0.0` for this release.
- Keep the existing controller `:8780` Tailscale-only.
- Set `YZU_DESK_ACCESS_TOKEN`; material POST routes require `X-Desk-Token` or Bearer auth.
- Store secrets in `~/.config/research-drive/front-door.env`, mode `0600`, outside git.
- No public reverse proxy, tunnel, TLS termination or CORS expansion is part of this release.

## Host prerequisites

- clean public checkout at the exact public authority SHA;
- private checkout at the merged private release SHA;
- Node/npm compatible with `package-lock.json`;
- Python environment already capable of running the private desk stack;
- Tailscale active on the Optiplex;
- user systemd available.

## Build

Create the host environment file:

```bash
mkdir -p ~/.config/research-drive
cp drive/config/optiplex-front-door.env.example ~/.config/research-drive/front-door.env
chmod 600 ~/.config/research-drive/front-door.env
# edit values; never paste secret values into evidence
```

Build the public authority:

```bash
set -a
source ~/.config/research-drive/front-door.env
set +a
bash drive/scripts/research_query_engine/build_optiplex_front_door.sh
```

The build refuses a mismatched public SHA or tracked dirty public checkout and writes `dist/research-drive-build.json` with both authority SHAs.

## Install and start

```bash
bash drive/scripts/research_query_engine/install_optiplex_front_door_systemd_user.sh --start
systemctl --user status research-drive-front-door.service --no-pager
journalctl --user -u research-drive-front-door.service -n 200 --no-pager
```

The service runs the private server with:

- `YZU_DESK_HOST` / `YZU_DESK_PORT`;
- public `dist/` as `YZU_DESK_STATIC_DIR`;
- configured registry path;
- `--serve-ui` fail-fast validation.

## Acceptance

From an authorized Tailscale client, record HTTP status and sanitized response identity for:

```text
GET  /
GET  /research-drive-build.json
GET  /health
GET  /health?live=1
GET  /datasets
GET  /library/desk/resources?live=1
GET  /library/live-identity?dataset_id=<known-smoke-dataset>
POST /library/chat/stream
```

Required claims:

1. One URL serves both the real UI and real private API.
2. `/research-drive-build.json` reports the approved public and private SHAs.
3. The known smoke asset returns real `dataset_id`, `registry_id`, `manifest_id`, `job_id`, `run_id`, `attempt`, `worker_id` and `readiness` where available.
4. `registered` remains distinct from `query_ready`.
5. Browser network requests do not target GitHub Pages, localhost on the client, or a second mock API.
6. An invalid desk token is rejected for a protected POST route.
7. The service restarts successfully and remains bound only to the Tailscale address.

## Grok evidence package

Return only sanitized evidence:

```text
PRIVATE_SHA:
PUBLIC_SHA:
FRONT_DOOR_URL:
BINDING:
SERVICE_STATUS:
BUILD_IDENTITY:
HEALTH:
LIVE_HEALTH:
KNOWN_DATASET_ID:
LIVE_IDENTITY:
CHAT_STREAM:
INVALID_TOKEN_RESULT:
RESTART_RESULT:
ROLLBACK_READY:
KNOWN_FAILURES:
```

Do not mutate queues, registries, tokens or firewall policy outside the approved deployment steps.

## Rollback

```bash
systemctl --user disable --now research-drive-front-door.service
```

If the installer reported a previous unit backup, restore it and run:

```bash
systemctl --user daemon-reload
```

Rollback does not alter the existing controller, worker, registry, archive or RC1 release.

## Exit criterion

> The Tailscale-authorized browser opens one Optiplex URL, receives the real public UI, and obtains live private identity for a known registered smoke asset without mocks or a manual CLI bridge.

Golden-path surface reconciliation begins only after this criterion is green.
