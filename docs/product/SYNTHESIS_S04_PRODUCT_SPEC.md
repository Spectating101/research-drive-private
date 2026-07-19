# Research Drive Synthesis — canonical product specification (S-04)

Status: canonical product direction, not yet implemented  
Branch: `agent/synthesis-s04-spec`  
Base: `feat/discover-main-converge`  
Date: 2026-07-18

## 1. Product thesis

Synthesis is the Research Drive workspace that turns a research intention and available evidence into a defensible, executable, verified, reusable research asset.

Its governing question is:

> The research asset or measure I need does not cleanly exist. What is the strongest defensible thing the lab can construct from held, queryable, sourceable, licensed, missing, and derivable evidence?

Synthesis is not:

- a generic join studio;
- a blueprint catalogue;
- a manual node editor;
- a pipeline canvas;
- a notebook replacement;
- a chat product with a dataset page beside it;
- an opaque one-shot prompt that silently builds data.

The product model is:

```text
RESEARCH INTENT
or
OWNED / REACHABLE EVIDENCE
        │
        ▼
AI EXPLORES POSSIBLE RESEARCH ASSETS
        │
        ▼
RESEARCHER SELECTS OR CORRECTS ONE DIRECTION
        │
        ▼
AI DESIGNS A DEFENSIBLE CONSTRUCTION
        │
        ▼
MATERIAL DECISIONS ARE RESOLVED
        │
        ▼
PLAN COMPILES INTO EXECUTABLE OPERATIONS
        │
        ▼
BOUNDED PREVIEW + DIAGNOSTICS
        │
        ▼
BUILD + VERIFY + REGISTER
        │
        ▼
REUSABLE LIBRARY ASSET
        │
        ├── REFRESHABLE CONSTRUCTION
        └── EMPIRICAL-USE GUIDANCE
```

## 2. Core experience principle

The system may be technically deep. The researcher should experience only the next consequential decision.

```text
SYSTEM COMPLEXITY

evidence inspection
construct design
method compilation
preview execution
diagnostics
verification
registration
empirical interpretation


USER EXPERIENCE

“What do you need?”
        ↓
“Here is my recommended construction.”
        ↓
“One decision needs you.”
        ↓
“Preview looks sound, with one warning.”
        ↓
“Build it.”
```

Non-negotiable UX rules:

1. One recommendation by default.
2. One primary action.
3. Zero or one material decision at a time.
4. Technical details remain available, but collapsed until requested.
5. AI interprets diagnostics before exposing raw diagnostics.
6. Routine reversible decisions are resolved automatically and disclosed.
7. Methodologically consequential decisions require explicit researcher approval.
8. Every action states its exact consequence.
9. No output is called registered until registration evidence exists.
10. No page should force the user to operate underlying infrastructure.

## 3. App grammar

The product retains the Research Drive shell:

```text
NAVIGATION | CENTRE | DETAIL / ASK
```

Synthesis gives each area a distinct authority.

### Centre

The centre stores durable product state:

- research brief;
- accepted construct;
- evidence architecture;
- method;
- unresolved decisions;
- preview result;
- build state;
- registered output;
- reusable construction definition.

### Detail

Detail reports factual truth about the selected object:

- source identity;
- evidence role;
- grain;
- coverage;
- readiness;
- provenance;
- current state;
- lineage;
- verification result.

### Ask

Ask is attached to the user's intent, not merely the selected object.

Ask:

- interprets the initial prompt;
- identifies material ambiguity;
- recommends a construction;
- explains why;
- accepts conversational constraints;
- proposes structured state changes;
- interprets diagnostics;
- explains methodological consequences;
- proposes cross-page handoffs;
- supports downstream empirical reasoning.

The governing contract is:

```text
DETAIL IS ATTACHED TO THE SELECTED OBJECT.
ASK IS ATTACHED TO THE USER’S INTENT.
THE CENTRE IS WHERE THEIR AGREEMENT BECOMES DURABLE.
```

## 4. One durable Synthesis thread

The large centre prompt is the first turn of Ask. It is not a separate search box.

```text
CENTRE PROMPT
        ↓
FIRST USER TURN IN THE SYNTHESIS THREAD
        ↓
ASK INTERPRETS THE REQUEST
        ↓
CENTRE RECEIVES A STRUCTURED RESEARCH BRIEF
        ↓
ASK EXPLAINS THE RECOMMENDATION
        ↓
USER ACCEPTS OR CORRECTS IT
```

