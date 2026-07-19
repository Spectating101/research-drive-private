# Research Drive UI Implementation Program

**Status:** Current execution program  
**Authority:** Derived exclusively from [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md), [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md), and [`LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md`](LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md)  
**Scope:** `drive/src/v2/*`, required API contracts, tests, rendered-pixel review

## Rule

Do not change faculty-facing navigation, page ownership, rail behavior, Preview, truth vocabulary, Discover lifecycle ownership, procurement-method representation, Library collection semantics, source/verification semantics, or Library row grammar without first amending the product authority.

Discover composition changes must amend the Discover full-scale appendix in the same change. Library composition changes must amend the Library full-scale appendix in the same change.

Current implementation must converge to authority. Existing components, historical selectors, backend directory shapes, and current tests do not override the frozen designs.

---

# Phase A — Discover convergence

## Slice A1 — Discover Explore composition

Goal: Discover is `Explore | History`; a selected source leaves Explore visible and drives bounded Detail/Ask.

- Normalize URL modes to `explore|history`; map legacy Search/Activity/Approvals aliases to Explore with focus state only when required for compatibility.
- Use the backend Explore source contract for results and the durable Discover History contract for History.
- Delete the centre takeover where a selected `focusTarget` replaces ranked results with a full Focused Evaluation workspace.
- Selection remains in the ranked list with the narrow `▌` marker and switches the rail to `Detail`.
- Move pending approvals into selected lifecycle/request Detail or the History priority territory; do not retain Activity as a third tab.
- Remove unselected-row fit badges, local-estate actions, collection actions, and Ask controls.
- Render source fit, five-state local sufficiency, verified evidence, unknowns, and valid next action in bounded Detail.
- Preserve the exact selected candidate as `external_candidate` Ask context.

Acceptance:

```text
Select source → ranked list remains visible → Detail changes.
Detail and Ask alternate without replacing centre selection.
Explore and History are the only Discover modes.
No Focused Evaluation centre takeover.
Legacy URLs land in Explore without reviving Activity.
History is not sourced from Resources activity events.
```

## Slice A2 — First-class Discover active objects

Goal: the rail always operates the exact selected Discover object.

- Preserve Explore and History selection as separate state.
- `Explore` selection produces `external_candidate`.
- `History` selection produces `discover_lifecycle`.
- `Preview` context is scoped to its parent candidate or lifecycle object.
- Clear stale active object context on mode/page/object transition.
- History row selection binds the selected lifecycle object to Detail and Ask; `selectedHistoryId` alone is insufficient.
- Extend typed rail context with lifecycle identity, lifecycle state/reason, decision ownership, evidence need, source/candidate identity, procurement method, and supported operations.

Acceptance:

```text
Select Explore result → rail context is that external candidate.
Switch History → stale Explore active context is cleared.
Select History row → rail context is that discover_lifecycle object.
Toggle Detail / Ask → exact object identity remains unchanged.
Switch back Explore → preserved Explore selection can be restored separately.
```

## Slice A3 — History lifecycle projector and compact ledger

Goal: History represents one durable evidence request progressing through procurement and evidence promotion.

- Add one backend-owned researcher lifecycle projection across Discover intents, selected/proposed routes, Discover-linked jobs, archive/manifest state, promotion/registry read-back, and subscriptions.
- Do not emit a linked intent and its current collection job as separate primary History objects.
- Backend projection owns lifecycle state/reason and decision ownership; frontend must not retain final state ownership through status regex bucketing.
- Preserve at least:

```text
lifecycle_state
active | ready | needs_recovery | scheduled

decision_owner
researcher | system | none
```

- Project `decision_owner=researcher` into `Needs you`.
- Render default `All` as `Needs you` plus one compact `Research lifecycle` ledger.
- Use the frozen three-line row grammar and right-edge current-state label.
- Initial lifecycle viewport budget is 8–12 rows with explicit `Load more`.
- Order by material durable lifecycle change, then latest durable change; heartbeats/polls do not continuously promote a row.
- Preserve truthful stages between collection and query-ready: archive pending, registration pending, readiness unconfirmed.

Acceptance:

```text
One evidence request = one primary History object.
Needs you contains researcher-owned decisions only.
All view does not create five giant state sections.
History row normal height = three visible lines.
completed does not automatically render Query-ready.
70 lifecycle objects remain navigable through compact rows, filters, and Load more.
```

## Slice A4 — Durable procurement method

Goal: hard acquisition-method engineering is visible as lifecycle state without becoming a page or pipeline builder.

