# Research Drive UI Implementation Program

**Status:** Current execution program  
**Authority:** Derived exclusively from [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md)  
**Scope:** `drive/src/v2/*`, required API contracts, tests, rendered-pixel review

## Rule

Do not change faculty-facing navigation, composition, rail behavior, Preview, truth vocabulary, or lifecycle ownership without first amending the product authority.

## Slice 1 — Discover composition

Goal: Discover is `Explore | History`; a selected source leaves Explore visible and drives Detail/Ask.

- Normalize URL modes to `explore|history`; map legacy Search/Activity/Approvals aliases to Explore with focus state.
- Use the backend Explore source contract for results and the durable Discover History contract for History.
- Move pending approvals into an Explore queue strip or selected request Detail; do not retain Activity as a third tab.
- Remove unselected-row fit badges, local-estate actions, collection actions, and Ask controls.
- Add a focused selected-source Detail projection: ranking reason, five-state local sufficiency, verified evidence, unknowns, access, and primary action.

Acceptance:

```text
Select source → list remains visible → Detail changes.
Explore and History are the only Discover modes.
Legacy URLs land in Explore without losing query/selection context.
History is not sourced from Resources activity events.
```

## Slice 2 — Preview and truth

Goal: Preview is a centre-scoped, accessible evidence overlay with an interactive Detail/Ask rail.

- Replace full-app `aria-modal` behavior with a centre overlay, or make the rail inert; current authority selects the centre-overlay contract.
- Define typed preview payloads for dataset/API, paper, filing, and web source evidence.
- Separate observed facts from unestablished facts.
- Carry provider/registry authority, freshness, and fallback state through all visible status labels.

Acceptance:

```text
Preview does not become a route.
Preview does not hide selected-object Detail/Ask.
Source type is visually obvious.
No cached/demo/model result appears as live authority.
```

## Slice 3 — Lifecycle, handoffs, and Ask

- Render the five local-sufficiency states and preserve their semantic distinction.
- Wire request/approval/active/ready/recovery into durable Discover History.
- Implement exact object handoffs among Discover, Library, Synthesis, Resources, and Profile context.
- Pass typed current context to Ask; render evidence artifact authority and clear stale selection on page changes.

## Slice 4 — Synthesis, Resources, Profile

- Make Synthesis profile reads side-effect free; reserve build/refresh for explicit mutation.
- Surface selected blueprint/output in Detail/Ask with input readiness and gap identity.
- Reduce Resources to provider capability/constraint interpretation.
- Add persisted Profile context and visible unbound/pilot state through all surfaces.

## Test gates

- Unit: URL mode aliases, five-state sufficiency, truth-envelope fallbacks, typed rail context.
- E2E: Explore/History, selected-row rail, Preview overlay, local sufficiency, request-to-registration, exact handoffs, Ask parity.
- Visual: desktop 1440, laptop 1280, tablet 900, mobile 390; review selection, loading, empty, unavailable, recovery, and output states.

No later slice begins until the preceding slice passes its behavior and rendered-pixel review.