The durable thread should contain:

```text
objective
conversation
selected evidence
AI interpretation
alternative constructions
accepted construct
method decisions
construction state
preview records
execution records
registered outputs
refresh history
```

There must not be two independent histories for the centre prompt and Ask.

## 5. State model

Synthesis is one persistent workspace whose centre changes by stage.

```text
EXPLORE → DESIGN → TEST → BUILD → REGISTERED → USE
```

Before a construction is accepted, the interface should not present a five-stage wizard. The opening state uses the restrained label `EXPLORATION READY`.

After acceptance, the stage strip may appear:

```text
EXPLORE ✓   DESIGN ●   TEST   BUILD   REGISTERED
```

Recommended durable states:

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

## 6. Canonical opening state — S-04

The opening state proves four things immediately:

1. the user's intent was understood;
2. the AI selected one recommended construction;
3. the recommendation is grounded in evidence roles;
4. nothing has been built or modified yet.

```text
┌────────────────────────┬──────────────────────────────────────────────────────────────────────────────┬──────────────────────────────────────┐
│ RESEARCH DRIVE         │ SYNTHESIS / HISTORICAL STABLECOIN ATTENTION                                 │ DETAIL                 ASK ●         │
│                        │                                                                              │ SYNTHESIS THREAD                     │
│    Home                │ EXPLORATION READY                                                            │                                      │
│    Library             │                                                                              │ YOUR INTENT                          │
│    Discover            │ HISTORICAL STABLECOIN ATTENTION                                              │                                      │
│  ● Synthesis           │                                                                              │ Build a defensible weekly measure    │
│    Resources           │ ┌──────────────────────────────────────────────────────────────────────────┐ │ of public attention to individual  │
│    Profile             │ │ RESEARCH BRIEF                                              EDIT INTENT │ │ stablecoins from 2021 onward.      │
│                        │ │                                                                          │ │                                      │
│ ────────────────────── │ │ A reusable longitudinal measure of observable public attention to       │ │ AI INTERPRETATION                   │
│                        │ │ individual stablecoins, constructed from held and reachable evidence.    │ │                                      │
│ ACTIVE WORK            │ │                                                                          │ │ Longitudinal research measure       │
│                        │ │ Target grain     asset × week                                            │ │ rather than an event-only panel.    │
│ ● Stablecoin attention│ │ Target period    2021 onward                                             │ │                                      │
│   Incident response    │ │ Intended use    reusable input for later empirical studies               │ │ No blocking ambiguity               │
│   JKSE PIT revisions   │ └──────────────────────────────────────────────────────────────────────────┘ │                                      │
│                        │                                                                              │ IMPORTANT ASSUMPTION                 │
│ ＋ New synthesis       │ RECOMMENDED CONSTRUCTION                                                    │                                      │
│                        │                                                                              │ Depegs and security incidents are    │
│ ────────────────────── │ ┌──────────────────────────────────────────────────────────────────────────┐ │ downstream applications of this    │
│                        │ │ COMPOSITE WEEKLY ATTENTION INDEX                          RECOMMENDED   │ │ measure—not its defining object.   │
│ REGISTERED OUTPUTS     │ │                                                                          │ │                                      │
│                        │ │                 HISTORICAL STABLECOIN ATTENTION                           │ │ [ Make event response primary ]     │
│ Trust weekly panel     │ │                              │                                           │ │                                      │
│ Security event panel   │ │              ┌───────────────┼───────────────┐                           │ │ [ Keep longitudinal measure ]       │
│                        │ │              │               │               │                           │ │                                      │
│                        │ │              ▼               ▼               ▼                           │ │ WHY THIS ROUTE                      │
│                        │ │        SEARCH INTENT    COMMUNITY ACTIVITY   PUBLIC VISIBILITY            │ │                                      │
│                        │ │        Google Trends    Reddit activity      Wikipedia views              │ │ • best longitudinal coverage        │
│                        │ │        asset-week       asset-week           asset-day                    │ │ • complementary evidence roles      │
│                        │ │              │               │               │                           │ │ • transparent construct             │
│                        │ │              └───────────────┬───────────────┘                           │ │ • reusable across later studies     │
│                        │ │                              ▼                                           │ │                                      │
│                        │ │                     ALIGN + NORMALISE                                    │ │ MAIN LIMITATION                     │
│                        │ │                              │                                           │ │                                      │
│                        │ │                              ▼                                           │ │ This is a defensible proxy—not      │
│                        │ │                COMPOSITE ATTENTION INDEX                                 │ │ direct historical audience data.    │
│                        │ │                              │                                           │ │                                      │
│                        │ │                              │ validate against                          │ │                                      │
│                        │ │                              ▼                                           │ │                                      │
│                        │ │                         GDELT NEWS                                       │ │                                      │
│                        │ │                    external visibility                                  │ │                                      │
│                        │ │                                                                          │ │                                      │
│                        │ │ IDEAL DIRECT MEASURE                                                     │ │                                      │
│                        │ │ Historical X follower growth       unavailable · no verified history    │ │                                      │
│                        │ │                                                                          │ │                                      │
│                        │ │ EXPECTED OUTPUT                                                          │ │                                      │
│                        │ │ Stablecoin attention weekly panel                                       │ │                                      │
│                        │ │ asset-week · estimated 2021–2026 · reusable Library asset               │ │                                      │
│                        │ │                                                                          │ │                                      │
│                        │ │ AI HAS ALREADY RESOLVED                                                  │ │                                      │
│                        │ │ source roles · target grain · validation role · initial entity strategy  │ │                                      │
│                        │ │                                                                          │ │                                      │
│                        │ │ METHOD DESIGN WILL RESOLVE                                               │ │                                      │
│                        │ │ component weighting · missing-component rule                             │ │                                      │
│                        │ │                                                                          │ │                                      │
│                        │ │ 2 alternative constructions available                              ▸    │ │                                      │
│                        │ └──────────────────────────────────────────────────────────────────────────┘ │                                      │
│                        │                                                                              │ QUICK QUESTIONS                      │
│                        │ WHAT HAPPENS NEXT                                                            │                                      │
│                        │                                                                              │ [ Why is GDELT validation? ]         │
│                        │ Accepting this construction will not build data yet. The AI will draft the  │ [ Compare other constructions ]      │
│                        │ detailed method and surface only choices that materially change the output. │ [ What decisions come next? ]        │
│                        │                                                                              │                                      │
│                        │ [ COMPARE ALTERNATIVES ]                         [ ACCEPT & DESIGN METHOD ]   │ ┌──────────────────────────────────┐ │
│                        │                                                                              │ │ Correct the interpretation, add │ │
│                        │                                                                              │ │ a constraint, or ask a question…│ │
│                        │                                                                              │ └──────────────────────────────────┘ │
│                        │                                                                              │                              SEND →  │
├────────────────────────┼──────────────────────────────────────────────────────────────────────────────┼──────────────────────────────────────┤
│ Stablecoin Research    │ AI recommendation ready · nothing built or modified                         │ Intent, feedback and Ask are linked  │
└────────────────────────┴──────────────────────────────────────────────────────────────────────────────┴──────────────────────────────────────┘
```