- Evidence request is created before method resolution.
- Initial unresolved state may render `ROUTE INVESTIGATING` / `Method not established`.
- Add a typed procurement-method envelope attached to the lifecycle object.
- Support semantic method states such as investigating, proposed, review-required, approved, queued, executing, revision-required, and completed.
- Support typed method kinds such as API query, HTTP manifest, browser extract, scraper run, and custom connector.
- Surface a compact centre cue only when method is material to the current state/decision.
- Detail expands verified method kind, equipment/engine, bounded route stages, knowns, unknowns, and review/revision action.
- Ask may investigate routes, run supported bounded probes/tests, propose/revise methods, and operate supported equipment; it may not silently approve irreversible execution.
- Do not hard-code Spectator, Playwright, Selenium, or another engine without durable method authority.

Acceptance:

```text
Request evidence → History object exists before method is solved.
Route investigation may become method review on the same lifecycle object.
Method review moves to Needs you when the researcher owns the decision.
Method approval moves the same object back into lifecycle execution.
Centre shows only a compact material method cue.
Full method reasoning lives in bounded Detail / Ask.
```

---

# Phase B — Library convergence

## Slice B1 — Research-location composition

Goal: Library provides Drive-level locational confidence while the evidence estate remains immediately visible.

- Current location and breadcrumb own the top of the centre.
- Render current collection name and asset count.
- Search appears immediately before readiness filters and the estate ledger.
- Use the frozen split:

```text
COLLECTIONS | EVIDENCE ESTATE
```

- Collection selection changes current location, breadcrumb, contents, and active rail object.
- Asset selection leaves the current collection visible and changes the active rail object only.
- Do not add permanent dashboard blocks for gaps, recommendations, provenance, or verification above the ledger.
- Collections must not mirror backend archive directory nesting.

Acceptance:

```text
Open Library → current research location is explicit.
Select collection → breadcrumb + contents change → collection Detail.
Select asset → current location stays → row remains selected → asset Detail.
Centre remains evidence-first.
No backend path tree leaks into faculty navigation.
```

## Slice B2 — Evidence row grammar and canonical states

Goal: every normal asset can be understood and authority-scanned in two lines.

Frozen row anatomy:

```text
TITLE                     SOURCE       VERIFY       STATE
plain-language one-line description
```

- The description says what the evidence is about; do not substitute metadata soup.
- `SOURCE` is one scan line.
- `VERIFY` is one scan line.
- `STATE` uses canonical readiness vocabulary.
- Canonical readiness:

```text
QUERY-READY
REGISTERED
METADATA ONLY
UNAVAILABLE / NOT VERIFIED
```

- Canonical verification:

```text
VERIFIED
MATCHED
PARTIAL
UNVERIFIED
NOT CHECKED
```

- Preserve source and verification as independent facts.
- Preserve readiness and verification as independent axes.

Acceptance:

```text
Self-provided + Unverified + Query-ready is valid.
Self-provided + Matched + Query-ready is valid.
BigQuery + Verified + Query-ready is valid.
No row uses generic Ready.
Normal asset row = two lines.
```

## Slice B3 — First-class Library active objects

Goal: the right rail interprets the exact selected Library object, not only datasets.

Add typed active objects:

```text
library_collection
library_asset
library_search_match
```

`library_collection` Detail owns:

```text
collection meaning
accepted context
estate summary
related-evidence suggestion state
known gaps
current organisation decision
```

`library_asset` Detail owns:

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

`library_search_match` is scoped to `library_asset` and carries exact match reason + authority.

- Selecting a new Library object switches rail to Detail unless the user explicitly invokes Ask on that object.
- Clear stale collection/asset/search-match context on transitions.
- Detail renders structured truth, not Composer prose.

Acceptance:

```text
Select collection → rail kind = library_collection.
Select asset → rail kind = library_asset.
Search select → rail carries exact asset + match reason.
Toggle Detail / Ask → exact object identity remains unchanged.
Collection rail context never accidentally operates stale asset context.
```

## Slice B4 — Source, citation, and verification authority

Goal: Library visibly separates origin, external correspondence, and usability.

- `SOURCE` derives from durable provenance/intake/provider records.
- Self-provided evidence renders `SELF-PROVIDED`; preserve the original upload/intake record.
- Derived assets collapse plural lineage to `N SOURCES` in the centre.
- Detail exposes exact source chain and citation actions where authority exists.
- Add typed verification relationships backed by durable comparison records.
- Verification may establish matched fields, differences, coverage divergence, and unknown transformation methodology.
- Model prose must not set verification state.
- Source/citation actions are ordinary research actions, not only Technical record diagnostics.

Acceptance:

```text
Direct source → source identity + Source record / citation action.
Self-provided → upload preserved + no external source claimed unless comparison establishes one.
Derived asset → N SOURCES in row → exact source chain in Detail.
Matched → exact matched facts visible.
Partial → matched + differs + unknowns visible.
Unavailable source → preserved evidence does not gain false verification confidence.
```

