# Research Drive UI Product Authority

**Status:** CURRENT UX IMPLEMENTATION AUTHORITY  
**Date:** 2026-07-15  
**Applies to:** `drive/src/v2/*` and every faculty-facing Research Drive route  
**Implementation owner:** frontend and backend workers executing this document  
**Acceptance owner:** rendered workflow and pixel review  

This is the sole top-level authority for Research Drive product composition, navigation, interaction grammar, visual direction, responsive behavior, and acceptance. No historical UX document, screenshot packet, runbook, component, test, backend directory shape, fixture, or backend capability overrides this document.

For Discover, [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md) is the normative full-scale visual and interaction appendix incorporated by reference into this authority. Its complete CLI wireframes are implementation authority, not examples.

For Library, [`LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md`](LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md) is the normative full-scale visual and interaction appendix incorporated by reference into this authority. Its complete CLI wireframes are implementation authority, not examples.

A Discover or Library composition change must amend this document and the corresponding full-scale appendix before implementation.

## 1. Product promise

Research Drive is a research-evidence procurement and evidence-estate workbench.

```text
research intention
→ external or local evidence
→ evidence sufficiency decision
→ bounded inspection
→ durable evidence request when appropriate
→ acquisition-method engineering where required
→ execution / archive / registration / readiness
→ registered Library asset
→ reusable research evidence
→ optional Synthesis input or output
```

It is not a generic Drive clone, chat-first product, data-engineering console, collection wizard, worker dashboard, or pipeline builder.

## 2. Navigation and application grammar

The only navigable faculty destinations are:

```text
Home · Library · Discover · Synthesis · Resources · Profile · Settings
```

These are not destinations:

```text
Cluster
Activity
Pipeline
Sources
Vault
Preview
Approval
route comparison
failure
registration
procurement method
job execution
collection suggestion review
verification comparison
```

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

A selected centre object remains visible while Detail or Ask changes. Do not replace the centre evidence landscape with a second page-local evaluation workspace.

## 3. Visual direction

```text
Quiet paper shell
+ graphite evidence surfaces when density is useful
+ ink reasoning rail for an active object or Ask
+ cobalt only for selection and meaningful action
```

- Home, Profile, and general workspace are quiet and editorial.
- Library, Discover, Resources, and Preview use compact, inspectable evidence surfaces.
- The rail is quiet when no meaningful object is active. It becomes the interpretation surface for a selected collection, asset, candidate, lifecycle object, preview target, blueprint, capability, or Ask.
- The rail must never be a permanent empty inspector.
- The desktop desk is full-height: navigation/context at left, sustained evidence work in centre, decision interpretation at right, and a narrow operational status edge at bottom.
- Evidence density must remain readable at inventory scale. Do not turn compact evidence rows into cards.

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
| Home | research intention, needs-you items, exact resume points | active research context and optional Ask |
| Library | research collections, durable evidence assets, evidence-estate search | selected collection context or selected asset authority, source, verification, readiness, gaps, reuse |
| Discover | external evidence and durable lifecycle objects | selected candidate/request judgment, current decision, and object-scoped operation |
| Synthesis | blueprints, input readiness, verified outputs | selected blueprint/output and gap action |
| Resources | source capabilities, usage, and method topology within the frozen Resources family | selected capability/usage/method-node interpretation |
| Profile | research context and its ranking impact | why context affects recommendations |
| Settings | workspace/session preferences | contextual help only |

## 6. Home

Home answers:

```text
What needs attention?
What can I resume?
What can I start?
```

It contains research-intention entry, a concise needs-you queue, and exact resume points. It is not a metrics dashboard, full catalogue, worker monitor, or generic chat landing page.

The visual hierarchy must remain:

```text
1. research intention
2. Needs you, only when real decisions exist
3. Continue / exact resume points
4. Recent work as low-weight context
```

## 7. Library

Library answers:

```text
What durable evidence does the lab own?
What is it about?
Where did it come from?
What source relationship is established?
Can I use it now?
What research context does it belong to?
What evidence is still missing?
```

The complete binding composition and state family are in [`LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md`](LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md).

### 7.1 Library composition

The centre is:

```text
research location / breadcrumb
current collection + asset count
search
readiness filters
Collections | Evidence estate
```

The evidence estate remains immediately visible. Do not insert permanent research-dashboard modules above the ledger.

Normal Library asset row grammar is:

```text
TITLE                     SOURCE       VERIFY       STATE
plain-language one-line description
```

The description explains what the evidence is about. Metadata strings such as grain, entity count, or coverage do not substitute for a human-readable description.

The centre column concepts are semantically distinct:

```text
EVIDENCE
what is this asset about?

SOURCE
where did the owned asset come from?

VERIFY
what source / sourcable-evidence relationship has been established?

STATE
can Research Drive currently use the asset?
```

### 7.2 Canonical readiness

Canonical readiness labels are:

```text
Metadata only
Registered
Query-ready
Unavailable / not verified
```

In compact ledger presentation they may be uppercase:

```text
METADATA ONLY
REGISTERED
QUERY-READY
UNAVAILABLE / NOT VERIFIED
```

Do not replace `Query-ready` with generic `Ready`.

```text
exists ≠ registered
registered ≠ query-ready
```

### 7.3 Source and verification are independent

Source answers:

```text
Where did this owned asset come from?
```

Examples:

```text
BigQuery
GDELT
MOPS
SEC EDGAR
DataCite
Self-provided
2 sources
Not recorded
```

Verification answers:

```text
What relationship has Research Drive established
between this owned asset and authoritative /
sourcable evidence?
```

Canonical verification states:

```text
Verified
Matched
Partial
Unverified
Not checked
```

Hard honesty rules:

```text
Verified ≠ data is true
Matched ≠ datasets are identical
Query-ready ≠ externally verified
Self-provided ≠ unusable
```

A self-provided asset may be Query-ready and Unverified. A self-provided asset may also be Matched or Partial when a durable comparison establishes correspondence with known sourcable evidence.

Detail must explain exactly what matched, differed, or remains unestablished.

### 7.4 Collections are research contexts

A Library collection is a research organisational context, not a physical archive directory.

```text
COLLECTION
=
research organisational context

NOT
=
physical storage directory
```

One durable asset may belong to multiple collections without duplication:

```text
USDT transaction dataset

├── Raw evidence
├── Historical transaction evidence
└── Event-study inputs
```

The asset has one durable identity, one registry identity, one archive authority, and one readiness state.

Faculty-facing collection hierarchy must not mirror arbitrary backend directory nesting.

The normal desktop hierarchy budget is three visible levels:

```text
root research context
  collection
    nested collection
```

### 7.5 Manual collection authority with system suggestions

Researchers control collection membership.

```text
create / edit collection
→ manually add evidence
→ accepted collection context accumulates
→ Library may propose related owned evidence
→ researcher reviews
→ researcher approves membership changes
```

Accepted collection context may derive from:

```text
collection description
accepted evidence
evidence type / grain
entities / markets
coverage
source relationships
active research context
```

A collection must have enough accepted context before the system presents organisation suggestions.

The system may say:

```text
3 owned assets may belong here.
Review suggestions
```

It must never silently move assets, create folder hierarchies, or change collection membership based on semantic similarity or model prose.

The collection suggestion review remains a temporary Library centre state, not a new route/page.

### 7.6 Library active rail objects

Selecting a collection creates:

```text
kind = library_collection
```

Collection Detail owns:

```text
collection meaning
accepted context
evidence estate summary
related-evidence suggestion state
known gaps
current organisation decision
```

Selecting an evidence asset creates:

```text
kind = library_asset
```

Asset Detail owns:

```text
asset research use
readiness
evidence shape / coverage
source
verification relationship
collection memberships
limitations
citation / source-chain actions
```

