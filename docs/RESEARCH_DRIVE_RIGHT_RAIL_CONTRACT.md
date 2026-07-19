# Research Drive right rail integration contract

**Status:** Active typed rail/backend contract  
**Authority:** Subordinate to [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md), [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md), and [`LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md`](LIBRARY_FULL_SCALE_FREEZE_2026-07-15.md)  
**Scope:** v2 interface and integration: `src/v2/InspectorRail.jsx`, `src/v2/DetailPanel.jsx`, `src/v2/RailPanels.jsx`, `src/v2/AskRail.jsx`, `src/v2/api.js`, active-object adapters, Discover lifecycle projection, Library collection/asset/search projections

The right rail is the product spine. The main destinations are lenses over the same research desk; the rail is where the exact selected object becomes usable, explainable, and actionable.

This contract exists to stop the repo from drifting back into separate products: Drive clone, generic AI chat, ops dashboard, procurement wizard, or a centre workspace that duplicates Detail.

---

## 1. Product rule

Every faculty-facing feature must answer one question first:

> What exact object is selected, and what should Detail or Ask do with that same object?

If a feature cannot produce a typed rail object, it is not ready for the main desk UI.

| Stable concept | Rule |
|---|---|
| Rail width | Desktop target remains a substantial interpretation rail; exact pixel width follows rendered authority. The rail is not a skinny helper drawer. |
| Rail height | Exactly the app viewport/shell height. Rail content never stretches the page. |
| Rail modes | Exactly **Detail** and **Ask**. One visible pane; both may remain mounted. |
| Detail | Structured truth and current decision for the exact selected object. |
| Ask | Composer / Cite-Agent / supported direct equipment scoped to the same selected object. |
| Navigation | Defined exclusively by `UI_PRODUCT_AUTHORITY.md`. |
| Not tabs/pages | Ask, Pipeline, Vault tree, Source, procurement method, approval, route investigation, collection suggestion review, verification comparison. These are rail modes, fields, review states, or lifecycle states. |

Legacy `src/main.jsx` remains cutover debt only. New work uses `src/v2/*` and `Detail | Ask`.

The compounding loop is binding:

```text
Centre
object + state

        ↓

Detail
meaning + current decision

        ↓

Ask
investigate / reason / operate exact object

        ↓

Durable backend consequence

        ↓

Centre
visible state changes

        ↓

Detail
new judgment / next decision
```

---

## 2. Rail viewport and density contract

```text
┌───────────────────────────────┐
│ FIXED IDENTITY / STATE        │
├───────────────────────────────┤
│                               │
│ BOUNDED SCROLL BODY           │
│                               │
│                               │
├───────────────────────────────┤
│ STICKY DECISION / ACTION      │
└───────────────────────────────┘
```

Implementation requirements:

```text
rail shell
height: app shell / viewport height
min-height: 0

identity header
fixed within rail layout

scroll body
min-height: 0
overflow-y: auto

footer/action area
sticky or fixed within rail
remains visible while body scrolls
```

Default Detail budget:

```text
identity / state
2–3 lines

primary judgment
max 3–4 lines

active decision module
state-specific

known facts
prefer 3; maximum 5

unknowns
maximum 3

one default operational disclosure
Technical record ▸

sticky actions
1 primary
maximum 2 secondary
```

Maximum default modules: five.

The rail is a decision instrument, not a report. Do not create separate `Current decision`, `Execution`, `Evidence`, and `What happens next` sections when they restate the same state and action.

`Technical record ▸` remains the default operational/developer disclosure.

Research-native evidence disclosures may also exist when they are ordinary research information rather than diagnostics:

```text
Source record ▸
Source chain ▸
Verification record ▸
```

Expanded disclosures remain inside the bounded scroll body. The sticky footer remains visible.

---

## 3. Generic rail context envelope

The UI maintains one explicit rail context object and sends the structured envelope to chat as `rail_context`.

