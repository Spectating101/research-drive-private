# Discover Local Sufficiency — visual notes

## Backend comparison-contract audit (summary)

Inspected Sharpe-Renaissance `/library/discover`, `/library/search`, registry, and Composer soft hits.

| Signal | Authority | Sufficiency use |
|---|---|---|
| `dataset_id` / `doi` / `candidate_key` | Registry + stamp | **Exact local match** |
| `source_system` / `source` / `source_id` | Registry / row | Related / partial basis |
| `join_keys` | Registry | Related / partial basis |
| `grain` | Registry (stripped from discover HTTP; available via `/datasets`) | Named partial gap when both sides present |
| `coverage` / temporal fields | Sparse on registry; present on some discover fixtures | Named partial gap when both sides present |
| `score` / `score_pct` / title tokens | Lexical rank | **Not used** |
| `index_miss` / `weak_match` / `strong_local_hit` | Query↔catalog soft miss | **Not** candidate sufficiency |
| Explicit `equivalent_dataset_id` / backend `local_comparison` | Optional | Exact / likely-equivalent only with explicit basis |

**Honestly supportable now:** exact-local, partial-local, related-local, no-local-alternative, comparison-unknown.

**Intentionally unsupported:** `likely-equivalent` (no canonical family/series equivalence contract). Screenshot **06 omitted**.

No backend commit in this pass — comparison runs client-side against the lab `/datasets` catalog via `discoverSufficiency.js`. Optional `row.local_comparison` is accepted when present.

## Design direction

`LAB COVERAGE` is a comparison decision band, not another nested status card or a second action surface.

- Exact local match hands the primary usability decision to the canonical local asset while preserving the external candidate identity.
- Partial coverage shows the known dimension as an explicit `In lab → Candidate` comparison.
- Related assets are named once and never upgraded to equivalent.
- The coverage block contains no duplicate Open/Inspect button; the Evaluation action bar remains the single command authority.
- External source evidence remains available below the comparison, while exact-local uncertainty follows the local asset's readiness context.

### Mobile Focus action hierarchy

The mobile action region represents one decision rather than wrapping the desktop action inventory.

- There is one primary action authority in the DOM and it is full-width at mobile width.
- Desktop keeps explicit secondary buttons.
- Mobile exposes at most one context-aware secondary action; remaining secondary actions are available from a `More actions` menu.
- Exact local match prefers `Inspect external source` as the visible secondary because `Open local dataset` already owns the primary decision.
- Partial/related coverage prefers the local asset action as the visible secondary.
- Lifecycle-owned states do not surface a competing secondary beside the lifecycle primary; additional actions remain in the overflow menu.

### Mobile Focus shell contract

The responsive failure was structural rather than cosmetic.

- `.rd-v2-eval-workspace-shell` had layout authority in CSS but was not rendered by the workspace variant, so the action-layout selectors were dead.
- Discover candidate selection also triggered the legacy InspectorRail mobile auto-open effect. The hidden inspector state caused the shell to reserve up to `560px` for the old bottom-sheet model even while Focused Evaluation owned the main canvas.
- Workspace now renders its shell explicitly.
- Discover Detail selection keeps the mobile inspector collapsed; only explicit `Ask` opens it.
- Closed Discover Focus uses the `no-rail` viewport contract and scrolls Evaluation internally above the action region.

Measured acceptance at `390×1200`, for exact-local and partial-local Focus:

- document width `390`; no horizontal overflow;
- document height `1200`;
- shell height `1200` with overflow hidden;
- inspector `rd-v2-rail-collapsed` and `display:none` while Detail owns Focus;
- `.yzu-main` bottom padding `0px`;
- Evaluation workspace height `934px`;
- action region `y=1092 → 1200`, height `108px`;
- primary action `x=12 → 378`;
- secondary row `x=12 → 378`.

The regression suite locks both geometry and interaction ownership: selecting a candidate must keep Focus/no-rail; tapping `Ask` must intentionally open the inspector.

## Screenshots

| # | State | Evidence | User decision | Primary action | Claim not made |
|---|---|---|---|---|---|
| 01 | Browse exact | same `dataset_id` | Use lab asset | Open local (on focus) | Equivalence from title |
| 02 | Browse partial | same source family + temporal gap | Inspect gap / maybe acquire | Source actions | Exact match |
| 03 | Browse related | same source + join keys, no gap | Inspect related | Source actions | Equivalent |
| 04 | Browse none | source identity searched, no lab hit | Acquire path remains | Source actions | “Does not exist in lab forever” |
| 05 | Focus exact | canonical id | Use query-ready lab asset | Open local dataset | Need to collect |
| 07 | Focus partial temporal | `2018–2024 → 2015–2026` | Understand time gap | Probe/Add remain | Exact / equivalent |
| 08 | Focus partial grain | `issuer_week → issuer_day` | Understand grain gap | Probe/Add remain | Equivalent |
| 09 | Focus related | same family | Inspect related | Inspect secondary | Equivalent |
| 10 | Focus none | completed empty compare | Ordinary acquire | Probe/Add | Unknown |
| 11 | Focus unknown | thin URL-only hit | Do not treat as none | Ordinary | No alternative found |
| 12 | Partial + Ask | Ask support rail | Ask with structured context | — | Related→Equivalent upgrade |
| 13 | Running + partial | lifecycle overrides | Track running job | Lifecycle primary | Sufficiency decides collect |
| 14 | Back | browse line preserved | Continue browsing | — | — |
| 15–18 | Tablet/mobile | same states | Same decisions | Responsive Focus hierarchy | Desktop action wrapping |

## Scope

- Composition not redesigned
- Lifecycle / Evaluation / D0 / D1 semantics unchanged
- Mobile Focus action hierarchy and viewport ownership are completed in this responsive slice
- Broader tablet/mobile Browse and page-shell responsive polish remains