A Library search result may create a scoped search-match context:

```text
kind = library_search_match
parent = library_asset
```

Detail explains why the asset matched while preserving canonical asset truth.

### 7.7 Composer / Cite-Agent in Library

The rail tab remains `Ask` for stable application grammar.

When truthful, the visible active intelligence identity may say:

```text
Composer · selected collection
Composer · selected evidence
Cite-Agent · selected evidence
```

The Library rail is not generic folder chat.

For a selected collection, Ask may:

```text
explain collection context
compare owned evidence against accepted context
propose related owned evidence
explain suggestion signals
inspect known gaps
prepare an exact Discover handoff
```

For a selected asset, Ask may:

```text
explain evidence semantics
inspect source relationship
compare owned evidence with matched sourcable evidence
reason over schema / coverage / provenance
find related owned evidence
assess research use
prepare an exact Discover handoff for a limitation / gap
```

Supported durable consequences may include:

```text
suggestions recorded
verification comparison completed
verification relationship updated
gap recorded
Discover requirement prepared
collection context refined when explicitly accepted
```

Ask may not silently add/remove collection membership, autonomously create collection hierarchies, silently rewrite accepted context, or upgrade source/verification authority from prose.

### 7.8 Library search

Library searches the evidence estate, not only filenames.

Search authority may include:

```text
asset identity / accepted description
entity
registered field / schema
source identity
citation / DOI / source record
provenance record
coverage
```

The search surface remains:

```text
Search assets, entities, fields, sources, provenance…
```

Normal rows remain two lines. Search result rows may add one temporary match line:

```text
TITLE                     SOURCE       VERIFY       STATE
plain-language description
MATCH · FIELD / SOURCE / PROVENANCE / COVERAGE · exact reason
```

The match reason requires typed authority. Model prose does not invent a field, source, citation, provenance, or coverage match.

### 7.9 Source and citation

Source/citation identity is first-class research information and is not relegated exclusively to Technical record.

Detail may expose:

```text
Source record ▸
Source chain ▸
Copy citation
Copy citations
Verification record ▸
```

For derived assets, the centre source cell collapses plural lineage to:

```text
2 sources
3 sources
8 sources
```

The exact registered source chain and citations belong in Detail.

### 7.10 Add evidence / intake

Library may offer:

```text
+ Add evidence

Upload files
Add URL or DOI
────────────────────
Find external evidence
```

Ownership:

```text
Upload files = actual local intake
Add URL or DOI = known-object / source-record intake
Find external evidence = Discover
```

Do not build a Library-local procurement workflow.

A self-provided intake may progress through:

```text
Source = Self-provided
Verification = Not checked

→ bounded supported verification when requested / available

→ Matched | Partial | Unverified
```

No model response alone may establish a verification relationship.

### 7.11 Known gaps and Discover handoff

Known gaps are typed estate knowledge, not generic AI recommendations.

A selected asset may show:

```text
LIMITATION
Earlier transaction history not present.

Find earlier transaction history
```

The exact Library → Discover handoff preserves:

```text
required evidence
existing asset identity
current coverage
named gap
compatibility context
```

The target is a prefilled evidence requirement, not the Discover landing page.

### 7.12 Library scale

At inventory scale:

```text
fixed evidence header
internally scrolling evidence pane
normal row = two lines
source = one scan line
verify = one scan line
state = canonical readiness label
```

The evidence pane remains the visual priority at 128+ assets.

Library may offer add-evidence intake only when it performs real intake or is explicitly labelled assisted intake; filename-only chat prompts are not uploads.

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

The complete binding composition and state family are in [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md).

### 8.1 Explore

Explore accepts a short query, question, research description, coverage gap, or evidence requirement through one evidence-need surface. There are no Keyword, Semantic, AI, Advanced Search, Browse, or Source Finder modes.

Visible composition:

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

### 8.2 Local sufficiency