Conceptual generic shape:

```json
{
  "tab": "library",
  "mode": "detail",
  "entity": {
    "kind": "library_asset",
    "id": "usdt_transactions_v4",
    "title": "Private USDT transactions"
  },
  "selected": {},
  "evidence_scope": {},
  "lifecycle": {},
  "procurement_method": {},
  "library": {},
  "source": {},
  "verification": {},
  "dataset_id": "",
  "folder_id": "",
  "vault_path": "",
  "search_query": "",
  "profile_email": "drkong@saturn.yzu.edu.tw",
  "readiness": "",
  "actions": []
}
```

Rules:

- `Detail` renders canonical fields from structured state, not assistant prose.
- `Ask` receives the same exact context and may use it to choose supported tools/equipment.
- The UI must not expose MCP protocol names to the professor except in developer/admin diagnostics.
- If the selected rail object changes, switch to `Detail` unless the user explicitly invoked an Ask action on the new object.
- If an action needs Composer/Cite-Agent/Ask, switch to `Ask` and submit from the same object context.
- Page, mode, and selected-object transitions must clear stale object context before Ask can act.
- Page-local preserved selections may be restored separately but must not leak into the wrong active-object context.

---

## 4. Entity contracts

| Entity kind | Produced by | Detail must show | Ask / primary operations |
|---|---|---|---|
| `library_collection` | Library collection tree/location | collection meaning, accepted context, evidence estate summary, suggestion state, known gaps, current organisation decision | explain context, compare owned estate, propose related evidence, explain signals, inspect gaps, prepare exact Discover handoff |
| `library_asset` | Library evidence ledger, Home exact resume | research use, readiness, evidence shape/coverage, source, verification, collection memberships, limitations, source/citation actions | explain evidence, inspect source relationship, compare matched source, reason over schema/coverage/provenance, find related evidence, assess use, prepare exact Discover handoff |
| `library_search_match` | Library evidence-estate search | exact match reason + authority + underlying asset truth | explain exact match, reason over exact asset with current match context |
| `external_candidate` | Discover Explore | selected source identity, fit judgment, local sufficiency, verified candidate facts, unknowns, access/acquisition constraint | assess, probe, preview, request evidence, schedule supported refresh, compare local gap |
| `discover_lifecycle` | Discover History | lifecycle state/reason, decision ownership, evidence need, current durable evidence, material method, knowns/unknowns, current decision | investigate route, explain/review/revise method, view evidence, supported execution/schedule actions, exact handoffs |
| `preview_target` | Discover/Library Preview | bounded observed evidence scoped to parent object | ask about observed evidence, return to parent object |
| `cluster_compare` | operational compatibility context only | compared datasets, shared keys/date coverage, gaps, honesty note | ask about overlap, open dataset |
| `resource_row` | Resources | measured value/status/source endpoint/freshness/related capability | explain exact resource object and supported operation |
| `profile_scope` | Profile | research context inputs and named product effects | Ask with this scope, explain ranking/context effect, edit profile |
| `settings_account` | Settings | identity/credential summary/preferences | Save, test connection, setup help |
| `synthesis_recipe` | Synthesis | blueprint identity, inputs, readiness, gaps | explain recipe, inspect gap, supported build/refresh intent |
| `synthesis_output` | Synthesis | output identity, authority, readiness, source inputs | open output, explain provenance/readiness, supported refresh |
| `empty_page` | no selection | page summary and next useful selection | optional Ask |

Do not build page-local detail workspaces that duplicate the rail.

---

## 5. Library active-object contract

Library has three first-class rail contexts:

```text
library_collection
library_asset
library_search_match
```

The active object is always the exact selected Library object.

```text
SELECT COLLECTION
        ↓
library_collection

SELECT ASSET
        ↓
library_asset

SELECT SEARCH RESULT
        ↓
library_search_match
scoped to library_asset
```

