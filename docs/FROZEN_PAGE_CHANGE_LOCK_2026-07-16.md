# Research Drive — Frozen Page Change Lock

**Status:** ACTIVE CHANGE-CONTROL LOCK  
**Date:** 2026-07-16  
**Scope:** Discover, Library, Profile, Home, and Resources product composition  
**Purpose:** prevent converged faculty-facing pages from being casually reopened, reinterpreted, or redesigned during remaining Research Drive convergence

This change-control lock is used with [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md), [`RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md), and the page-specific frozen appendices.

The current lock state is:

```text
DISCOVER     HARD FROZEN
LIBRARY      HARD FROZEN
PROFILE      GROUNDED HARD FROZEN
HOME         HARD FROZEN — ITERATION 10
RESOURCES    HARD FROZEN — ITERATION 05
```

The remaining active product-design work is:

```text
PROFILE      bounded visual polish / thin-state completion inside the grounded freeze
PREVIEW      renderer / centre-overlay validation
SETTINGS     truthful low-complexity convergence
SYNTHESIS    final major product-design problem
```

Responsive, component, accessibility, implementation, and pixel convergence may continue across frozen pages only when page ownership and composition are preserved.

---

## 1. Discover — hard frozen

Normative authority:

- [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md)
- [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md)
- [`RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md)
- [`DISCOVER_E2E_AUTHORITY_AUDIT.md`](DISCOVER_E2E_AUTHORITY_AUDIT.md)

Frozen composition:

```text
DISCOVER

EXPLORE
+
HISTORY

Centre = candidate / lifecycle object + current state
Detail = meaning + current decision
Ask = intelligence + supported acquisition operation
Backend = durable consequence
Centre = consequence becomes visible
```

The following are not permitted as design reinterpretations:

```text
Focused Evaluation centre takeover
Semantic / AI / Advanced Search tabs
Evidence Builder
Research Query / Browse / Source Finder modes
worker-dashboard History
Activity resurrection
Search / Probe / Procure event-kind filters
infinite activity feed
giant lifecycle sections
full-height Detail growth
per-row Ask / collect controls
new permanent acquisition workspace
new permanent Agent page
```

### Discover change rule

```text
NO CASUAL DISCOVER REDESIGN.
```

A Discover composition change is permitted only when all of the following are true:

1. A concrete cross-page contradiction or proven rendered-workflow failure exists.
2. The problem cannot be solved inside the frozen Discover composition.
3. The change is reviewed visually at full-page scale before implementation.
4. `UI_PRODUCT_AUTHORITY.md` is explicitly amended.
5. `DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md` is explicitly amended.
6. The right-rail contract and Discover E2E authority audit are updated where affected.

New backend capability, new MCP tools, new source connectors, or new execution machinery do **not** by themselves justify a new Discover surface.

---

## 2. Library — hard frozen

Normative authority:

- [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md)
- [`LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md`](LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md)
- [`RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md)

Frozen product grammar:

```text
RESEARCH LOCATION
↓
COLLECTION TREE
↓
EVIDENCE ESTATE
↓
COLLECTION OR ASSET SELECTION
↓
DETAIL / ASK
↓
DURABLE LIBRARY CONSEQUENCE
```

Collection selection remains navigation.

Evidence selection remains inspection.

Source, verification, and readiness remain separate axes.

Collections remain research organisational contexts, not physical archive directories.

One durable evidence asset may belong to multiple collections without duplication.

No system or model silently moves evidence between collections.

### Library change rule

The default answer to a proposed Library composition redesign is **no**.

Any material composition change must amend both `UI_PRODUCT_AUTHORITY.md` and `LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md` before implementation.

---

## 3. Profile — grounded hard freeze

Normative grounded authority:

- [`PROFILE_GROUNDED_FREEZE_2026-07-16.md`](PROFILE_GROUNDED_FREEZE_2026-07-16.md)
- current faculty-profile / registry data contract
- current `profileViewModel.js` evidence-gated derivation rules

Frozen information architecture:

```text
MEMORY
↓
WORKS
↓
LAB

LINKED | SUGGESTED
```

Profile remains research memory derived from the real faculty-profile / registry contract.

It is not:

```text
social profile
CV / resume builder
academic identity graph
settings form
opaque AI-memory inspector
context-origin ledger
ranking-effect ledger
synthetic researcher ontology
```

The frontend must not invent canonical Profile truth for markets/entities, evidence preferences, inferred signals, accepted context, product-effect ledgers, profile-belief provenance, or other unsupported fields.

### Profile change rule

```text
PRODUCT MODEL        FROZEN
IA                   FROZEN
DATA HONESTY RULE    FROZEN
MAJOR REDESIGN       NO
VISUAL POLISH        YES
```

Permitted work is limited to in-place convergence such as:

```text
Memory hierarchy
Current research direction emphasis
Works density
Lab Linked / Suggested balance
Detail rail typography / spacing
thin-profile rendering
pilot / unbound labelling
"saved contexts" honesty correction
responsive convergence
pixel polish
```

A richer faculty-profile backend does not automatically reopen Profile design.

The default answer to a proposed Profile redesign is **no**.

---

## 4. Home — hard frozen

Normative Home authority:

- [`HOME_FULL_SCALE_FREEZE_2026-07-16.md`](HOME_FULL_SCALE_FREEZE_2026-07-16.md)
- [`RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md)
- canonical Library / Discover / Synthesis / Resources object truth used by the Home projection

Approved Iteration 10 composition:

```text
TOP BAND

PICK UP                         RESOURCE HEADROOM

MIDDLE BAND

RECOMMENDED EVIDENCE

BOTTOM BAND

RECENT TRAIL
```

Frozen caps:

```text
PICK UP
1 primary + 1 secondary max

RESOURCE HEADROOM
2 resources max

RECOMMENDED EVIDENCE
2 recommendations max

RECENT TRAIL
3 consequences max

DESKTOP HOME PAGE SCROLL
NEVER
```

Home does not become a command centre, metrics dashboard, activity feed, worker monitor, news feed, research pulse, related-method recommender, or session-analytics surface.

Resource bars require authoritative used value, real cap / denominator, and current resource state.

Recommendations require grounded recommendation authority.

Recent Trail excludes browser history and ordinary execution noise.

### Home change rule

```text
NO CASUAL HOME REDESIGN.
```

A Home composition change is permitted only when a concrete rendered failure or cross-page contradiction cannot be solved inside Iteration 10, and the alternative is reviewed visually at full-page scale before the Home appendix and this lock are amended.

---

## 5. Resources — hard frozen

Normative Resources authority:

- [`RESOURCES_FULL_SCALE_FREEZE_2026-07-16.md`](RESOURCES_FULL_SCALE_FREEZE_2026-07-16.md)
- [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md), especially the permanent `Sources | Usage | Method` family
- [`RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md)
- current source manifest, Resources rollup, and durable expenditure records as truth inputs

Approved Iteration 05 family:

```text
SOURCES
capability
current headroom
access authority
source routes

USAGE
period totals
resource expenditure history
research-object attribution
recorded outcomes

METHOD
find
acquire
execute
promote
bounded current method progress
```

Frozen permanent tabs:

```text
Sources | Usage | Method
```

Frozen ownership:

```text
SOURCES
What can the lab use now?

USAGE
What resources did the lab actually spend,
when, and on what research object?

METHOD
How does evidence move through the machine?
```

Progress bars require:

```text
current numerator
+
real denominator
+
current authoritative state
```

A manifest route definition is not provider health.

```text
ROUTE EXISTS
≠
ACCESS VERIFIED
```

Resources must distinguish:

```text
OBSERVED
ROUTE DEFINED
CONDITIONAL
UNAVAILABLE
NOT CHECKED
```

Usage is an expenditure ledger, not generic application activity.

Every primary Usage history row should answer:

```text
WHEN?
WHAT RESOURCE?
HOW MUCH?
FOR WHAT RESEARCH OBJECT?
WHAT RECORDED OUTCOME?
```

Method explains evidence movement; it does not default to worker tables, queue tables, ports, MCP counts, architecture prose, or a job browser.

The following rejected directions must not return:

```text
Overview | Activity
Activity as a permanent Resources tab
Review / Jobs / Ask / Discovery / Query / Metered filter browser
generic run log
worker-dashboard posture
job approvals inside Resources centre
Storage / Agents / Integrations / Billing / Architecture permanent tabs
fake quota bars
manifest declaration presented as live health
```

### Resources change rule

```text
NO CASUAL RESOURCES REDESIGN.
```

A Resources composition change is permitted only when all of the following are true:

1. A concrete rendered-workflow failure or cross-page contradiction exists.
2. The problem cannot be solved inside the frozen Iteration 05 family.
3. The alternative is reviewed visually at full-page scale.
4. `RESOURCES_FULL_SCALE_FREEZE_2026-07-16.md` is explicitly amended before implementation.
5. This change lock and `UI_PRODUCT_AUTHORITY.md` are aligned where affected.
6. Resources tests are updated to the new authority rather than preserving old implementation drift.

The current `Overview | Activity` implementation and its tests do not override the frozen Resources appendix.

The default answer to a proposed Resources redesign is **no**.

---

## 6. What remains open

The following work remains:

```text
PROFILE
bounded visual polish and complete thin / unbound full-page state preservation

PREVIEW
centre-scoped renderer / overlay validation

SETTINGS
truthful low-complexity convergence and removal of hardcoded / developer-facing status leakage

SYNTHESIS
final major product-design problem
```

Recommended design order:

```text
PROFILE POLISH
↓
SETTINGS
↓
PREVIEW
↓
SYNTHESIS
↓
RESPONSIVE / COMPONENT / PIXEL CONVERGENCE
```

Profile polish and Settings should be deliberately short passes.

Preview is narrow but renderer-sensitive.

Synthesis remains the only major unresolved product surface.

Frozen pages may still be implemented, made responsive, accessibility-correct, and pixel-polished.

That does not reopen their page thesis or centre composition.

---

## 7. Recovery rule

When a new agent, model, developer, or design session enters the repository:

```text
READ UI_PRODUCT_AUTHORITY.md
↓
READ FROZEN_PAGE_CHANGE_LOCK_2026-07-16.md
↓
READ THE PAGE'S FULL-SCALE FREEZE / GROUNDED FREEZE
↓
READ RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md WHERE RELEVANT
↓
IMPLEMENT OR POLISH INSIDE THE FROZEN COMPOSITION
```

For Home, `HOME_FULL_SCALE_FREEZE_2026-07-16.md` is the approved Iteration 10 visual authority.

For Resources, `RESOURCES_FULL_SCALE_FREEZE_2026-07-16.md` is the approved Iteration 05 visual authority.

Do not infer that an old component, screenshot, test, fixture, backend object, or newly added capability grants permission to redesign a frozen page.

```text
OLD UI
NEW BACKEND
NEW TOOL
NEW EVENT KIND
NEW MODEL OUTPUT

DO NOT OVERRIDE

FROZEN PRODUCT COMPOSITION
```

---

## Final lock

```text
DISCOVER
DO NOT REDESIGN.

LIBRARY
DO NOT REDESIGN.

PROFILE
DO NOT REDESIGN.
POLISH INSIDE THE GROUNDED FREEZE.

HOME
DO NOT REDESIGN.

RESOURCES
DO NOT REDESIGN.
```

These pages may be implemented better, rendered better, made responsive, accessibility-correct, and pixel-polished.

They are not waiting for another conceptual pass.