The domain contract preserves five semantic states:

| State | Meaning | Likely primary action |
|---|---|---|
| Exact | canonical qualifying local asset exists | Open in Library |
| Partial | known local subset and named gap | Compare or Preview |
| Related | same research object; equivalence unproven | Preview source |
| No local alternative | completed comparison found no qualifying asset | Preview / request / access action |
| Comparison unknown | comparison could not complete from available evidence | Preview / probe source |

`No local alternative` and `Comparison unknown` are distinct domain states. `likely-equivalent` is unsupported unless a durable backend contract is added.

### 8.3 Evidence request entry

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

### 8.4 History

History is the durable researcher lifecycle inbox. It is not a chronological activity feed, worker dashboard, job table, or event-kind browser.

Default composition:

```text
NEEDS YOU
researcher-owned decisions

RESEARCH LIFECYCLE
all remaining durable research objects
```

`Needs you` is decision ownership, not a lifecycle-state peer.

The projection preserves at least:

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

History ordering is by material durable lifecycle change, then latest durable change. Heartbeats, polls, worker checks, and unchanged progress refreshes do not continuously promote a row.

### 8.5 History lifecycle projection

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

```text
collection completed ≠ archive verified
archive verified ≠ registry promoted
registry promoted ≠ registry read-back confirmed
registered ≠ query-ready
```

### 8.6 Procurement method

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

The centre shows a compact material cue such as `Browser extraction proposed` only when method engineering is part of the current state or decision. Detail may expand the verified equipment/engine, route stages, knowns, unknowns, and review/revision action. Do not hard-code Spectator, Playwright, Selenium, or another engine without durable method authority.

### 8.7 History active rail object

Selecting a History row creates:

```text
kind = discover_lifecycle
```

The rail context includes exact lifecycle identity, lifecycle state/reason, decision ownership, evidence need, source/candidate identity when present, procurement-method state when present, and supported operations.

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

Preview separates observed evidence from facts not established by the preview. If Preview is unavailable, Detail explains why and offers the valid alternative; no empty preview overlay appears.

Preview remains scoped to the selected candidate, lifecycle object, or Library asset. Opening Preview does not start collection or mutate source/verification state.

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

Synthesis remains downstream of the procurement and evidence-estate core. It may be deferred without weakening Library or Discover ownership. It must not force Library into a pipeline-builder model.

## 12. Resources

Resources answers:

```text
What evidence capabilities and constraints can this lab currently use?
```

The frozen Resources family remains:

```text
Sources | Usage | Method
```

```text
Sources = what can we use?
Usage = what have we used?
Method = how does the machine run?
```

Resources is not the primary evidence estate, procurement lifecycle, Library folder system, or worker dashboard.

`Explore source` opens Discover with source and access context.

## 13. Profile and Settings

Profile exposes active research inputs and their ranking effects. An unbound/pilot profile is visibly labelled as such in centre, Detail, Ask, recommendations, and handoffs.

Settings controls workspace/session preference, notifications, and truth-backed connection status. Static `configured`, `synced`, `available`, or similar strings are not provider health without authority.

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

Do not repeat the same state under multiple headings such as `Current decision`, `Execution`, `Evidence`, and `What happens next` when state, judgment, and action already communicate it.

`Technical record ▸` is the default operational/developer disclosure. When expanded, it scrolls inside the rail body; the sticky action footer remains visible.

Research-native evidence disclosures may also exist where they are part of ordinary research use rather than diagnostics:

```text
Source record ▸
Source chain ▸
Verification record ▸
```

```text
ASK
- typed current page/tab/object context
- stated evidence scope
- named tool activity
- typed artifacts: sources, assets, preview facts, collection suggestions, verification results, request/method/schedule receipts
- source identity + retrieval/observation time + verification state
```

Ask is an accelerator, never a dependency. The ordinary UI must still make evidence meaning, source, verification, readiness, local sufficiency, Preview, request, approval, lifecycle, method review, organisation review, and reuse understandable.