Collection and asset selection state are distinct:

```text
current collection location
≠
selected asset
```

Selecting an asset does not erase the current collection location.

Switching back to collection interpretation restores the current collection active object.

A stale asset must not remain the Ask context after the researcher selects a different collection.

---

## 6. Library `library_collection` contract

Selecting a collection produces:

```text
kind = library_collection
```

Conceptual context:

```text
object

kind = library_collection
id = collection_raw_evidence
title = Raw evidence


location

research_context = Stablecoin Research
breadcrumb = Stablecoin Research / Raw evidence
asset_count = 128
query_ready_count = 91


collection_context

description = Primary evidence retained for stablecoin market and event-study research.
signals = Stablecoins, Transactions, Market events
context_authority = description + accepted evidence + active research
accepted_asset_count = 128


suggestion_state

status = ready
count = 3
material_changed_at = ...


known_gaps

count = 4
authority = typed gap records


available_operations

review_suggestions
edit_collection_context
compare_owned_evidence
review_gaps
find_external_evidence
ask_about
```

Collection Detail owns:

```text
collection meaning
estate summary
accepted context
related-evidence suggestion state
known gaps
current organisation decision
```

Example:

```text
RAW EVIDENCE
COLLECTION

Primary evidence retained for
stablecoin market and event-study
research.

EVIDENCE

128 assets
91 query-ready

CONTEXT

Stablecoins
Transactions
Market events

RELATED EVIDENCE

3 owned assets may belong here.

Review suggestions

KNOWN GAPS

4 recorded evidence gaps

Review gaps

Technical record ▸

─────────────────────────────

[ Review suggestions ]

Edit context
Find external evidence
```

The rail may omit `RELATED EVIDENCE` or `KNOWN GAPS` when no typed material state exists. Do not render `0 suggestions` or `0 known gaps` as celebratory completeness claims.

---

## 7. Collection context and suggestion authority

A collection is research organisation, not a physical storage folder.

```text
collection description
+
accepted evidence
+
typed evidence shape / entities / markets / coverage
+
source relationships
+
active research context

        ↓

accepted collection context
```

Do not infer a rich context from title alone.

Suggestion state requires a typed Library comparator over accepted collection context and owned evidence.

Suggestion object concept:

```text
suggestion

collection_id
asset_id
status = proposed | accepted | rejected | dismissed

match_signals
Transactions
Stablecoins
Historical evidence

comparator_authority
accepted_collection_context
asset_registered_metadata
source / evidence shape authority

created_at
updated_at
```

The system may prepare suggestions.

It may not silently add/remove collection membership.

The centre review state is deterministic UI, not chat output:

```text
RELATED EVIDENCE
3 SUGGESTIONS

□ asset
  description
  WHY RELATED
  signal · signal · signal

[ Add selected to Raw evidence ]

Not related
```

Successful membership mutation returns a compact receipt and refreshes collection state:

```text
✓ 2 assets added to Raw evidence
```

The same assets retain one durable identity and may remain members of other collections.

---

## 8. Library `library_asset` contract

Selecting an evidence asset produces:

```text
kind = library_asset
```

Conceptual context:

```text
object

kind = library_asset
id = usdt_transactions_v4
title = Private USDT transactions


asset

description = Historical USDT transfer records supplied by the researcher.
evidence_shape = transactions
entity_count = 47
registered_field_count = 8
coverage = 2020-2024
readiness = query_ready


source

kind = self_provided
label = Self-provided
intake_id = intake_...
original_upload_preserved = true


verification

state = matched
matched_source_id = source:bigquery:usdt
summary = Strong correspondence with BigQuery public USDT records.
matched = transaction identifiers, timestamps, transfer values
unknowns = complete row equivalence, private transformations
record_id = verification_...


collections

Raw evidence
Historical transaction evidence
Event-study inputs


limitations

earlier transaction history not present


available_operations

preview
compare_source_match
use_in_synthesis
manage_collections
find_gap_evidence
open_source_record
open_verification_record
ask_about
```

