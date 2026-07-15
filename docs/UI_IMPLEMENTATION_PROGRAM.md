# Research Drive UI Implementation Program

**Status:** Current execution program  
**Authority:** Derived exclusively from [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md) and its incorporated Discover appendix [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md)  
**Scope:** `drive/src/v2/*`, required API contracts, tests, rendered-pixel review

## Rule

Do not change faculty-facing navigation, composition, rail behavior, Preview, truth vocabulary, Discover lifecycle ownership, or procurement-method representation without first amending the product authority. Discover composition changes must amend the full-scale freeze appendix in the same change.

## Slice 1 — Discover Explore composition

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

## Slice 2 — First-class Discover active objects

Goal: the rail always operates the exact selected Discover object.

- Preserve Explore and History selection as separate state.
- `Explore` selection produces `external_candidate`.
- `History` selection produces `discover_lifecycle`.
- `Preview` context is scoped to its parent candidate or lifecycle object.
- Clear stale active object context on mode/page/object transition.
- History row selection must bind the selected lifecycle object to Detail and Ask; `selectedHistoryId` alone is insufficient.
- Extend typed rail context with lifecycle identity, lifecycle state/reason, decision ownership, evidence need, source/candidate identity, procurement method, and supported operations.

Acceptance:

```text
Select Explore result → rail context is that external candidate.
Switch History → stale Explore active context is cleared.
Select History row → rail context is that discover_lifecycle object.
Toggle Detail / Ask → exact object identity remains unchanged.
Switch back Explore → preserved Explore selection can be restored separately.
```

## Slice 3 — History lifecycle projector and compact ledger

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

- Project `decision_owner=researcher` into the `Needs you` priority territory.
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

## Slice 4 — Durable procurement method

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

## Slice 5 — Preview and truth

Goal: Preview is a centre-scoped, accessible evidence overlay with an interactive Detail/Ask rail.

- Replace full-app `aria-modal` behavior with a centre overlay, or make the rail inert; current authority selects the centre-overlay contract.
- Define typed preview payloads for dataset/API, paper, filing, and web source evidence.
- Scope Preview to the selected candidate or lifecycle object.
- Separate observed facts from unestablished facts.
- Carry provider/registry/method authority, freshness, and fallback state through all visible labels.
- Opening Preview never starts collection.

Acceptance:

```text
Preview does not become a route.
Preview does not hide selected-object Detail/Ask.
Source type is visually obvious.
No cached/demo/model result appears as live authority.
```

## Slice 6 — Bounded Detail / Ask

- Rail height is the app viewport; rail content never stretches the page.
- Identity/state is fixed, body uses `min-height: 0; overflow-y: auto`, and decision/action footer remains sticky inside the rail.
- Default Detail has at most five modules, one judgment, 3–5 known facts, three unknowns, one disclosure, one primary action, and up to two secondary actions.
- Remove duplicate semantic modules such as separate Current decision / Execution / Evidence / What happens next when they repeat current state.
- `Technical record ▸` is the one default disclosure and scrolls inside the bounded rail body.
- Pass typed current context to Ask; render evidence artifact authority and clear stale selection on transitions.
- Collapse completed Ask activity by default; retain optional `Agent activity ▸`.
- Successful mutations return compact product receipts and refresh durable state.

Acceptance:

```text
Rail never exceeds shell height.
Primary action remains visible while body/disclosure scrolls.
Centre selection remains visible while Detail/Ask alternates.
Ask operates exact selected candidate or lifecycle object.
Durable mutation → visible centre state change → updated Detail judgment.
```

## Slice 7 — Exact handoffs

- Wire exact object handoffs among Discover, Library, Synthesis, Resources, and Profile context.
- Exact or registered Discover result opens the exact Library asset.
- Registered/query-ready result can open compatible Synthesis blueprints.
- Library and Synthesis gaps create prefilled Discover evidence requirements with existing-input context.
- Resources capability handoff opens Discover with provider/access constraint.

## Slice 8 — Synthesis, Resources, Profile

- Make Synthesis profile reads side-effect free; reserve build/refresh for explicit mutation.
- Surface selected blueprint/output in Detail/Ask with input readiness and gap identity.
- Keep Resources provider capability/constraint ownership.
- Add persisted Profile context and visible unbound/pilot state through all surfaces.

## Test gates

- Unit: URL mode aliases, five-state sufficiency, lifecycle projection, decision ownership, method envelope fallbacks, truth-envelope fallbacks, typed candidate/lifecycle rail context.
- E2E: Explore/History, selected-row rail, no Focused Evaluation takeover, History active-object binding, request-to-route-investigation, route-to-method-review, method-to-execution, schema review, Preview overlay, local sufficiency, request-to-registration, exact handoffs, Ask parity.
- Visual: desktop 1440 first; laptop 1280 second. Tablet/mobile must preserve semantics but do not drive desktop composition. Review 5-item, 20-item, and 70-item History states plus direct API, BigQuery, hard browser source, method failure, schema review, schedule record, and query-ready asset.

### Discover E2E interpretation rule

Before treating any Discover Playwright red as a Slice failure:

1. Classify each test against [`DISCOVER_E2E_AUTHORITY_AUDIT.md`](DISCOVER_E2E_AUTHORITY_AUDIT.md).
2. Discard **ENVIRONMENT FAILURE** runs (wrong Vite tree, contested port, overlapping workers).
3. Do not use **LEGACY EXPECTATION** tests for Activity or Focused Evaluation centre takeover as current acceptance gates.
4. Report **git SHA + Vite cwd + base URL** on every run.
5. Prefer a clean report-only audit on an isolated port (`YZU_DESK_URL`, `--strictPort`, `workers=1`) before product patches.

No later slice begins until the preceding slice passes its behavior and rendered-pixel review under current authority—not under historical Search/Activity or Focused Evaluation anchors.