Ask may open deterministic UI intents such as:

```text
Open asset
Open source
Open Preview
Open History item
Review method
View evidence
Review collection suggestions
Compare source match
Review gap
```

It must clear stale object context on page/mode/object transitions.

Active tool activity may show a compact evolving phase sequence. Completed activity collapses or disappears by default, with optional `Agent activity ▸`.

A successful platform mutation produces a compact product receipt such as:

```text
✓ Evidence request recorded
✓ Procurement method prepared
✓ Schedule recorded
✓ Collection queued
✓ Method revised
✓ Collection suggestions recorded
✓ 2 assets added to Raw evidence
✓ Verification relationship updated
✓ Evidence gap recorded
```

The selected centre object remains visible while Detail and Ask alternate.

## 15. Truth, freshness, and authority

Every visible claim requires an authority and freshness state.

| Claim | Authority | Fallback |
|---|---|---|
| Asset description | registered metadata / accepted asset description | Description not recorded |
| Coverage | provider metadata or observed response / asset authority | Not reported |
| Preview evidence | bounded observed response | Preview unavailable |
| Local relationship | completed comparator | Comparison unknown |
| Readiness | registry read-back | Registered — readiness not confirmed |
| Source | provenance / intake / provider record | Not recorded |
| Self-provided ownership | durable intake record | Source not recorded |
| Verification | completed typed source-comparison record | Not checked / Unverified |
| Verification match facts | observed schema/row/source comparison | Match details unavailable |
| Citation / DOI | source or provenance record | Citation not recorded |
| Source chain | registered lineage / build provenance | Source lineage not established |
| Collection membership | durable membership record | Not in collection |
| Collection context | explicit description + accepted evidence + named context inputs | Context not established |
| Related evidence suggestion | typed Library comparator over accepted collection context | No suggestion claim |
| Known evidence gap | typed gap / sufficiency / comparison authority | Gap not established |
| Library search match | exact typed field/source/provenance/coverage or grounded metadata match | Match reason unavailable |
| Access | entitlement/provider state | Access not verified |
| Lifecycle | durable lifecycle projection | Status unavailable |
| Procurement method | durable proposal/observation/approval/execution record | Method not established |
| Archive | archive/manifest verification | Archive verification pending |
| Registration | promotion/read-back | Registration pending |
| Ranking | named ranking signals | Why ranked unavailable |
| AI evidence | source/time/verification envelope | Assistant interpretation — verify source |

No demo fixture, stale cache, UI estimate, free-form frontend status regex, filename guess, backend folder name, lexical-title similarity, or model prose may render as a live authoritative fact.

Composer interprets research need and may explain typed match, collection, verification, or lifecycle context. Source/provider/registry/probe establishes candidate facts. Library intake/provenance establishes source ownership. Typed comparison establishes verification. Comparator establishes local relationship and related-evidence/gap claims. Lifecycle projection establishes researcher-facing state. Durable method records establish procurement-method truth.

## 16. Exact handoffs

```text
Discover Exact → exact Library asset
Discover registered result → exact Library asset
Discover registered result → compatible Synthesis blueprint
Library asset gap → Discover prefilled exact gap requirement + existing asset
Library collection gap → Discover prefilled evidence requirement + collection context
Library related owned evidence → exact Library asset / collection suggestion review
Synthesis input gap → Discover requirement + existing inputs
Resources capability → Discover provider/access constraint
Profile explanation → Discover named ranking signals
```

Every handoff opens an exact object, bounded review state, or prefilled query—not a generic landing page.

## 17. Responsive and accessibility requirements