Asset Detail owns:

```text
asset identity
readiness
plain research-use judgment
evidence shape / coverage
source
verification relationship
collection memberships
limitation
source / citation / verification actions
```

Example:

```text
PRIVATE USDT TRANSACTIONS
QUERY-READY

Historical USDT transfer records
supplied by the researcher.

EVIDENCE

Transactions · 47 entities
8 registered fields
Coverage · 2020–2024

SOURCE

Self-provided
Original upload preserved

VERIFICATION

MATCHED

Strong correspondence with
BigQuery public USDT records.

✓ transaction identifiers
✓ timestamps
✓ transfer values

? complete row equivalence
? private transformations

COLLECTIONS

Raw evidence
Historical transaction evidence
Event-study inputs

Verification record ▸
Source record ▸

─────────────────────────────

[ Preview ]

Compare source match
Use in Synthesis
```

The exact module composition may compress to stay within the global five-module budget. Source, verification, or limitation becomes the active decision module based on the selected asset state.

---

## 9. Library source contract

`SOURCE` answers:

```text
Where did this owned asset come from?
```

Source semantic kinds may include:

```text
provider_source
self_provided
derived_lineage
not_recorded
```

Centre display:

```text
BIGQUERY
GDELT
MOPS
SEC EDGAR
DATACITE
SELF-PROVIDED
2 SOURCES
3 SOURCES
8 SOURCES
NOT RECORDED
```

Self-provided means:

```text
researcher supplied this evidence
original intake / upload record is preserved
no external source is claimed merely by ownership
```

Derived lineage centre display uses source count. The exact registered source chain is a Detail disclosure/action.

Do not concatenate multiple source names into the ledger.

Source record / source chain / citation actions are first-class research actions when authority exists.

---

## 10. Library verification contract

`VERIFICATION` answers:

```text
What relationship has Research Drive established
between this owned asset and authoritative /
sourcable evidence?
```

Semantic states:

```text
verified
matched
partial
unverified
not_checked
```

Centre labels:

```text
VERIFIED
MATCHED
PARTIAL
UNVERIFIED
NOT CHECKED
```

Hard rules:

```text
VERIFIED ≠ THE DATA IS TRUE
MATCHED ≠ DATASETS ARE IDENTICAL
QUERY-READY ≠ EXTERNALLY VERIFIED
```

Verification must be backed by a typed durable comparison/source relationship record.

Composer/Cite-Agent prose does not set verification state.

Conceptual verification record:

```text
verification

id = verification_...
asset_id
state
matched_source_id

comparison_scope
schema
coverage
sampled row identity
source metadata

matched_facts
transaction identifiers
timestamps
raw transfer values

observed_differences
3 derived fields
14-day coverage extension

unknowns
transformation methodology
complete row equivalence

observed_at
source_freshness
verification_authority
```

A supported comparison may durably change:

```text
MATCHED
        ↓
PARTIAL
```

when differences are established.

The centre row updates; Detail explains the new relationship.

---

## 11. Library `library_search_match` contract

Library search is evidence-estate search, not filename search only.

Selecting a search result produces:

```text
kind = library_search_match
parent_kind = library_asset
parent_id = ...
```

Conceptual context:

```text
search_match

query = counterparty address
match_type = field
matched_values = to_address, from_address
match_authority = registered schema

asset = canonical library_asset context
```

Match types may include:

```text
identity
accepted_description
entity
field
source
citation
provenance
coverage
```

Search result row may add a temporary third line:

```text
TITLE                     SOURCE       VERIFY       STATE
plain-language description
MATCH · FIELD · to_address · from_address
```

Detail owns:

```text
MATCH
FIELD

to_address
from_address

Registered fields
✓ from_address
✓ to_address
✓ tx_hash
✓ block_time

SOURCE
BigQuery public datasets

VERIFICATION
VERIFIED
```

