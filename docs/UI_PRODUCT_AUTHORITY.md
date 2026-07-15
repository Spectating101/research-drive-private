# Research Drive UI Product Authority

**Status:** CURRENT UX IMPLEMENTATION AUTHORITY  
**Date:** 2026-07-15  
**Applies to:** `drive/src/v2/*` and every faculty-facing Research Drive route  
**Implementation owner:** frontend and backend workers executing this document  
**Acceptance owner:** rendered workflow and pixel review  

This is the sole top-level authority for Research Drive product composition, navigation, interaction grammar, visual direction, responsive behavior, and acceptance. No historical UX document, screenshot packet, runbook, component, test, or backend capability overrides this document.

For Discover, [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md) is the normative full-scale visual and interaction appendix incorporated by reference into this authority. Its complete CLI wireframes are implementation authority, not examples. A Discover composition change must amend both this document and that appendix before implementation.

## 1. Product promise

Research Drive is a research-evidence procurement workbench.

```text
research intention
→ external or local evidence
→ evidence sufficiency decision
→ bounded inspection
→ request / approval when appropriate
→ durable collection lifecycle
→ registered Library asset
→ reusable Synthesis input or output
```

It is not a generic Drive clone, a chat-first product, a data-engineering console, or a collection wizard.

## 2. Navigation and application grammar

The only navigable faculty destinations are:

```text
Home · Library · Discover · Synthesis · Resources · Profile · Settings
```

These are not destinations: Cluster, Activity, Pipeline, Sources, Vault, Preview, Approval, route comparison, failure, registration, procurement method, or job execution.

The application grammar is fixed:

```text
Navigation: where am I?
Centre: what evidence or research object am I working with?
Detail / Ask: what does it mean, and what is the valid next action?
```

Use the same grammar everywhere. A page does not become a new product merely because its centre object changes.

For active evidence work, the three surfaces compound rather than duplicate:

```text
Centre = object + current state
Detail = meaning + current decision
Ask = intelligence + supported operation
Backend = durable consequence
Centre = consequence becomes visible
```

## 3. Visual direction

```text
Quiet paper shell
+ graphite evidence surfaces when density is useful
+ ink reasoning rail for an active object or Ask
+ cobalt only for selection and meaningful action
```

- Home, Profile, and general workspace are quiet and editorial.
- Library, Discover, Resources, and Preview use compact, inspectable evidence surfaces.
- The rail is quiet when no evidence object is active. It becomes the ink interpretation surface for a selected candidate, lifecycle object, asset, blueprint, capability, or Ask.
- The rail must never be a permanent empty inspector.
- The desktop desk is full-height: navigation/context at left, sustained evidence work in centre, decision interpretation at right, and a narrow operational status edge at bottom.
- A selected centre object remains visible while Detail or Ask changes. Do not replace the centre evidence landscape with a second page-local evaluation workspace.

## 4. Active research context

There is one active research object.

```text
Active research
+ emphases
+ themes
+ entities / markets
+ evidence preferences
```

These are attributes of the active research object, not a second navigation system. Profile makes the inputs visible and editable. Discover and Ask must explain recommendations using named context signals.

## 5. Page ownership

| Page | Centre owns | Detail / Ask owns |
|---|---|---|
| Home | research intention, needs-you items, resume points | active research context and optional Ask |
| Library | durable lab assets | selected asset readiness, provenance, preview, reuse |
| Discover | external evidence and durable lifecycle objects | selected candidate/request judgment, current decision, and object-scoped operation |
| Synthesis | blueprints, input readiness, verified outputs | selected blueprint/output and gap action |
| Resources | source capabilities and constraints | selected capability interpretation |
| Profile | research context and its ranking impact | why context affects recommendations |
| Settings | workspace/session preferences | contextual help only |

## 6. Home

Home answers:

```text
What needs attention?
What can I resume?
What can I start?
```

It contains research-intention entry, a concise needs-you queue, and exact resume points. It is not a metrics dashboard, a full catalogue, a worker monitor, or a generic chat landing page.

## 7. Library

Library answers:

```text
What durable evidence does the lab own, and can I reuse it now?
```

The centre is collections and assets. Detail shows readiness, research use, provenance, and next action. Preview is contextual. Library may offer add-evidence intake only when it performs real intake or is explicitly labelled assisted intake; filename-only chat prompts are not uploads.

Canonical readiness labels are:

```text
Metadata only
Registered
Query-ready
Unavailable / not verified
```

## 8. Discover

Discover answers:

```text
What external evidence could answer this research need,
and what must Research Drive do to turn that need into durable usable evidence?
```

Discover has exactly two internal modes:

```text
Explore | History
```

The full-scale binding composition and state family are in [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md).

### Explore

Explore accepts a short query, question, research description, coverage gap, or evidence requirement through one evidence-need surface. There are no Keyword, Semantic, AI, Advanced Search, Browse, or Source Finder modes.