## Slice B5 — Manual collections + related-evidence suggestions

Goal: researcher-controlled organisation gains contextual intelligence without becoming an AI organiser.

- A collection is research organisation, not physical storage.
- One asset may belong to multiple collections.
- Use organisation language:

```text
Add to collection
Manage collections
Remove from collection
```

- Removing from one collection does not delete the asset.
- New collection may start with name + optional description.
- Do not create rich collection context from title alone.
- Collection context accumulates from explicit description, accepted evidence, typed evidence metadata, source relationships, and active research context.
- Once enough accepted context exists, the Library comparator may prepare related-owned-evidence suggestions.
- The collection rail shows a quiet signal such as:

```text
3 owned assets may belong here.
Review suggestions
```

- Suggestion review is a temporary Library centre state, not a new route.
- Each suggestion shows exact asset identity, source, verification, readiness, description, and named `WHY RELATED` signals.
- Nothing changes until the researcher explicitly adds selected assets.
- Ask/Composer may prepare suggestions but may not silently change collection membership or create hierarchies.

Acceptance:

```text
Empty new collection → no suggestion claim.
Manually add evidence → accepted context grows.
Enough accepted context → related evidence may be suggested.
Review suggestions → explicit selection → Add selected.
Durable membership updates → same asset identity remains.
No silent organisation.
```

## Slice B6 — Library search and exact match explanation

Goal: search the evidence estate rather than filenames only.

Supported typed match families:

```text
asset identity / accepted description
entity
registered field / schema
source identity
citation / DOI / source record
provenance record
coverage
```

- Normal rows remain two lines.
- Search result rows may add one third match line:

```text
MATCH · FIELD / SOURCE / PROVENANCE / COVERAGE · exact reason
```

- Match explanation is typed authority and must not replace the asset description.
- Detail renders match reason plus canonical underlying asset truth.
- Ask receives the exact asset and current match reason.

Acceptance:

```text
counterparty address → exact field match reason.
BigQuery → exact source match reason.
DOI → exact provenance/citation match reason.
before 2020 → coverage match or honest no-owned-evidence result.
No model-invented fields or citations.
```

## Slice B7 — Add evidence / intake and verification outcomes

Goal: local intake is real, source ownership is honest, and verification outcomes are durable.

Top menu:

```text
Upload files
Add URL or DOI
────────────────
Find external evidence
```

- Upload performs actual intake.
- URL/DOI intake performs known-object/source-record intake.
- Find external evidence opens Discover with context.
- Do not create a Library procurement workflow.

Self-provided intake may progress:

```text
Source = Self-provided
Verification = Not checked

→ bounded supported comparison

→ Matched | Partial | Unverified
```

- A checking state may show current bounded verification activity without claiming an outcome.
- Durable comparison record establishes the final verification relationship.

Acceptance:

```text
Upload preserves original intake record.
Not checked is not displayed as Unverified until semantics warrant it.
Matched / Partial / Unverified require durable outcome authority.
Query readiness remains independent.
```

## Slice B8 — Inventory scale and exact gap handoffs

Goal: 128+ assets remain readable and Library gaps create exact Discover work.

- Evidence header remains fixed inside the evidence pane.
- Evidence pane uses `min-height: 0; overflow-y: auto`.
- Normal row remains two lines.
- Source/Verify/State remain one-line scan facts.
- Collection tree remains location navigation, not a tag facet.
- Known gap claims require typed gap/comparison authority.
- Asset limitation action creates exact Discover requirement with existing asset identity and coverage context.
- Collection gap action creates exact Discover requirement with collection context.

Acceptance:

```text
128 assets remain visually scannable.
Evidence pane scrolls independently.
No source secondary text expands every row.
0 known gaps → no gap claim.
Asset limitation → exact Discover requirement.
Collection gap → exact Discover requirement.
```

---

# Phase C — Remaining surface convergence

## Slice C1 — Profile

- Make research-context inputs visible, editable, and accountable.
- Every visible context signal must map to an actual product effect or be deleted.
- Detail/Ask explains named ranking/context effects.
- Preserve unbound/pilot state honestly.

## Slice C2 — Home

- Preserve Home ownership: intention, attention, resume.
- Tighten visual hierarchy:

```text
1. What are you investigating?
2. Needs you, only when present
3. Continue
4. Recent work
```

- Do not add metrics-dashboard chrome.

## Slice C3 — Preview

Goal: Preview is a centre-scoped, accessible evidence overlay with an interactive Detail/Ask rail.