The underlying asset truth remains canonical. Search match context explains why it surfaced.

No model prose may invent a field, source, DOI, provenance record, or coverage match.

---

## 12. Library Ask / Composer / Cite-Agent operating contract

The Library rail is not generic folder chat.

The stable tab is:

```text
ASK
```

The visible active intelligence identity may truthfully say:

```text
Composer · selected collection
Composer · selected evidence
Cite-Agent · selected evidence
```

Ask receives:

```text
exact selected Library entity
current collection location
asset identity when selected
accepted collection context when selected
stated evidence scope
source authority
verification authority
readiness
coverage / schema / provenance when authoritative
current search match reason when selected
supported operations
```

For `library_collection`, Ask may:

- explain accepted collection context;
- compare owned evidence against that context;
- prepare related-owned-evidence suggestions;
- explain named suggestion signals;
- inspect typed known gaps;
- prepare an exact Discover evidence requirement;
- open deterministic suggestion/gap review UI.

For `library_asset`, Ask may:

- explain evidence semantics;
- inspect source relationship;
- compare owned evidence with matched sourcable evidence;
- reason over schema, coverage, and provenance;
- find related owned evidence;
- assess research use;
- prepare an exact Discover evidence requirement for a typed limitation/gap;
- open deterministic Preview/source/verification/source-chain UI.

Ask may not:

- invent asset descriptions, fields, source records, citations, provenance, or coverage;
- create verification authority from prose;
- silently add/remove assets from collections;
- autonomously create collection hierarchies;
- silently rewrite accepted collection context;
- upgrade readiness;
- delete an asset when removing it from a collection;
- act on stale asset context while a different collection is selected.

Successful durable Library mutations return compact receipts:

```text
✓ 3 related evidence suggestions recorded
✓ 2 assets added to Raw evidence
✓ Collection context updated
✓ Verification comparison completed
✓ Verification relationship updated to Partial
✓ Evidence gap recorded
✓ Discover requirement prepared
```

A receipt alone is not product completion. Centre/Detail must refresh to the new durable state.

---

## 13. Discover `external_candidate` contract

Explore centre owns the ranked evidence landscape. Selecting a row leaves the list visible and binds:

```text
kind = external_candidate
```

Required semantic context:

```text
entity
kind
id
title

selected
source_id
connector_id
candidate_key
endpoint / source URL when authoritative

query_interpretation / evidence_scope
research object
evidence need
analytical use
coverage constraints
preferred fields

candidate_evidence
grain / evidence shape with authority
coverage with authority
subjects with authority
access with authority
preview state

local_relationship
Exact | Partial | Related | No local alternative | Comparison unknown
comparator authority

match
named signals
score when authoritative
explanation derived from typed facts

available_operations
preview
probe
request_evidence
open_local / compare when supported
schedule_refresh when supported
ask_about
```

Detail owns selected-source interpretation. Ask may investigate or operate the same candidate.

A durable Ask mutation produces a compact receipt and refreshes centre state, for example:

```text
✓ Evidence request recorded
✓ Schedule recorded
```

---

## 14. Discover `discover_lifecycle` contract

History selection must produce a first-class lifecycle rail object. `selectedHistoryId` without a bound active object is not sufficient.

Conceptual context:

```text
object

kind = discover_lifecycle
id = intent_...
title = Historical USDT transactions


lifecycle

state = active
reason = route_investigating
decision_owner = system
decision_reason = null
status_label = ROUTE INVESTIGATING


evidence_need

object = stablecoin transfers
coverage = before 2020
preferred_fields = entity identifiers, transaction identifiers


source

source_id
connector_id
candidate_key


procurement_method

state = investigating
kind = null
method_id = null
equipment = []
engine = null


evidence_state

preview_retained = true
archive = pending / confirmed / unknown
registration = pending / confirmed / unknown
readiness = query_ready / unconfirmed / unavailable / unknown


available_operations

investigate_route
probe_source
test_supported_route
propose_method
schedule_refresh
return_to_source
```