The visible composition is:

```text
WHAT EVIDENCE ARE YOU LOOKING FOR?

[ natural-language / short-query evidence input ]

INTERPRETING

signal · signal · signal · +N

Refine evidence need ▾

BEST FIT
when ranking authority supports a strong first result

OTHER MATCHES

compact source rows
```

Unselected rows contain only source identity, provider, proven evidence shape, proven access state, compact match signals, local relationship, and optional coverage/preview truth. Unknown candidate facts are omitted or conservatively degraded; Composer prose does not create source authority.

Selection leaves the ranked result list in place and drives Detail. The selected marker is a narrow `▌`. Do not use full-row cobalt fill, cards, checkboxes, radios, or a centre-scoped Focused Evaluation takeover.

Detail owns:

```text
why relevant
local sufficiency
verified facts
unknowns
one primary next action
up to two secondary actions
```

Ask receives the same selected `external_candidate` identity and evidence scope. It may investigate and operate supported platform equipment. A durable mutation returns a compact receipt and becomes visible in product state.

### Local sufficiency

The domain contract preserves five semantic states:

| State | Meaning | Likely primary action |
|---|---|---|
| Exact | canonical qualifying local asset exists | Open in Library |
| Partial | known local subset and named gap | Compare or Preview |
| Related | same research object; equivalence unproven | Preview source |
| No local alternative | completed comparison found no qualifying asset | Preview / request / access action |
| Comparison unknown | comparison could not complete from available evidence | Preview / probe source |

`No local alternative` and `Comparison unknown` are distinct domain states. The UI may visually compress them only if their explanation and valid next action remain unambiguous. `likely-equivalent` is unsupported unless a durable backend contract is added.

### Evidence request entry

History begins when the researcher commits an evidence need as durable work, not when a procurement method has already been solved.

```text
Explore selected source
→ Request this evidence
→ confirm evidence need / required evidence / observed evidence
→ Start evidence request
→ durable lifecycle object created immediately
```

The initial lifecycle state may be:

```text
ROUTE INVESTIGATING

Evidence need preserved
Acquisition method not established
```

Nothing is silently collected merely because the request exists.

### History

History is the durable researcher lifecycle inbox. It is not a chronological activity feed, worker dashboard, job table, or event-kind browser.

Default composition:

```text
NEEDS YOU
researcher-owned decisions

RESEARCH LIFECYCLE
all remaining durable research objects
```

`Needs you` is decision ownership, not a lifecycle state peer. The projection preserves at least two semantic axes:

```text
lifecycle_state
active | ready | needs_recovery | scheduled

decision_owner
researcher | system | none
```

Researcher-owned objects are promoted into `Needs you`. Every durable object appears once in the centre.

Filters remain:

```text
All · Needs you · Active · Ready · Recovery · Scheduled
```

The default `All` view does not create five giant state sections.

History rows are compact:

```text
TITLE                                           CURRENT STATE
source · evidence identity · optional scope
one current-state evidence line · freshness
```

Normal row budget is three visible lines. The right edge shows current state only. Actions belong in Detail.

History initially shows all researcher-owned decisions and a bounded 8–12-item lifecycle ledger. Use explicit `Load more`; do not recreate an endless activity feed through infinite scrolling.

History ordering is by material durable lifecycle change, then latest durable change. Heartbeats, polls, worker checks, and unchanged progress refreshes must not continuously promote a row.

### History lifecycle projection

Durable backend machinery may remain decomposed into intent, proposal, selected route, job, archive/manifest, promotion, registry read-back, and subscription records. History projects them into one researcher-facing lifecycle object.

A single evidence request may progress as:

```text
ROUTE INVESTIGATING
→ METHOD REVIEW
→ COLLECTION QUEUED
→ COLLECTING / EXTRACTING
→ SCHEMA REVIEW when required
→ ARCHIVE PENDING
→ REGISTRATION PENDING
→ READINESS UNCONFIRMED
→ QUERY-READY
```

Linked intent and collection job are not separate primary History rows for the same evidence request.

Generic `completed`, `archived`, `registered`, and `ready` strings must not be collapsed into query-ready:

```text
collection completed ≠ archive verified
archive verified ≠ registry promoted
registry promoted ≠ registry read-back confirmed
registered ≠ query-ready
```

### Procurement method

Hard procurement is a first-class lifecycle concern:

```text
How do we actually acquire this evidence?
```

A procurement method belongs to the durable lifecycle object. It is not a page and must not exist only as private Ask prose.

Method states may include:

```text
investigating
proposed
review_required
approved
queued
executing
revision_required
completed
```

Method kinds may include:

```text
api_query
http_manifest
browser_extract
scraper_run
custom_connector
```