## 7. Explore behavior

### Input modes

Synthesis may begin from:

1. a natural-language research objective;
2. selected Library assets;
3. an evidence gap or acquired asset handed off from Discover;
4. a saved construction to refresh or duplicate;
5. a registered output to extend.

### AI exploration

The AI may propose arbitrary research objects, including:

- proxy variables;
- indices and factors;
- longitudinal reconstructions;
- derived feature panels;
- event datasets;
- combined research panels;
- matched samples;
- transformed series;
- reusable research-asset specifications.

The default presentation is one strongest recommendation. Alternatives remain collapsed until explicitly compared.

### Alternative comparison

`COMPARE ALTERNATIVES` opens a temporary centre overlay:

```text
CURRENT RECOMMENDATION
Composite behavioural index

ALTERNATIVE
News-visibility index
Simpler, but narrower construct

ALTERNATIVE
Follower-history reconstruction
Closer to the ideal measure, but sourcing is unresolved
```

Closing the overlay returns to the focused recommendation.

### Clarification threshold

Ask interrupts only when different answers would produce materially different research objects.

Ask now:

- longitudinal measure versus event-response panel;
- firm-week panel versus event-relative-day panel;
- complete-chain catalogue versus selected-contract transfers.

Resolve and disclose:

- date parsing;
- canonical formatting;
- documented unit conversions;
- routine aggregation implied by the accepted target grain.