Method review example:

```text
lifecycle
state = needs_you
reason = method_review
decision_owner = researcher

procurement_method
state = review_required
kind = browser_extract
equipment = spectator
engine = playwright
method_id = method_...

available_operations
explain_method
review_method
revise_method
return_to_source
```

The semantic fields are binding even if exact JSON names adapt to backend conventions.

The frontend must not infer final lifecycle state, method truth, or available operations from free-form status regex once normalized backend projection exists.

---

## 15. History projection and decision ownership

History consumes one researcher-facing lifecycle projection, not raw event kinds.

```text
intent
proposal / route
Discover-linked job
archive / manifest
promotion
registry read-back
subscription

        ↓

HISTORY LIFECYCLE PROJECTOR

        ↓

one discover_lifecycle object
```

Required semantic axes:

```text
lifecycle_state
active | ready | needs_recovery | scheduled

decision_owner
researcher | system | none
```

`Needs you` is projected when `decision_owner = researcher`.

One evidence request remains one primary lifecycle object through route investigation, method review, collection/extraction, schema review, archive, registration, and readiness.

Do not map generic `completed` directly to `ready`.

---

## 16. Procurement-method rail contract

Hard procurement is represented through a typed method attached to `discover_lifecycle`.

Method semantic state:

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

Method kind:

```text
api_query
http_manifest
browser_extract
scraper_run
custom_connector
```

Equipment and engine are named only when durable authority establishes them.

Detail method-review example:

```text
HISTORICAL USDT TRANSACTIONS
METHOD REVIEW

Browser extraction proposed

WHY THIS METHOD
Direct collection did not establish
the required historical records.

METHOD
Browser extraction
Spectator · Playwright

ROUTE
1 Open historical archive
2 Traverse periods
3 Traverse stablecoin records
4 Extract required transfer fields

KNOWN
✓ direct route checked
✓ browser route observed
✓ bounded route tested

UNKNOWNS
? traversal completeness
? session stability
? final extraction volume

Technical record ▸

─────────────────────────────
[ Review method ]

Ask about method
Return to source
```

Centre shows only the material cue:

```text
Browser extraction proposed
```

The method does not become a page or permanent worker-configuration block.

---

## 17. Shared Ask operating contract

Ask is the operating intelligence of the selected object, not a generic chat sidecar.

Ask receives:

```text
exact selected entity
current page / mode / location
current lifecycle or Library object state
current decision ownership when applicable
stated evidence scope
source / candidate / verification authority
procurement method when present
supported operations
```

Ask may:

- explain current structured state;
- investigate supported source/acquisition constraints;
- run supported direct equipment paths;
- perform bounded probes, route tests, source comparisons, or estate comparisons;
- propose or revise procurement methods;
- prepare collection suggestions;
- explain verification relationships;
- schedule supported refresh behavior;
- create durable evidence requests;
- record typed gaps when authority supports them;
- queue or operate supported collection paths;
- open deterministic UI intents.

Ask may not:

- create canonical facts from prose;
- invent legal clearance or entitlement;
- invent equivalence, verification, or query readiness;
- silently approve irreversible operations;
- silently change collection membership;
- act on stale context from a prior selection.

Active tool activity may be compact and evolving. Completed activity collapses by default; optional `Agent activity ▸` may disclose it.

Successful mutations return compact product receipts and must refresh visible product state.

---

## 18. Backend mapping

Use `/library/*` for new integrations. `/yzu/*` remains a compatibility surface when no `/library/*` route exists yet.