The centre shows a compact material cue such as `Browser extraction proposed` only when method engineering is part of the current state or decision. Detail may expand the verified equipment/engine, route stages, knowns, unknowns, and review/revision action. Do not advertise routine worker configuration or hard-code Spectator, Playwright, Selenium, or another engine without durable method authority.

### History active rail object

Selecting a History row creates a first-class active rail object:

```text
kind = discover_lifecycle
```

The rail context must include exact lifecycle identity, lifecycle state/reason, decision ownership, evidence need, source/candidate identity when present, procurement-method state when present, and supported operations.

Explore and History selections are separate preserved states:

```text
Explore selection state ≠ History selection state
```

The active rail object must never remain a stale Explore candidate while a History lifecycle object is selected.

## 9. Preview

Preview is a centre-scoped evidence overlay, not a route and not a full-app blocking modal.

```text
Navigation | active preview evidence | active Detail / Ask interpretation
```

The centre renderer adapts to source type:

| Type | Evidence object |
|---|---|
| Dataset/API | bounded rows, observed fields, coverage evidence, access condition |
| Paper | title/abstract, research question, method, cited claims, replication/access state |
| Filing | issuer/type/period, authenticity, relevant sections, source-linked facts |
| Web | page identity, excerpt, publisher/time, source-linked facts, retrieval limits |

Preview separates observed evidence from facts not established by the preview. If preview is unavailable, Detail explains why and offers the valid alternative; no empty preview overlay appears.

Preview remains scoped to the selected candidate or lifecycle object. Opening Preview does not start collection.

## 10. Approval and lifecycle

Approval is a contextual confirmation modal. It shows the immutable request: source, route when applicable, scope, entity/field selection, destination, observed evidence, and constraints.

A request proceeds through durable lifecycle state and returns to Library only after archive and registry authority are present. Registration and query readiness are separate claims.

Auto-approved public paths must visibly state their policy basis. Ask cannot approve irreversible operations.

## 11. Synthesis

Synthesis is blueprint/recipe oriented:

```text
registered inputs
→ defined blueprint
→ visible input readiness and gaps
→ explicit build / refresh
→ verified durable output
```

Viewing a blueprint is read-only. Build or refresh is an explicit mutation with a receipt. A missing input creates an exact Discover handoff with the required grain, variables, coverage, and existing inputs.

## 12. Resources

Resources answers:

```text
What evidence capabilities and constraints can this lab currently use?
```

It is a source capability map: provider, evidence type, access state, checked/freshness state, supported research use, and meaningful constraint. It is not the primary jobs, worker, spend, or operational ledger surface.

`Explore source` opens Discover with source and access context.

## 13. Profile and Settings

Profile exposes active research inputs and their ranking effects. An unbound/pilot profile is visibly labelled as such in centre, Detail, Ask, recommendations, and handoffs.

Settings controls workspace/session preference, notifications, and truth-backed connection status. Static “configured” strings are not provider health.

## 14. Detail and Ask

The rail is a bounded decision instrument, not a vertical report.

```text
RAIL HEIGHT = APP VIEWPORT

fixed identity / state
bounded internal scroll body
sticky action footer
```

The page never grows because of rail content.

Default Detail budget:

```text
DETAIL
- 2–3 identity/status lines
- one judgement, max 3–4 lines
- state-specific active decision module
- no more than five visible known facts; prefer three
- no more than three unknowns
- one optional disclosure
- one primary and up to two secondary actions
- maximum five default modules
```

Do not repeat the same state under multiple headings such as `Current decision`, `Execution`, `Evidence`, and `What happens next` when the state, judgment, and action already communicate it.

`Technical record ▸` is the one default disclosure. When expanded, it scrolls inside the rail body; the sticky action footer remains visible.

```text
ASK
- typed current page/tab/object context
- stated evidence scope
- named tool activity
- typed artifacts: sources, assets, preview facts, request/method/schedule receipts
- source identity + retrieval/observation time + verification state
```

Ask is an accelerator, never a dependency. The ordinary UI must still make evidence fit, local sufficiency, preview, request, approval, lifecycle, method review, and reuse understandable.

Ask may open deterministic UI intents such as Open asset, Open source, Open Preview, Open History item, Review method, or View evidence. It must clear stale object context on page/mode/object transitions.

Active tool activity may show a compact evolving phase sequence. Completed activity collapses or disappears by default, with optional `Agent activity ▸`. A successful platform mutation produces a compact product receipt such as:

```text
✓ Evidence request recorded
✓ Procurement method prepared
✓ Schedule recorded
✓ Collection queued
✓ Method revised
```

The selected centre object remains visible while Detail and Ask alternate.

## 15. Truth, freshness, and authority

Every visible claim requires an authority and freshness state.