- Define typed preview payloads for dataset/API, paper, filing, and web source evidence.
- Scope Preview to the selected candidate, lifecycle object, or Library asset.
- Separate observed facts from unestablished facts.
- Opening Preview never starts collection or changes verification state.

## Slice C4 — Settings

- Keep Settings clean, truthful, and low-drama.
- Workspace/session preference, notifications, and truth-backed connection status only.
- Static `configured` / `synced` / `available` copy is not provider health.

## Slice C5 — Synthesis

- Keep Synthesis downstream of registered Library evidence.
- Make profile/blueprint reads side-effect free; reserve build/refresh for explicit mutation.
- Surface selected blueprint/output in Detail/Ask with input readiness and gap identity.
- Do not allow Synthesis uncertainty to contaminate Library or Discover ownership.
- Synthesis may be deferred if the visual/product model remains unresolved.

---

# Shared bounded Detail / Ask slice

- Rail height is the app viewport; rail content never stretches the page.
- Identity/state is fixed, body uses `min-height: 0; overflow-y: auto`, and decision/action footer remains sticky inside the rail.
- Default Detail has at most five modules, one judgment, 3–5 known facts, three unknowns, one default operational disclosure, one primary action, and up to two secondary actions.
- Research-native disclosures such as Source record, Source chain, and Verification record may exist when they are ordinary research information rather than diagnostics.
- Remove duplicate semantic modules when they repeat current state.
- Pass typed current context to Ask and clear stale selection on transitions.
- Collapse completed Ask activity by default; retain optional `Agent activity ▸`.
- Successful mutations return compact product receipts and refresh durable state.

Acceptance:

```text
Rail never exceeds shell height.
Primary action remains visible while body/disclosure scrolls.
Centre selection remains visible while Detail/Ask alternates.
Ask operates the exact selected object.
Durable mutation → visible state change → updated Detail judgment.
```

---

# Exact handoffs

- Discover Exact / registered result → exact Library asset.
- Library asset gap → Discover prefilled exact gap requirement + existing asset context.
- Library collection gap → Discover prefilled evidence requirement + collection context.
- Library related-owned-evidence suggestion → exact Library asset review.
- Registered/query-ready Discover result → compatible Synthesis blueprint where supported.
- Synthesis input gap → Discover requirement + existing inputs.
- Resources capability handoff → Discover provider/access constraint.

---

# Test gates

## Unit

```text
Discover URL aliases
five-state sufficiency
lifecycle projection
decision ownership
procurement-method envelopes
truth-envelope fallbacks
typed candidate/lifecycle rail context
Library readiness vocabulary
Library source projection
Library verification projection
collection multi-membership
collection context authority
related-evidence suggestion authority
Library search match authority
library_collection / library_asset / library_search_match rail contexts
```

## E2E

```text
Discover Explore/History
selected-row rail
no Focused Evaluation takeover
History active-object binding
request → route investigating
route → method review
method → execution
schema review
Preview overlay
request → registration
exact Discover/Library handoffs

Library collection navigation
collection Detail
asset selection preserves location
asset Detail source + verification
128-asset inventory
field/source/provenance search match
self-provided intake
Matched / Partial / Unverified outcomes
plural source lineage
empty collection
manual add to collection
related-evidence suggestion review
remove from collection ≠ delete asset
Library gap → exact Discover requirement
Ask-assisted and non-Ask parity
```

## Visual

Review desktop 1440 first, laptop 1280 second.

Discover required visual states:

```text
5 items
20 items
70 lifecycle objects
direct API
BigQuery
hard browser source
method failure
schema review
schedule record
query-ready asset
```

Library required visual states:

```text
6 assets
128 assets
collection selected
asset selected
collection Ask active
search field match
search source/provenance match
derived asset with 2–8 source lineage
empty collection
self-provided Not checked
self-provided Matched
self-provided Partial
self-provided Unverified
unavailable source
related-evidence suggestion review
```

Tablet/mobile must preserve semantics but do not drive desktop composition.

---

# Discover E2E interpretation rule

Before treating a Discover Playwright red as a Slice failure:

1. Classify each test against [`DISCOVER_E2E_AUTHORITY_AUDIT.md`](DISCOVER_E2E_AUTHORITY_AUDIT.md).
2. Discard **ENVIRONMENT FAILURE** runs: wrong Vite tree, contested port, overlapping workers.
3. Do not use **LEGACY EXPECTATION** tests for Activity or Focused Evaluation centre takeover as current acceptance gates.
4. Report **git SHA + Vite cwd + base URL** on every run.
5. Prefer a clean report-only audit on an isolated port (`YZU_DESK_URL`, `--strictPort`, `workers=1`) before product patches.

No implementation slice passes because historical components or tests are internally consistent with each other. Acceptance is against current product authority and its incorporated full-scale appendices.