| UI need | HTTP route / contract | Notes |
|---|---|---|
| Library asset list | `GET /datasets` / current registry-backed list | Frontend never reads registry JSON directly. Must adapt to Library asset projection. |
| Library asset detail | `GET /datasets/{id}` / typed asset detail | Must converge to source, verification, readiness, collection membership, and limitation authority. |
| Library collections | typed Library collection API required | Must represent research organisation, multi-membership, context authority, and counts; not raw filesystem directories. |
| Library collection suggestions | typed Library comparator / suggestion store required | Suggestions are durable review state; no silent membership mutation. |
| Library verification | typed source-comparison/verification contract required | Establishes Matched/Partial/Unverified outcomes and exact comparison facts. |
| Library search | typed evidence-estate search contract required | Search identity/description/entity/field/source/citation/provenance/coverage with exact match reason. |
| Preview rows | `GET /query/{id}?limit=50` or typed Preview contract | Centre overlay; does not navigate away or mutate verification. |
| Discover Explore | `/library/discover/sources` / current Explore source contract | Produces typed external candidates. |
| Discover History | `/library/discover/history` / lifecycle projector | Must converge from raw compatibility feed to one lifecycle object per evidence request. |
| Ask rail | `POST /library/chat/stream` | Composer/direct equipment + typed `rail_context`. |
| Fallback chat | `POST /library/chat` | Same brain, non-streaming fallback. |
| Jobs | `GET /library/jobs`, approval/action routes | Jobs are internal durable machinery; History projects researcher-facing lifecycle. |
| Resources | `GET /library/desk/resources`, `GET /library/ops` | Capability/usage/method truth as owned by Resources authority. |
| Acquisitions | `GET /yzu/acquisitions` | Compatibility until folded into `/library/*`. |
| Profile | `GET /library/faculty/profile?email=` | Ranking and Ask context. |
| Warm session | `POST /library/desk/warm` | Prime Composer and vault brief. |

Text `[context: ...]` prefixes are compatibility only. Structured rail context is the authority target.

---

## 19. Composer and direct-equipment procurement path

The rail does not implement a Python planner in React. Composer reasons over typed context; direct equipment paths may bypass Composer when an action is explicit and safe to dispatch.

Conceptual procurement path:

```text
selected candidate / lifecycle object
  → local registry / source facts / comparator context
  → known direct route when established
  → bounded probe when route is not established
  → procurement-method investigation
  → direct API / HTTP manifest / query route / browser extraction / scraper route / custom connector proposal
  → review when decision ownership belongs to researcher
  → execution
  → archive verification
  → promotion / registry read-back
  → readiness truth
```

Conceptual Library reasoning path:

```text
selected collection / asset
  → registered asset / collection context
  → source / provenance / readiness authority
  → typed verification / schema / coverage authority when present
  → owned-estate comparison or bounded source comparison
  → prepare suggestions / verification result / typed gap
  → researcher review where membership or context changes
  → durable Library mutation
  → same collection / asset state refresh
```

Professor-facing copy says `Ask`, `Composer` or `Cite-Agent` only when truthful, `Request this evidence`, `Review method`, `Preview`, `History`, `Library`, `Review suggestions`, `Compare source match`, and `Resources`.

It does not expose MCP protocol names or internal planner modules.

---

## 20. Tab grounding

| Tab | Main canvas owns | Rail Detail owns | Ask owns |
|---|---|---|---|
| Home | intention, needs-you, continue/recent | selected attention/research context | resume or investigate exact selected work |
| Library | current research location, collections, durable evidence estate, estate search | selected collection context or selected asset authority/source/verification/readiness | collection organisation, source/verification reasoning, exact gap preparation on selected Library object |
| Discover Explore | ranked external evidence landscape | selected candidate fit, local relationship, facts, unknowns, decision | investigate/probe/request/schedule supported operations on selected candidate |
| Discover History | priority + compact lifecycle ledger | selected lifecycle state, evidence need, material method, current decision | investigate/operate exact lifecycle object |
| Synthesis | blueprints, readiness, outputs | selected blueprint/output and gap | blueprint/output-scoped explanation and supported action |
| Resources | capability, consumption, method topology | selected capability/metric/node interpretation | explain exact resource object and supported operation |
| Profile | research context | selected scope/ranking effect | ranking/procurement with that profile context |
| Settings | preferences and credential summaries | contextual help | setup help only |