- Desktop maintains full-height navigation, evidence centre, and active rail.
- At 1440 the full three-surface desk is authoritative. Mobile does not drive desktop composition.
- Discover and Library full-scale appendices define their binding 1440 compositions.
- Laptop may reduce navigation and rail width, but compact evidence/lifecycle row grammar and bounded rail budgets do not expand.
- Library at 1280 preserves distinct Evidence, Source, Verify, and State semantics; reduce padding before deleting meaning.
- Tablet may collapse navigation and present Detail/Ask as a selected-object slide-over while preserving centre state.
- Library tablet may collapse the collection tree into a clear location selector when simultaneous tree + evidence width is no longer readable.
- Mobile sequences context rather than duplicating it; selected evidence and Detail become a clear drill-in, not a compressed three-column view.
- Preview supports Escape, focus management, labelled source identity, and an accessible close action. A centre-scoped overlay must not falsely claim `aria-modal=true` while the rail remains interactive.
- Keyboard users can search, move through evidence rows, move through collection locations, inspect selection, open Preview, review collection suggestions, and access primary actions.
- Selected state cannot rely on cobalt alone; the narrow `▌` marker and accessible selected semantics must be present.

## 18. Implementation and acceptance order

Current convergence order:

```text
1. Discover — frozen concept; converge implementation to Discover appendix.
2. Library — frozen concept; converge implementation to Library appendix.
3. Profile — next visual convergence target.
4. Home — tighten hierarchy and freeze.
5. Preview — validate renderer family / overlay behavior.
6. Settings — clean, truthful, boring.
7. Synthesis — final major visual/product problem; may be deferred but not allowed to contaminate Library/Discover ownership.
8. Suite-wide responsive / component / pixel convergence.
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

Required Library journeys:

```text
Open collection → collection Detail
Select asset → asset Detail while collection remains visible
128-asset inventory remains readable
Search by field → exact match reason
Search by source / provenance / citation → exact match reason
Self-provided upload → Not checked
Self-provided asset → Matched
Matched asset → Composer comparison → Partial when differences established
Self-provided asset → Unverified while still Query-ready
Derived asset → plural source lineage / Copy citations
Create empty collection → no suggestion claim
Manually add evidence → collection context established
Collection context → related owned evidence suggestions
Review suggestions → explicit add selected
Remove from collection ≠ delete asset
Collection gap → exact Discover requirement
Asset limitation → exact Discover requirement
Ask-assisted and non-Ask parity
```

No later implementation worker may reinterpret frozen composition because current components, selectors, or backend directory shapes are easier to preserve.

## 19. Documentation hierarchy

1. This file is the sole top-level current UX/product authority.
2. [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md) is the incorporated normative full-scale visual and interaction appendix for Discover. Its CLI wireframes are binding.
3. [`LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md`](LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md) is the incorporated normative full-scale visual and interaction appendix for Library. Its CLI wireframes are binding.
4. `UI_IMPLEMENTATION_PROGRAM.md` is the execution plan derived from this authority and the incorporated appendices.
5. `RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md` is a subordinate typed rail/backend contract.
6. `DISCOVER_ACQUISITION.md` is a subordinate operational runbook.
7. `DISCOVER_E2E_AUTHORITY_AUDIT.md` is the subordinate Discover Playwright classification and clean-audit contract. It does not amend product composition; it governs how E2E reds are interpreted and requires git SHA / Vite root identity on every report.
8. `RESEARCH_DRIVE_UI_CANON.md`, `RESEARCH_DRIVE_UI_V2.md`, `RESEARCH_DRIVE_UX_HANDOFF_2026-07-14.md`, and `design/DISCOVER_LOOP_ANCHOR.md` are historical redirects only.
9. `RESEARCH_DRIVE_UI_CONTRACT.md` is legacy-only until its legacy UI and tests are retired.

Any proposed interface change must amend this document first. A Discover or Library composition change must amend the corresponding full-scale appendix in the same change, then update the implementation program and subordinate contracts. Discover E2E rewrites must stay consistent with both the top-level authority and Discover appendix and update `DISCOVER_E2E_AUTHORITY_AUDIT.md` classification tables in the same change.