| Claim | Authority | Fallback |
|---|---|---|
| Coverage | provider metadata or observed response | Not reported |
| Preview evidence | bounded observed response | Preview unavailable |
| Local relationship | completed comparator | Comparison unknown |
| Readiness | registry read-back | Registered — readiness not confirmed |
| Access | entitlement/provider state | Access not verified |
| Lifecycle | durable lifecycle projection | Status unavailable |
| Procurement method | durable proposal/observation/approval/execution record | Method not established |
| Archive | archive/manifest verification | Archive verification pending |
| Registration | promotion/read-back | Registration pending |
| Ranking | named ranking signals | Why ranked unavailable |
| AI evidence | source/time/verification envelope | Assistant interpretation — verify source |

No demo fixture, stale cache, UI estimate, free-form frontend status regex, or model prose may render as a live authoritative fact.

Composer interprets the research need and may explain typed match or lifecycle context. Source/provider/registry/probe establishes candidate facts. Comparator establishes local relationship. Lifecycle projection establishes researcher-facing state. Durable method records establish procurement-method truth.

## 16. Exact handoffs

```text
Discover Exact → Library exact asset
Discover registered result → Library exact asset
Discover registered result → compatible Synthesis blueprint
Library evidence gap → Discover prefilled gap query
Synthesis input gap → Discover requirement + existing inputs
Resources capability → Discover provider/access constraint
Profile explanation → Discover named ranking signals
```

Every handoff opens an exact object or prefilled query—not a landing page.

## 17. Responsive and accessibility requirements

- Desktop maintains full-height navigation, evidence centre, and active rail.
- At 1440 the full three-surface desk is authoritative. Mobile does not drive desktop composition.
- Laptop may reduce navigation and rail width, but History rows remain compact and the rail content budget does not expand.
- Tablet may collapse navigation and present Detail/Ask as a selected-object slide-over while preserving centre state.
- Mobile sequences context rather than duplicating it; selected evidence and Detail become a clear drill-in, not a compressed three-column view.
- Preview supports Escape, focus management, labelled source identity, and an accessible close action. A centre-scoped overlay must not falsely claim `aria-modal=true` while the rail remains interactive.
- Keyboard users can search, move through evidence rows, inspect selection, open Preview, and access primary actions.

## 18. Implementation and acceptance order

```text
1. Converge Discover Explore to list-preserving selection and bounded Detail/Ask.
2. Add a first-class discover_lifecycle active object and clear stale cross-mode context.
3. Add the History lifecycle projector: durable records → one researcher-facing object.
4. Render priority + compact lifecycle ledger, material procurement-method cue, and bounded Load more.
5. Make Preview centre-scoped, source-type specific, and accessible.
6. Add typed candidate / lifecycle / method / truth envelopes to Ask and Detail.
7. Wire exact Library and Synthesis handoffs.
8. Separate Synthesis reads from execution.
9. Render real desktop/laptop states and review pixels before additional redesign.
```

Required Discover journeys:

```text
Natural-language evidence need → interpretation → ranked candidates
Exact local match
Partial local match
No preview / constrained source
No local alternative
Comparison unknown
Request evidence → Route investigating
Route investigating → Method review
Method review → approved execution
Browser extraction / hard procurement
Extraction → Schema review
Collection complete → archive pending
Archive → registration pending
Registered → readiness unconfirmed
Query-ready → exact Library asset
Registered/query-ready result → compatible Synthesis
Failure → safe recovery
Schedule recorded with non-executing honesty
Ask-assisted and non-Ask parity
```

## 19. Documentation hierarchy

1. This file is the sole top-level current UX/product authority.
2. [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md) is the incorporated normative full-scale visual and interaction appendix for Discover. Its CLI wireframes are binding.
3. `UI_IMPLEMENTATION_PROGRAM.md` is the execution plan derived from this authority and the incorporated appendix.
4. `RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md` is a subordinate typed rail/backend contract.
5. `DISCOVER_ACQUISITION.md` is a subordinate operational runbook.
6. `DISCOVER_E2E_AUTHORITY_AUDIT.md` is the subordinate Discover Playwright classification and clean-audit contract. It does not amend product composition; it governs how E2E reds are interpreted and requires git SHA / Vite root identity on every report.
7. `RESEARCH_DRIVE_UI_CANON.md`, `RESEARCH_DRIVE_UI_V2.md`, `RESEARCH_DRIVE_UX_HANDOFF_2026-07-14.md`, and `design/DISCOVER_LOOP_ANCHOR.md` are historical redirects only.
8. `RESEARCH_DRIVE_UI_CONTRACT.md` is legacy-only until its legacy UI and tests are retired.

Any proposed interface change must amend this document first. A Discover composition change must amend the full-scale appendix in the same change, then update the implementation program and subordinate contracts. Discover E2E rewrites must stay consistent with both authority documents and update `DISCOVER_E2E_AUTHORITY_AUDIT.md` classification tables in the same change.