---

## 21. Visual direction

Preserve:

- a dense, stable rail that explains the exact selected object;
- stronger instrumental character than the centre without turning the app into a dark ops console;
- source/provenance/verification/readiness evidence when part of the current decision;
- sticky primary action and restrained secondary actions;
- cobalt only for selection and meaningful action.

Drop:

- full-screen terminal styling;
- generic assistant cards;
- duplicate navigation trees;
- page-local detail workspaces that eat the rail's job;
- vertically unbounded report-like rail modules;
- permanent execution timelines after completion;
- Library centre dashboards for suggestions/gaps;
- generic folder-chat framing;
- source/verification claims compressed into unexplained badges.

---

## 22. Upgrade rule

New capabilities attach to a typed object/rail contract before they become navigation:

| Capability growth | Where it appears first |
|---|---|
| New data source | Discover row + `external_candidate` Detail |
| New procurement route/engine | `discover_lifecycle.procurement_method` + material centre cue + Detail |
| New collected evidence asset | Library row + `library_asset` Detail |
| New collection intelligence | `library_collection` context / suggestion state + Detail |
| New verification capability | `library_asset.verification` + Compare source match / Verification record |
| New Library search authority | `library_search_match` typed match reason |
| New worker/job type | backend machinery; Resources capability/method where faculty-relevant; History only through lifecycle projection |
| New profile signal | Profile scope + Ask context |
| New storage tier | Resources storage/method truth + asset provenance |
| New query backend | asset readiness + Preview/Detail truth |

If a feature needs its own full page, prove why the typed object and rail are insufficient and amend product authority first.

---

## 23. Acceptance checklist

- [ ] Every faculty destination uses the same `InspectorRail` grammar.
- [ ] Rail height is bounded to the app shell; body scrolls internally; action footer remains visible.
- [ ] Selecting a Library collection binds `library_collection` and switches rail to `Detail`.
- [ ] Selecting a Library asset binds `library_asset`, preserves current collection location, and switches rail to `Detail`.
- [ ] Selecting a Library search result binds `library_search_match` scoped to the exact underlying asset.
- [ ] Library Detail renders source, verification, readiness, and membership from structured authority, not Composer prose.
- [ ] Library Ask may prepare collection suggestions but cannot silently change membership.
- [ ] Library Ask may compare source matches but cannot set verification without durable comparison authority.
- [ ] Successful Library mutation returns a receipt and visibly refreshes the same collection/asset state.
- [ ] Selecting an Explore candidate switches rail to `Detail` and leaves ranked results visible.
- [ ] Explore selection binds `external_candidate` context.
- [ ] Switching to History clears stale Explore active context.
- [ ] Selecting a History row binds `discover_lifecycle` context and switches to `Detail`.
- [ ] Detail/Ask toggles preserve exact object identity.
- [ ] Search/Ask/request actions use the same selected context.
- [ ] `Ask` may persist session state but cannot act on stale object context.
- [ ] `Detail` does not rely on Composer prose for canonical fields.
- [ ] History lifecycle state is backend-projected; final frontend does not own state through regex bucketing.
- [ ] Procurement method is visible when material and hidden when routine/irrelevant.
- [ ] Completed Ask activity collapses by default; durable mutation returns a product receipt.
- [ ] A receipt-triggered refresh produces visible centre/Detail state change.
- [ ] No v2 UI revives Activity, Pipeline, Source, Focused Evaluation, AI Organiser, or Library Procure as faculty composition.

The rail is visually intense only for an active evidence/research object or Ask. It must not impose a permanent empty inspector on an idle page.