Ask later:

- weighting;
- missing-component threshold;
- treatment/control definition;
- winsorization;
- event-window convention.

## 8. Accepting the construction

Primary action:

```text
ACCEPT & DESIGN METHOD
```

Exact consequence:

```text
ACCEPT

the construct
the evidence architecture
the intended output


THEN

AI generates the detailed method


BUT NOT YET

execute
build
register
modify source assets
```

The action creates a revision-bound accepted construction state.

## 9. Design stage

Design converts the accepted construction into a concise complete method without exposing a specification wall.

Initial centre composition:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ AI-DESIGNED METHOD                                                   │
│                                                                      │
│ Evidence       Trends · Reddit · Wikipedia                           │
│ Grain          asset-week                                            │
│ Construction   align → normalise → combine → validate                │
│ Output         stablecoin_attention_weekly                           │
│                                                                      │
│ ✓ 6 routine decisions resolved                                      │
│ ! 1 methodological decision needs review                            │
│                                                                      │
│                                          [ REVIEW DECISION ]         │
└──────────────────────────────────────────────────────────────────────┘
```

The centre may expose `VIEW FULL METHOD`, but the default must remain concise.

### Ask during Design

Ask displays exactly one material decision:

```text
COMPONENT WEIGHTING

How should the three signals contribute?

● Equal weights — recommended
○ Reliability-adjusted
○ Custom

Why equal weighting?
Transparent, reproducible, and avoids pretending a reliability model
is already established.

[ ACCEPT RECOMMENDATION ]
```

### Authority labels

Every method choice should have one authority label:

```text
OBSERVED
Directly established from registered evidence.

SOURCE-DEFINED
Specified by source documentation or registered metadata.

AI RESOLVED
AI selected a low-risk routine operation.

RESEARCHER DECISION
A methodological choice requires explicit approval.

BLOCKED
Evidence or an executable operation is missing.

UNSUPPORTED
The AI can describe the idea, but the current runtime cannot execute it.
```

### Method categories

The semantic method may include:

- entity alignment;
- temporal alignment;
- point-in-time alignment;
- normalization;
- aggregation;
- filtering;
- component availability;
- weighting;
- event alignment;
- matched-sample construction;
- derived variables;
- validation;
- output contract;
- refresh policy.

## 10. Test stage

After all material decisions are accepted, the method compiles into executable operations and runs a bounded preview.

The preview must prove that the AI-generated plan is more than prose.

Default Test composition:

```text
┌───────────────────────────────────────────────────────────────────┐
│ PREVIEW RESULT                                                    │
│                                                                   │
│ READY TO BUILD — WITH ONE DOCUMENTED WARNING                      │
│                                                                   │
│ 3,120 preview rows                                                │
│ 29 / 30 entities matched                                          │
│ 94.8% complete three-component observations                       │
│ output key unique                                                 │
│ all fields traceable                                              │
└───────────────────────────────────────────────────────────────────┘

SAMPLE

asset     week       attention    components
USDT      2025-W01      0.28          3
USDC      2025-W01      0.20          3
DAI       2025-W01      0.26          3

5 diagnostic checks passed · 1 warning      View diagnostics ▸

[ RETURN TO DESIGN ]                         [ ACCEPT & BUILD ]
```

### Ask during Test

Ask interprets the most material diagnostic:

```text
COMPONENT IMBALANCE

Warning: Reddit dominates the index for 6 of 29 assets.

AI recommendation:
Keep equal weighting for v1, expose component contributions,
and record the limitation.

