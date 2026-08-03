# Research Drive — visual closure freeze

**Status:** CURRENT FROZEN CROSS-PRODUCT VISUAL CLOSURE AUTHORITY  
**Date:** 2026-07-30  
**Authority:** Normative finishing appendix incorporated by [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md)  
**Scope:** Home, Library, Discover, Synthesis, Resources, Profile, Settings, Detail / Ask, desktop and mobile  
**Reviewed implementation:** `feat/platform-ui-convergence` at `e58d0d15a26dd1974d92021161ab9a9946c8c67e`  
**Purpose:** Preserve the completed product model and authorize only the bounded visual-completion work listed here.

This document does not replace the page-specific Discover, Library, Resources, Profile, Home, or Synthesis authorities. It freezes the converged product and closes the remaining cross-page visual gaps. If an older screenshot, fixture, test, component comment, or agent summary conflicts with this document and the page-specific authorities, it is not authority.

---

## 1. Frozen product composition

The following decisions are settled and must not be reopened without evidence from real use, accessibility testing, operational failure, or measurable workflow friction:

```text
Navigation
Home · Library · Discover · Synthesis · Resources · Profile · Settings

Application grammar
left navigation · centre research object · right Detail / Ask

Discover
one automatic composer
keyword → immediate index results
research question → same results + automatic assessment + seeded right-rail Ask
Custom strategy → compact readiness chrome + visual modal
Add to collection → acquisition review modal
Explore | History only

Synthesis
objective-first AI construction workspace
one durable research thread
Ask clarifies and grounds the objective
centre visualizes interpretation, proxies, method, decisions, build, and registered output
Library evidence in; verified registered evidence out

Truth boundary
completed ≠ archived / verified ≠ registered ≠ query-ready
Observed ≠ Proposed ≠ Unknown
no procurement, collection, approval, registration, or readiness is implied by preview
```

The visual language is also frozen:

```text
quiet parchment canvas
graphite navigation
forest accent
hairline evidence surfaces
compact inventory rows
one dominant conclusion or decision at a time
plain language before internal identifiers
```

Do not introduce:

- a `Search | Ask` toggle;
- a permanent Acquisition, Plan, Pipeline, or workflow page;
- a dashboard of statistic cards;
- a graph-first Synthesis canvas;
- a generic chat landing page;
- a permanent coverage-assessment band in Discover;
- another navigation destination;
- a second page-local AI composer;
- more cards merely to occupy empty space.

---

## 2. Current visual assessment

The reviewed build is design-complete and visually coherent. The remaining work is completion and polish, not redesign.

| Surface | Visual maturity | Frozen assessment |
|---|---:|---|
| Discover — populated results | 9 / 10 | High-tier; preserve composition |
| Custom dataset strategy | 9 / 10 | Strong visual reasoning artifact |
| Acquisition review | 8.5 / 10 | Clear and disciplined |
| Synthesis entry | 8.5 / 10 | Strong centre; stale rail copy remains |
| Ask rail | 8 / 10 | Strong answer state; weak working-state emphasis |
| Resources | 8 / 10 | Strong surface; collector vocabulary is ambiguous |
| Home | 7 / 10 | Calm but visually unfinished when activity is sparse |
| Library | 7 / 10 | Strong ledger; sparse branches need a useful next action |
| Settings | 7 / 10 | Clear, but connected state contradicts its controls |
| Profile | 5.5 / 10 | Read-only empty record rather than an actionable research-memory surface |
| Mobile comfort | 7 / 10 | Stable layout; rail trigger consumes too much working viewport |

Reference renders:

- `artifacts/release-visual/home-1440x900.png`
- `artifacts/release-visual/library-1440x900.png`
- `artifacts/release-visual/discover-1440x900.png`
- `docs/status/generated/discover-freeze-2026-07-28/results.png`
- `docs/status/generated/discover-freeze-2026-07-28/strategy.png`
- `docs/status/generated/discover-freeze-2026-07-28/acquisition-review.png`
- `artifacts/release-visual/synthesis-1440x900.png`
- `artifacts/release-visual/resources-1440x900.png`
- `artifacts/release-visual/profile-1440x900.png`
- `artifacts/release-visual/settings-1440x900.png`
- `artifacts/release-visual/feedback-ask-progress-1440x900.png`
- `docs/status/generated/discover-freeze-2026-07-28/mobile-results.png`

---

## 3. Authorized visual closure work

These corrections are required before calling the cross-product interface visually complete. They must be implemented without changing the frozen composition.

### VC-1 — Make Profile actionable

Current failure:

```text
Memory       No specialties, tracks, or methods on file.
Linked       None yet
Suggested    —
```

There is no visible way to improve the research memory even though it affects Discover, Ask, and Synthesis.

Required correction:

```text
Research memory
No research direction saved.
[Add research focus]

Library connections
No evidence linked to this profile.
[Find relevant Library assets]

Suggested
Suggestions appear after a research focus is saved.
```

Add one primary `Complete research memory` or `Edit research memory` action. State concisely that the memory affects Discover ranking, Ask context, and Synthesis constraints. Do not add a gamified completion score.

### VC-2 — Reduce the mobile rail obstruction

The wide `Show Detail · Ask` grip plus bottom navigation consumes too much of a 390 × 844 viewport and covers useful result content.

Required correction:

- preserve the mobile Detail / Ask sheet;
- reduce its closed trigger to a compact, minimum-44px contextual control;
- do not show a full-width dormant grip when there is no meaningful selected object;
- keep bottom navigation stable;
- ensure content can scroll fully above fixed controls.

### VC-3 — Keep Settings actions consistent with state

Current contradiction:

```text
This browser     Connected
[Connect browser] [Disconnect]
```

Required correction:

- when connected, remove the primary `Connect browser` action;
- optionally show a quiet `Reconnect` action only when useful;
- keep `Disconnect` visually secondary and clearly destructive;
- remove `Use EXAMPLE (Kong)` from production presentation or gate it behind an explicit demo mode.

### VC-4 — Reconcile Resources collector language

The same screen currently exposes:

```text
3 / 12 joined
0 / 12 collectors
2 / 12 available
```

These may be different operational dimensions, but the interface does not explain that.

Required correction:

```text
12 registered · 3 connected · 2 idle · 1 running
```

Use only fields actually present. If a dimension is unknown, omit it or say `Not reported`; never infer it. The toolbar, capability card, and rail must use the same nouns and denominator.

### VC-5 — Teach Discover's automatic behavior visually

The one-composer model is correct but is currently explained mostly through prose.

Under the idle composer, add no more than two compact examples:

```text
Try a keyword          stablecoin
Ask a research need    What data can I use to study de-pegs?
```

The first demonstrates fast index search. The second demonstrates the same result surface with automatic assessment and seeded Ask. These are examples, not modes or tabs.

Also:

- collapse the large curated-source block to one quiet line when it has zero routes;
- fix singular grammar (`1 asset`, not `1 assets`);
- remove duplicate result/offering counts from the populated state;
- preserve `Custom strategy ready` as compact toolbar chrome.

### VC-6 — Align the Synthesis rail with the current product

Retire the stale `Choose a blueprint or custom pair` instructions.

The quiet Detail rail for a new project should explain:

```text
START      Describe the construct you need
ASK        Clarifies meaning and required evidence
GROUND     Checks Library inputs and defensible proxies
REVIEW     You approve the method before execution
OUTPUT     Archive, registration, and readiness remain separate
```

Also:

- add `Enter an objective to continue` beside the disabled start action;
- let registered-method names wrap or expose their full title accessibly;
- do not add another AI panel—the existing centre and right-rail Ask remain the interface.

### VC-7 — Make Ask work look active

The current Ask progress surface is too pale and resembles disabled content.

Required state hierarchy:

```text
✓ Gathering Library context
● Checking provenance and coverage
○ Composing grounded response
```

- current step: dark or accented;
- completed step: explicit check;
- future step: muted;
- keep the concise progress grammar and existing reduced-motion behavior.

### VC-8 — Give sparse Home and Library states one useful action

Home:

- when Recent trail is empty, show the existing profile-aware suggested-question treatment or one equivalent compact action;
- use the existing `HomeSuggestedAsks` / `homeSuggestedPrompts` contract rather than inventing dashboard content;
- remove `Recent assets appear as you work` from the sidebar when there are no real recent assets.

Library:

- preserve the folder-first ledger;
- when a branch is genuinely empty, provide a compact footer such as:

```text
Nothing else in this folder.
[Add files] [Add URL] [Find missing data]
```

- do not introduce a dashboard, tutorial card stack, or duplicated Discover catalogue.

---

## 4. Secondary polish after VC-1 through VC-8

These are worthwhile but must not delay the required closure:

1. Increase surface/background separation slightly for projectors and bright rooms.
2. Tighten excessive vertical padding in sparse Home, Profile, and modal states.
3. Replace remaining system-language with plain research language where meaning is unchanged.
4. Remove empty sidebar placeholders rather than decorating them.
5. Capture populated current renders for Discover and Synthesis; empty fixture captures materially understate the product.

No new components are required solely for these items.

---

## 5. Visual acceptance

The closure is accepted only when all of the following are rendered at 1440 × 900 and 390 × 844:

| Journey | Required proof |
|---|---|
| Home — sparse | useful start action, no dead sidebar placeholder |
| Library — sparse branch | clear branch state and bounded intake actions |
| Discover — idle | keyword and research-question examples, no empty oversized route block |
| Discover — populated question | results, seeded Ask, compact custom-strategy chrome, no duplicate counts |
| Discover — strategy | visual input → transform → output plan and explicit unknowns |
| Acquisition review | human-readable route, no raw identifier dominance, collection not started |
| Synthesis — new | objective, AI lifecycle cues, corrected rail, clear disabled-action reason |
| Synthesis — active | one thread across centre and Ask, open decision visible |
| Ask — working | current, completed, and future steps visually distinct |
| Resources | one coherent collector-state vocabulary |
| Profile — thin | actionable memory and Library-connection next steps |
| Settings — connected | state-consistent actions and no production example control |
| Mobile Discover | first result readable; fixed controls do not consume excessive viewport |

Acceptance is visual and behavioral. Unit tests and builds are necessary but do not prove comfort, hierarchy, or comprehension.

---

## 6. Handoff order

For the next agent:

```text
1. Read UI_PRODUCT_AUTHORITY.md completely.
2. Read this visual closure freeze completely.
3. Read the page-specific authority before modifying that page.
4. Implement VC-1 through VC-8 without changing navigation or composition.
5. Capture the acceptance matrix.
6. Review screenshots before changing tests to accept the result.
7. Amend this document if—and only if—rendered evidence proves a frozen rule defective.
```

Recommended implementation order:

```text
VC-3 Settings truth             XS
VC-4 Resources vocabulary       XS
VC-6 Synthesis rail             XS
VC-7 Ask progress hierarchy     S
VC-5 Discover first-use cues    S
VC-2 Mobile rail trigger        S
VC-1 Profile completion         S–M
VC-8 Sparse Home / Library      S
```

The design phase is closed. The next agent's job is disciplined visual completion, not another product redesign.
