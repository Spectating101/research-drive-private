# Discover visual states — composition authority

**Status:** CURRENT Discover composition authority  
**Date:** 2026-08-13  
**Incorporated by:** [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md)  
**Truth rules (not composition):** [`DISCOVER_ADAPTIVE_FREEZE_2026-07-28.md`](DISCOVER_ADAPTIVE_FREEZE_2026-07-28.md)

The July 15 Discover CLI (`WHAT EVIDENCE ARE YOU LOOKING FOR?` / `BEST FIT` / `OTHER MATCHES`) is withdrawn. Git history retains it. Do not open, cite, or rebuild it.

Composition is the rendered family below — not a markdown wireframe, not live `:8765` (`42d5b100` / `63de3d05`), and not visual-pass HEAD if that HEAD has drifted (it currently splits **Request collection** / **Add to collection**; the approved row has one label).

## The family

| State | What it proves | Harness | Capture | Viewports | Row baseline |
|---|---|---|---|---|---|
| `discover-05-offerings` | Default result list: source · title · description · coverage · grain · route · **Add to collection**. No selected-candidate centre takeover. | `e2e/program-visual-states.spec.js` | `docs/screenshots-review/program-visual-states/discover-05-offerings-{1280,1440,1920}.png` | 1280×800, 1440×900, 1920×960 | `dcfb06a9` — one mutation label |
| `discover-rail-selected` | **Canonical selected-result state.** Centre list stays; selected row remains visible; rail interprets that offering. | same spec (`discover-rail-selected-1440`) | `docs/screenshots-review/program-visual-states/discover-rail-selected-1440.png` | 1440×900 | same |
| `acquisition-review` | **Add to collection** opens review over preserved results. Collection has not started. | `e2e/discover-adaptive-freeze-screenshots.spec.js` | `docs/status/generated/discover-freeze-2026-07-28/acquisition-review.png` | 1440×900 | same |

Hero frame if only one is shown: **`discover-rail-selected`**.

## Binding composition

```text
Search
  → compact ranked list (discover-05-offerings)
  → select one row; list stays put
  → rail explains that exact offering (discover-rail-selected)
  → Add to collection
  → review modal; nothing starts yet (acquisition-review)
  → route choice / History
```

No selection: centre is the compact list; rail is “Choose an offering to inspect” plus query-level facts only — not generic aggregates, fake “already in your Library” skeletons, or “not established” filler.

Selected: same list; rail is What it is · runtime readiness · what is untested · one valid action. Action is **Add to collection** → review. Do not ship a competing **Request this evidence** / **Request collection** primary.

## What prose may still define

[`DISCOVER_ADAPTIVE_FREEZE_2026-07-28.md`](DISCOVER_ADAPTIVE_FREEZE_2026-07-28.md) keeps interaction and truth rules that cannot be drawn: Explore \| History only, no Search/Ask toggle, Add never silently collects, History preserves the decision chain, prohibited fabricated access/coverage/cost/readiness.

Its own CLI drawings are not composition authority.

## Regeneration

Re-render **these three states** from the harness when composition is disputed. Do not regenerate the 203-capture corpus against drifted HEAD and call that the design record.
