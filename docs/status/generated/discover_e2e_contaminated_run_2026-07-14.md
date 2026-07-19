# Discover E2E contaminated run — 2026-07-14 (DISCARD)

**Status:** Discarded as product evidence  
**Recorded:** 2026-07-14  
**Operator:** Cursor Grok session (FE↔BE integration)  
**Companion contract:** [`../../DISCOVER_E2E_AUTHORITY_AUDIT.md`](../../DISCOVER_E2E_AUTHORITY_AUDIT.md)

## Identity (what was intended vs what was served)

| Field | Value |
|---|---|
| Intended repo | `/home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/Sharpe-Renaissance` |
| Intended branch tip (approx) | `feat/discover-fe-be-integration` @ `9cb1310` (FE↔BE commit); later local Discover UI cleanup uncommitted |
| `YZU_DESK_URL` | `http://127.0.0.1:5179` |
| **Actual Vite root** | `/tmp/yzu-discover-routes` (Codex Terra tree) |
| BrowsePage size mismatch | temp ~605 lines vs intended tree ~1100+ lines |
| Parallelism | Multiple Playwright processes manipulating Discover; `reuseExistingServer: true` |
| Backend | Not certified as part of this discarded run |

## Harness notes

- Playwright default port/baseURL: `:5179` (`playwright.config.js`).
- `webServer.reuseExistingServer: true` attached to the foreign Vite.
- Timeouts of **120s** on `innerText` / `fill` are compatible with “expected DOM never existed / page stolen,” not with slow search product logic.

## Observed discover-loop outcomes (not product evidence)

| Test (as observed) | Failure shape | Pre-classification (Codex) |
|---|---|---|
| suggested card → SERP | 120s timeout (`innerText`) | ENVIRONMENT + later clean CURRENT |
| search status settles | missing `.rd-v2-discover-search-summary` / no `\d+ result` | ENVIRONMENT / SELECTOR DRIFT |
| query preserved across Review queue | 120s timeout | ENVIRONMENT / MIXED |
| Activity job owns rail | fail ~12s | **LEGACY EXPECTATION** (title may already be retargeted in tree; treat Activity ownership as legacy) |
| header pending → Activity | 120s timeout | **LEGACY** if Activity; Explore-queue form is CURRENT after rewrite |
| Explore \| History stable modes | fail ~16s | CURRENT critical (after clean run) |
| History trail + rail | 120s timeout | CURRENT critical (after clean run) |
| History round-trip shareable search | 120s timeout on `fill` | CURRENT direction (after clean run) |
| Activity summarizes “Awaiting” | missing `discover-activity-summary` | **LEGACY EXPECTATION** |
| dataset-driven research context | missing `discover-research-context` | CURRENT critical (after clean run) |

`e2e/v2-discover.spec.js` did not finish cleanly in the contaminated run.

## Actions taken

1. Stopped the contaminated Playwright parent tree.
2. Left foreign `/tmp` Vite alone.
3. Made **no** product fixes from these reds.
4. Documented environment + contract-drift in `DISCOVER_E2E_AUTHORITY_AUDIT.md`.

## What this run is allowed to mean

```text
Allowed:   proof that the harness can attach to the wrong tree
Allowed:   proof that Activity-era assertions still exist in the suite
Forbidden: claim that FE↔BE integration is broken
Forbidden: claim that Explore|History product composition failed
Forbidden: drive BrowsePage / API patches from these artifacts
```