● Accept and document
○ Modify construction
○ Exclude affected assets
```

The researcher should never be required to interpret a dashboard of raw diagnostic cards before receiving the AI's judgment.

### Preview diagnostics

The preview engine should support:

- sample rows;
- target schema;
- key uniqueness;
- entity matching;
- time coverage;
- join loss;
- missingness;
- component availability;
- source contribution;
- outlier behavior;
- event overlap;
- point-in-time leakage checks;
- field-level lineage;
- estimated output size;
- custom validation rules.

## 11. Build stage

The Build stage shows research-relevant progress, not infrastructure telemetry.

```text
PREPARE INPUTS             COMPLETE
ALIGN ENTITIES             COMPLETE
ALIGN TIME                 COMPLETE
CONSTRUCT COMPONENTS       COMPLETE
CREATE OUTPUT              COMPLETE
VERIFY OUTPUT              RUNNING
REGISTER IN LIBRARY        WAITING
```

Visible facts:

- source snapshots locked;
- current transformation phase;
- provisional row and field counts;
- represented entities;
- coverage;
- verification phase;
- write consequence.

Hidden by default:

- worker nodes;
- queues;
- CPU and memory;
- low-level logs;
- infrastructure telemetry.

Those belong to Resources or technical logs.

## 12. Registered stage

The primary success is the durable research asset.

Registered view must show:

- output identity;
- query readiness;
- row count;
- field count;
- entity count;
- coverage;
- verification summary;
- source lineage;
- manifest;
- saved construction;
- refresh state;
- open in Library;
- duplicate and modify;
- refresh output.

Only after registration should Synthesis present empirical-use guidance.

### Empirical-use guidance

Generated from actual output characteristics:

- grain;
- fields;
- variation;
- missingness;
- coverage;
- event density;
- lineage;
- verification results.

It may propose:

- descriptive analysis;
- panel fixed-effects models;
- event studies;
- difference-in-differences extensions;
- predictive analysis;
- heterogeneous effects;
- robustness requirements.

It must not claim:

- causal validity;
- parallel trends;
- instrument exogeneity;
- construct validity;
- publication readiness.

Use language such as `Possible empirical designs`, not `Valid empirical methods`.

## 13. Ask interaction contract

Ask must be proactive but restrained.

Speak proactively when:

- the request is materially ambiguous;
- results conflict with apparent intent;
- a stronger construction exists;
- a cross-page handoff is useful;
- a methodological assumption is being made;
- an irreversible or costly action is proposed;
- a preview exposes a material warning.

Remain quiet when:

- the user is merely navigating;
- the query is straightforward;
- the action is reversible and obvious;
- commentary would only narrate the interface.

Bad:

```text
“You selected three datasets.”
```

Good:

```text
“These three datasets can form a point-in-time panel,
but one uses fiscal-period dates while the others use publication dates.”
```

## 14. Conversational changes

Ask may propose changes, but durable state changes only through a visible centre diff.

Example:

```text
ASK

“I recommend treating GDELT as validation evidence
rather than a core attention component.”


CENTRE

PROPOSED CHANGE

GDELT
Core component → Validation source

Effect:
• index remains behaviour-led
• validation stage added
• no change to core weighting

[ REJECT ] [ APPLY ]
```

Conversational instruction example:

```text
“Actually, make this monthly and exclude news from the final index.”
```

Expected response:

```text
I will change the target grain from asset-week to asset-month
and retain GDELT only as validation.

This affects temporal aggregation, expected row count,
and the output contract.

