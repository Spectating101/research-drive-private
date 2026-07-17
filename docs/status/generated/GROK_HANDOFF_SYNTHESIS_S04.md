# Builder handoff — implement Research Drive Synthesis S-04

Branch: `agent/synthesis-s04-spec`  
Base implementation branch: `feat/discover-main-converge`  
Date: 2026-07-18  
Canonical product spec: `docs/product/SYNTHESIS_S04_PRODUCT_SPEC.md`

## Mission

Replace the current narrow Synthesis surface with the S-04 AI-native product model without weakening the rest of Research Drive.

The implementation must make this user experience real:

```text
STATE A RESEARCH NEED
        ↓
SEE AND CORRECT THE AI INTERPRETATION
        ↓
REVIEW ONE RECOMMENDED CONSTRUCTION
        ↓
ACCEPT AND DESIGN THE METHOD
        ↓
RESOLVE ONE MATERIAL DECISION AT A TIME
        ↓
PREVIEW THE ACTUAL OUTPUT
        ↓
BUILD, VERIFY, AND REGISTER
        ↓
REOPEN, REFRESH, AND USE THE ASSET
```

Do not interpret this as permission to build only a static mock. Where backend capability is missing, define and implement the required contract rather than reducing the product to current routes.

## Existing implementation context

Primary frontend files:

- `drive/src/v2/SynthesisPage.jsx`
- `drive/src/v2/api.js`
- `drive/src/v2/useAskChat.js`
- `drive/src/v2/InspectorRail.jsx`
- `drive/src/v2/PageRailPanel.jsx`
- `drive/src/v2/V2App.jsx`
- Synthesis styles under `drive/src/v2/`

Existing Synthesis capabilities on the current branch include:

- registered profile listing and detail;
- profile execution;
- two-dataset pair execution;
- client-side compatibility summaries;
- contextual Ask;
- Library opening after output.

A richer prior branch/experiment also established useful concepts:

- durable Synthesis threads;
- linked Ask sessions;
- structured AI proposals;
- accept/reject proposal patches;
- Discover evidence-gap handoffs;
- approval-queued execution;
- durable execution polling;
- manifest and registration proof;
- reload persistence.

Reuse strong contracts and tested lifecycle behavior where practical. Do not restore the previous graph canvas as the primary interface.

## Product boundaries

### Must preserve

- global `Navigation | Centre | Detail / Ask` grammar;
- existing Library, Discover, Resources, Profile, Home, and Preview behavior;
- honest readiness and registration states;
- contextual Ask;
- responsive shell behavior;
- existing API compatibility where possible;
- current CI and Playwright coverage.

### Must remove or demote

- blueprint catalogue as the opening mental model;
- predefined profile selection as the dominant Synthesis experience;
- custom-pair assembly as the main creation route;
- client-only compatibility claims presented as authoritative execution validation;
- graph-first construction workbench;
- separate centre prompt and Ask histories;
- giant specification walls;
- multiple equal-weight recommendation cards;
- chat-only state changes;
- any claim that a preview or registration happened without evidence.

## Canonical frontend architecture

Recommended component decomposition:

```text
SynthesisPage
├── SynthesisWorkspaceList
├── SynthesisStageHeader
├── ExploreStage
│   ├── ResearchBrief
│   ├── RecommendedConstruction
│   ├── SemanticConstructionDiagram
│   ├── AlternativeConstructionOverlay
│   └── NextConsequence
├── DesignStage
│   ├── ConciseMethodSummary
│   ├── ResolvedDecisionSummary
│   ├── MaterialDecisionPrompt
│   └── FullMethodDrawer
├── TestStage
│   ├── PreviewVerdict
│   ├── PreviewSample
│   ├── DiagnosticSummary
│   └── DiagnosticDrawer
├── BuildStage
│   ├── BuildProgress
│   ├── OutputEstimate
│   └── TechnicalLogDrawer
├── RegisteredStage
│   ├── RegisteredAssetSummary
│   ├── VerificationSummary
│   ├── SavedConstructionActions
│   └── EmpiricalUseGuide
└── SynthesisAskContextAdapter
```

Do not force this exact file split if a cleaner implementation exists. Preserve the behavioral boundaries.

## State requirements

Use a durable thread object rather than scattered page-local booleans.

Minimum state:

```ts
{
  id,
  title,
  objective,
  interpretation,
  selectedAssetIds,
  recommendedConstruction,
  alternativeConstructions,
  acceptedConstructionId,
  method,
  decisions,
  compilation,
  previews,
  execution,
  outputs,
  conversationId,
  revision,
  createdAt,
  updatedAt
}
```

Required stage/status values:

