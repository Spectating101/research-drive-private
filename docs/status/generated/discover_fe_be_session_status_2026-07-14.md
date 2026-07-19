# Discover FE↔BE + E2E authority — session status (2026-07-14)

**Branch tip at FE↔BE push:** `feat/discover-fe-be-integration` @ `9cb1310`  
**Remote:** `yzu` → `https://github.com/Spectating101/yzu-cluster`  
**GitHub main authority tip (referenced):** `ec5d939` — `docs(ux): normalize current interface authority`  
**Note:** On this worktree, `UI_PRODUCT_AUTHORITY.md` / `UI_IMPLEMENTATION_PROGRAM.md` were present on disk as untracked copies aligned with main; they are now part of the documentation set for this effort.

## What landed in product (FE↔BE)

- Discover modes: Explore | History (prefer live `GET /library/discover/sources`, History via discover history + merge rules).
- Preview → `POST /library/discover/sources/preview` when available.
- Probe/collect pass `candidate_key`.
- Synthesis: GET miss → `found:false` (no auto-run); Build via explicit run; lazy synthesis imports.
- Trust badges: Synced / Cached / Demo / Offline / Unknown.
- Helpers/tests: `drive/src/v2/discoverAdapters.js`, unit adapters tests, synthesis read≠run test.

## What Terra added (Discover IA)

- `discoverMode.js` normalization (legacy aliases → Explore / focusAwaiting).
- In-Explore review strip (`discover-queue-strip`) instead of Activity workspace.
- Partial e2e retarget toward Explore queue.

## What Grok finished after Terra interrupt

- Removed dead `showActivity` paths.
- Explore search runs when mode is `explore` (not only legacy `search`).
- Review queue / header pending → `onOpenReviewQueue` / `openDiscoverAwaiting`.
- Unit tests for discoverMode + adapters green.

## Playwright

| Item | Status |
|---|---|
| Contaminated `:5179` / `/tmp/yzu-discover-routes` run | **DISCARDED** — see `discover_e2e_contaminated_run_2026-07-14.md` |
| Product fixes from that run | **None** (correct) |
| Contract-drift recognition | Documented — not all reds were “just environment” |
| Next gate | Clean report-only authority audit per `DISCOVER_E2E_AUTHORITY_AUDIT.md` |

## Documentation added/updated this pass

| Path | Role |
|---|---|
| `docs/DISCOVER_E2E_AUTHORITY_AUDIT.md` | Classification vocabulary + clean audit procedure + suite tables |
| `docs/status/generated/discover_e2e_contaminated_run_2026-07-14.md` | Discarded-run evidence record |
| `docs/UI_PRODUCT_AUTHORITY.md` §19 | Hierarchy entry for E2E audit contract |
| `docs/UI_IMPLEMENTATION_PROGRAM.md` | Discover E2E interpretation rule under Test gates |
| `docs/design/DISCOVER_LOOP_ANCHOR.md` | Historical redirect (Search\|Activity obsolete) |
| `e2e/v2-discover-loop.spec.js` / `e2e/v2-discover.spec.js` | Headers + LEGACY/MIXED annotations |

## Explicit non-actions (by design)

- No blind Discover E2E rerun in this documentation pass.
- No product patches driven by contaminated reds.
- Legacy Activity tests annotated, not yet deleted/skipped (rewrite belongs with the clean audit / re-anchor PR).


## Convergence update (feat/discover-main-converge)

Rebased strategy onto `yzu/main` @ `ec5d939` via worktree. Selective port:

- Kept main Discover browse/focus evaluation + sufficiency/lifecycle
- Added Explore|History modes, queue strip, discoverMode, History panel
- Added FE clients: discoverSources / discoverHistory / previewDiscoverSource
- Pending approvals open Discover Explore queue (not Resources-only)
- E2E authority audit docs + lean Explore|History loop

Donor Sharpe FE↔BE BE Python modules remain outside this FE-only GitHub main.