[ REJECT ] [ APPLY CHANGE ]
```

## 15. Discover handoff

Synthesis may identify evidence that is missing, sourceable, or requires access.

The handoff to Discover must preserve:

- synthesis thread identity;
- research objective;
- evidence family;
- intended evidence role;
- target grain;
- target coverage;
- required fields;
- current held evidence;
- missing evidence identity;
- why the evidence matters.

Discover should return the acquired or newly registered asset to the active Synthesis thread.

Synthesis must never invent an acquisition result.

## 16. Library relationship

Library owns durable research assets and organisation.

Synthesis reads:

- dataset identity;
- fields and samples;
- grain;
- coverage;
- readiness;
- join keys;
- provenance;
- source versions;
- prior lineage;
- refresh state.

Synthesis writes:

- registered output asset;
- construction definition;
- lineage manifest;
- verification record;
- source snapshot references;
- refresh policy;
- empirical-use guide.

## 17. Required platform layers

The product definition is not limited by the present frontend or backend. Missing layers are implementation requirements.

### AI research-asset designer

Produces:

- interpreted objective;
- alternative research objects;
- recommended construct;
- evidence roles;
- target grain;
- candidate method;
- limitations;
- material decisions;
- output contract;
- validation contract.

### Durable semantic state

Stores:

- objective;
- interpretation;
- sources and evidence families;
- semantic relationships;
- accepted proposals;
- rejected proposals;
- method revisions;
- decisions;
- output specification;
- execution records.

### Synthesis compiler

Converts semantic research methods into deterministic execution plans.

The compiler returns:

- supported operations;
- unsupported operations;
- blocked operations;
- required researcher decisions;
- executable specification;
- output contract;
- verification contract;
- estimated resources.

### Operator runtime

Minimum target vocabulary:

```text
read registered input
select
filter
rename
cast
derive
aggregate
resample
join
entity map
deduplicate
point-in-time align
event align
window transform
normalize
rank
winsorize
restrict coverage
construct matched sample
custom code step
validate
register output
```

### Preview engine

Runs bounded execution and returns actual diagnostics.

### Verification engine

Runs standard and custom validation rules.

### Materialisation engine

Executes the accepted revision-bound specification, archives source and output manifests, and registers the output.

### Empirical analyst

Examines a registered output and proposes grounded empirical uses and identification gaps.

## 18. Suggested API contracts

Illustrative only; exact transport may change.

### Create thread

```http
POST /library/synthesis/threads
```

```json
{
  "objective": "Construct a weekly stablecoin attention measure",
  "selected_asset_ids": ["google_trends", "reddit", "wikipedia"],
  "project_id": "stablecoin-research"
}
```

### Interpret objective

```http
POST /library/synthesis/threads/{thread_id}/interpret
```

Returns:

```json
{
  "interpretation": {},
  "ambiguities": [],
  "blocking_question": null,
  "alternatives": [],
  "recommended_construction": {}
}
```

### Accept construction

```http
POST /library/synthesis/threads/{thread_id}/constructions/{construction_id}/accept
```

### Design method

```http
POST /library/synthesis/threads/{thread_id}/design
```

Returns the concise method, full method, resolved operations, and material decisions.

### Apply decision

```http
POST /library/synthesis/threads/{thread_id}/decisions/{decision_id}
```

### Compile

```http
POST /library/synthesis/threads/{thread_id}/compile
```

### Preview

```http
POST /library/synthesis/threads/{thread_id}/preview
```

### Execute

```http
POST /library/synthesis/threads/{thread_id}/execute
```

### Refresh

```http
POST /library/synthesis/threads/{thread_id}/refresh
```

### Empirical-use analysis

```http
POST /library/synthesis/threads/{thread_id}/empirical-use
```

## 19. Suggested semantic data shape

```ts
type SynthesisThread = {
  id: string;
  projectId?: string;
  title: string;
  objective: string;
  interpretation: SynthesisInterpretation;
  selectedAssetIds: string[];
  recommendedConstruction?: ConstructionProposal;
  alternativeConstructions: ConstructionProposal[];
  acceptedConstructionId?: string;
  method?: SynthesisMethod;
  decisions: MethodDecision[];
  compilation?: CompilationResult;
  previews: PreviewRecord[];
  execution?: ExecutionRecord;
  outputs: RegisteredOutput[];
  conversationId?: string;
  revision: number;
  createdAt: string;
  updatedAt: string;
};
```

```ts
type ConstructionProposal = {
  id: string;
  title: string;
  summary: string;
  targetObject: ResearchObject;
  evidenceRoles: EvidenceRole[];
  semanticSteps: SemanticStep[];
  outputContract: OutputContract;
  limitations: string[];
  unresolvedQuestions: string[];
  confidence: "high" | "medium" | "low";
};
```

```ts
type MethodDecision = {
  id: string;
  label: string;
  status: "open" | "recommended" | "accepted" | "rejected";
  authority: "observed" | "source_defined" | "ai_resolved" | "researcher_decision";
  recommendation?: unknown;
  alternatives: unknown[];
  consequence: string;
};
```

## 20. Frontend implementation principles

1. Do not build the opening state as a five-step wizard.
2. Do not use a manual React Flow or Alteryx-style canvas as the primary interaction.
3. A compact semantic diagram is allowed as a read-only explanation.
4. Avoid giant cards containing every lifecycle concern.
5. Keep one dominant centre object per stage.
6. Keep one primary action per stage.
7. Ask should open by default during intent entry and exploration.
8. Detail may become primary during evidence inspection, preview warnings, and registered output review.
9. Preserve the global right-rail grammar.
10. On mobile, preserve the centre summary and expose Ask as a deliberate sheet; do not collapse all state into chat.
11. Raw IDs must never be primary labels or actions.
12. Technical details must remain inspectable.

## 21. Honesty rules

Never claim:

- evidence is held when it is only proposed;
- a route is queryable when access is unknown;
- a plan is executable before compilation;
- a preview passed before actual preview execution;
- a build completed before execution evidence;
- an output is registered before registry confirmation;
- empirical identification is valid merely because fields exist.

Preferred state language:

```text
Draft interpretation
Recommendation ready
Method designing
Decision required
Compilation blocked
Preview running
Preview passed with warning
Build pending approval
Output produced
Registration pending
Registered
Refresh available
```

## 22. Required browser contracts

### Opening

- centre prompt becomes the first Ask message;
- Ask interpretation appears without duplicate user input;
- recommended construction appears in centre;
- nothing is called built or registered;
- alternatives are collapsed;
- primary action is `ACCEPT & DESIGN METHOD`.

### Interpretation correction

- changing longitudinal to event-response shows a visible consequence;
- accepting the change regenerates the centre recommendation;
- rejecting preserves the prior state.

### Method design

- routine operations are summarized as resolved;
- only one material decision is foregrounded;
- applying a decision persists across reload;
- full method is inspectable.

### Preview

- preview displays actual rows and diagnostics;
- the AI verdict is shown before raw diagnostics;
- warnings require explicit acceptance or method revision;
- no Library write occurs.

### Build

- request and approval are distinct when required;
- active state survives reload;
- failure displays a grounded error;
- retry is possible;
- registered state displays rows, manifest, verification, and output identity.

### Cross-page

- evidence gap opens Discover with the Synthesis brief;
- acquired evidence returns to the active thread;
- registered output opens in Library;
- Library selections can start a new Synthesis with context retained.

## 23. Implementation sequence

### Phase 1 — durable product state

- unify centre prompt and Ask conversation;
- implement objective interpretation;
- render S-04 recommendation;
- persist accepted construction;
- implement alternative comparison;
- implement visible proposal diffs.

### Phase 2 — method design

- semantic method model;
- material-decision model;
- concise method view;
- full method inspection;
- Ask decision rail.

### Phase 3 — compiler and preview

- compiler contract;
- supported operator registry;
- blocked/unsupported reporting;
- bounded preview;
- diagnostic interpretation;
- field lineage.

### Phase 4 — build and registration

- revision-bound execution;
- approval lifecycle;
- durable polling;
- verification;
- manifest creation;
- Library registration;
- failure and retry.

### Phase 5 — reuse and empirical enablement

- refresh;
- duplicate and modify;
- empirical-use guide;
- notebook and empirical-plan handoff.

## 24. Definition of done

Synthesis is product-complete when a researcher can:

1. state a research asset need in ordinary language;
2. see and correct the AI's interpretation;
3. review one evidence-grounded recommended construction;
4. compare alternatives without losing focus;
5. accept the construction without accidentally building data;
6. review a concise AI-designed method;
7. resolve only consequential methodological choices;
8. compile the method into an inspectable deterministic plan;
9. run a bounded preview with actual diagnostics;
10. receive an AI interpretation of the preview;
11. approve and execute the full build;
12. verify registration and lineage;
13. reopen, refresh, duplicate, and modify the construction;
14. open the result in Library;
15. receive grounded empirical-use guidance.

## 25. Frozen direction versus open refinement

Frozen direction:

- intent-first;
- Ask and centre prompt are one thread;
- one recommendation by default;
- centre stores durable state;
- compact semantic construction visual;
- no manual node graph;
- stage-specific interface;
- one material decision at a time;
- preview before build;
- verified Library registration;
- empirical guidance only after registration.

Still open to refinement:

- exact typography and spacing;
- exact semantic diagram geometry;
- alternative-comparison overlay composition;
- mobile Ask behavior;
- Design-state visual compression;
- diagnostic summarization language;
- exact compiler and operator schemas;
- exact empirical-use output format.

Do not reopen the product from zero unless real implementation or user evidence disproves this model.