```text
DRAFT_INTENT
INTERPRETING
EXPLORATION_READY
CONSTRUCTION_ACCEPTED
DESIGNING_METHOD
DECISION_REQUIRED
METHOD_READY
COMPILING
PREVIEW_RUNNING
PREVIEW_READY
PREVIEW_BLOCKED
BUILD_PENDING_APPROVAL
BUILD_QUEUED
BUILD_RUNNING
VERIFYING
REGISTERING
REGISTERED
FAILED
STALE_INPUTS
REFRESH_AVAILABLE
```

## Ask integration

This is the highest-priority interaction correction.

### One thread

The centre objective composer and Ask must create one conversation.

The first centre submission should:

1. create or retrieve a durable Synthesis thread;
2. append the objective as the first user message;
3. attach selected Library/Discover context;
4. open Ask by default;
5. request interpretation and recommended constructions;
6. render structured results in the centre;
7. persist the linked conversation ID.

The user must not retype the objective in Ask.

### Ask context

Send Ask:

```text
thread identity
objective
active stage
current interpretation
selected assets
recommended construction
selected evidence object
method revision
open decision
preview warning
execution state
active research project
```

### Structured AI artifacts

Ask should return structured artifacts in addition to prose:

```text
synthesis_interpretation
construction_proposals
construction_patch
method_proposal
method_decision
preview_interpretation
execution_recommendation
empirical_use_guide
```

Prose explains. Structured artifacts update the centre only after the correct approval flow.

### Visible diffs

A conversational change must produce a centre diff before persistence.

Example:

```text
Target grain
asset-week → asset-month

GDELT role
core candidate → validation only

Effect
monthly aggregation, lower expected row count, unchanged construct

[ REJECT ] [ APPLY CHANGE ]
```

## Explore implementation

### Opening hierarchy

1. restrained state label: `EXPLORATION READY`;
2. research brief;
3. one recommended construction;
4. compact semantic diagram;
5. ideal unavailable evidence;
6. expected output;
7. AI-resolved versus later decisions;
8. collapsed alternatives;
9. exact next consequence;
10. `ACCEPT & DESIGN METHOD`.

### Semantic diagram

The diagram is explanatory, not editable.

It should support:

- target construct;
- evidence families;
- concrete sources;
- semantic construction step;
- output;
- validation source;
- unavailable ideal measure.

Use layout and connecting lines, but do not restore React Flow interaction, draggable nodes, minimaps, or a graph editor mental model.

### Alternative constructions

Open a temporary overlay or drawer. Do not place three permanent full-size cards in the main flow.

### Action semantics

`ACCEPT & DESIGN METHOD` must:

- persist the accepted construct and evidence architecture;
- increment the thread revision;
- request detailed method design;
- transition to Design;
- not execute data;
- not create a Library output.

## Design implementation

Default centre view:

```text
AI-DESIGNED METHOD

Evidence       Trends · Reddit · Wikipedia
Grain          asset-week
Construction   align → normalise → combine → validate
Output         stablecoin_attention_weekly

✓ routine decisions resolved
! one methodological decision needs review

[ VIEW FULL METHOD ]                  [ REVIEW DECISION ]
```

Only one open decision should dominate Ask.

Examples:

- component weighting;
- minimum available components;
- event window;
- point-in-time convention;
- treatment/control definition;
- winsorization rule.

Each decision must include:

```text
recommendation
alternatives
reason
research consequence
execution consequence
reversibility
```

Authority labels:

```text
OBSERVED
SOURCE-DEFINED
AI RESOLVED
RESEARCHER DECISION
BLOCKED
UNSUPPORTED
```

Applying a decision must persist across reload and create a new revision.

## Compiler requirements

Do not mark a method executable merely because the AI wrote plausible prose.

Implement or expose a compiler that maps semantic steps to deterministic operations.

Minimum operation registry:

```text
read
select
filter
rename
cast
derive
aggregate
resample
join
entity_map
deduplicate
point_in_time_align
event_align
window_transform
normalize
rank
winsorize
restrict_coverage
matched_sample
custom_code
validate
register
```

Compilation result must classify every semantic step as:

```text
SUPPORTED
BLOCKED
UNSUPPORTED
DECISION_REQUIRED
```

Compilation should return:

- execution plan;
- output contract;
- verification contract;
- unresolved items;
- estimated resource use;
- immutable accepted revision hash.

## Preview implementation

A real bounded preview is required.

It should return:

- sample rows;
- output schema;
- row count;
- entity match rate;
- key uniqueness;
- coverage;
- missingness;
- join loss;
- source contribution;
- validation results;
- field lineage;
- warnings;
- blockers.

Ask should interpret the most important warning before the centre exposes raw diagnostic detail.

Default verdict language:

```text
READY TO BUILD
READY TO BUILD — WITH DOCUMENTED WARNING
METHOD REVISION RECOMMENDED
BLOCKED
```

No preview result may be mocked as real in production.

## Build implementation

Build is revision-bound and approval-aware.

Required lifecycle:

```text
READY
PENDING_APPROVAL
APPROVED
QUEUED
RUNNING
PRODUCED
VERIFYING
ARCHIVING
REGISTERING
REGISTERED
FAILED
CANCELLED
```

Visible build phases should remain research-semantic:

```text
Prepare inputs
Align entities
Align time
Construct components
Create output
Verify output
Register in Library
```

Do not expose worker telemetry in the primary centre.

Required registered proof:

```text
output dataset identity
row count
field count
entity count
coverage
manifest identity
source snapshots
verification summary
Drive/archive verification
Library query readiness
accepted revision hash
```

Failure must show a grounded error and allow retry.

## Registered and empirical-use implementation

Registered stage actions:

```text
OPEN IN LIBRARY
PREVIEW
DOWNLOAD MANIFEST
VIEW METHOD
DUPLICATE & MODIFY
REFRESH OUTPUT
```

Empirical-use guidance must inspect actual output metadata and diagnostics.

It may propose candidate designs and limitations. It may not assert causal validity.

Actions may include:

```text
DRAFT EMPIRICAL PLAN
CREATE NOTEBOOK
ASK ABOUT IDENTIFICATION
```

## Cross-page contracts

### Library → Synthesis

Selected assets should create a new Synthesis with:

- asset IDs retained;
- active project retained;
- Ask aware of the selection;
- objective optional;
- evidence roles inferred, not assumed final.

### Synthesis → Discover

Evidence-gap handoff preserves:

- thread ID;
- objective;
- evidence family and role;
- target grain and coverage;
- required fields;
- held evidence;
- missing evidence;
- reason it matters.

### Discover → Synthesis

After acquisition/registration, return the asset to the active thread and rerun evidence inspection.

### Synthesis → Library

Registered output opens as the exact registered dataset identity, not title matching.

### Registered output → Synthesis

Allow refresh, extension, and duplicate-and-modify.

## Styling direction

Target visual character:

- premium, calm, decisive;
- light-mode Research Drive grammar;
- spacious centre hierarchy;
- compact semantic diagram;
- restrained status language;
- no dashboard-card explosion;
- no decorative AI gimmicks;
- no excessive sparkle icons;
- one dominant centre artifact;
- right rail dense enough to be useful, not essay-like.

At rest, the user should see:

```text
what they asked for
what the AI understood
what the AI recommends
why it recommends it
what will happen next
```

## Required Playwright tests

1. New objective becomes the first Ask turn.
2. Ask interpretation appears in the centre.
3. Longitudinal versus event interpretation correction regenerates the recommendation.
4. Recommended construction survives reload.
5. Alternative comparison opens and closes without changing state.
6. `ACCEPT & DESIGN METHOD` creates no output and enters Design.
7. Method decision acceptance persists across reload.
8. Compilation reports unsupported operations honestly.
9. Preview returns actual sample and diagnostics.
10. Preview creates no Library write.
11. Warning acceptance is revision-bound.
12. Build request and approval are distinct.
13. Active build survives reload.
14. Failure can be retried.
15. Registered output shows manifest and opens in Library.
16. Evidence gap opens Discover with the correct brief.
17. Newly registered evidence returns to the thread.
18. Ask context follows selected evidence and stage.
19. Mobile preserves the centre summary and deliberate Ask access.
20. No primary state depends on raw IDs or title matching.

## Migration approach

Do not delete working profile execution immediately.

Recommended migration:

1. retain profile execution as a legacy/runtime route;
2. wrap known profiles as accepted construction templates;
3. make intent-first Synthesis the default opening;
4. expose predefined profiles only as reusable prior constructions or starting examples;
5. remove the old blueprint sidebar once the new opening is validated;
6. preserve pair execution as an internal operator or fallback, not a primary UI mode.

## Definition of done for the builder

The implementation is not done when the S-04 screen looks correct.

It is done when:

- the visual hierarchy matches the canonical spec;
- Ask and the centre use one durable conversation;
- structured AI artifacts drive the centre;
- state survives reload;
- method decisions are explicit and revisioned;
- compilation is honest;
- preview runs on actual data;
- build and registration are proven;
- cross-page handoffs retain identity;
- tests cover the full lifecycle;
- no current page regressions are introduced.

## Builder warning

Do not reduce the specification because the current backend lacks a route. Implement the missing contract or leave the state explicitly blocked. A subpar product that merely exposes current backend limitations is not an acceptable interpretation of this handoff.
