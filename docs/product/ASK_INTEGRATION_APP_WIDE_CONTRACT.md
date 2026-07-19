# Research Drive — App-wide Ask integration contract

Date: 2026-07-18
Status: canonical interaction specification
Related: `SYNTHESIS_S04_PRODUCT_SPEC.md`

## Purpose

This document defines how Ask integrates with every Research Drive workspace.

The correction is fundamental:

> Ask is not a generic chat tab placed beside otherwise self-contained pages.

Ask is the intent-aware reasoning layer operating through each workspace. It must inherit live page context automatically, interpret the user's goal, explain ambiguity and recommendations, propose structured actions, and hand accepted consequences back to the centre canvas.

## Shared authority model

```text
DETAIL = understands the selected object
ASK    = understands the user's intent
CENTRE = stores accepted, durable consequence
```

Detail and Ask are not equivalent inspector tabs.

### Detail owns

- selected-object identity;
- readiness and access state;
- grain and coverage;
- provenance and ownership;
- source identity;
- current status;
- durable factual metadata;
- object-scoped actions.

### Ask owns

- interpretation of the user's current intent;
- clarification of material ambiguity;
- explanation of recommendations;
- comparison of plausible routes;
- warnings about methodological or operational consequences;
- natural-language modification requests;
- structured action proposals;
- cross-workspace handoffs;
- contextual reasoning over the active object and workspace.

### Centre owns

- results and ranked candidates;
- accepted plans;
- accepted state changes;
- selected evidence architecture;
- preview and verification results;
- durable output identity;
- explicit diffs before consequential changes;
- current project or workflow state.

## The app-wide intelligence loop

```text
PAGE INPUT / SELECTION
search · prompt · filters · selected assets · current object
        ↓
ASK INTERPRETS THE INTENT
        ↓
ASK EXPLAINS / RECOMMENDS / FLAGS AMBIGUITY
        ↓
CENTRE SHOWS A STRUCTURED PROPOSAL OR RESULT
        ↓
USER APPROVES MATERIAL CHANGES
        ↓
DURABLE PAGE STATE CHANGES
```

The user must never need to restate in Ask what they just searched, selected, filtered, or opened in the centre.

## One thread, multiple renderings

A workspace may contain a large search or prompt surface in the centre and an Ask conversation in the right rail. These are not separate input systems.

```text
CENTRE SEARCH / PROMPT
        ↓
FIRST USER TURN IN ASK
        ↓
AI INTERPRETATION
        ↓
STRUCTURED PAGE RESULT
```

The same durable thread contains:

- original user prompt;
- active workspace;
- selected object identities;
- current filters and search state;
- AI interpretation;
- accepted and rejected proposals;
- cross-page handoff context;
- resulting durable state changes.

The centre renders structured, consequential state. Ask renders interpretation, explanation, conversation, and proposed changes.

## Ask context envelope

Every page should provide Ask with a normalized context envelope.

```ts
interface AskWorkspaceContext {
  workspace: "home" | "library" | "discover" | "synthesis" | "resources" | "preview" | "profile";
  project?: {
    id?: string;
    title?: string;
    objective?: string;
  };
  query?: {
    raw?: string;
    interpreted?: string;
    filters?: Record<string, unknown>;
  };
  selected?: Array<{
    kind: string;
    id: string;
    title?: string;
    source_id?: string;
    connector_id?: string;
    dataset_id?: string;
    candidate_key?: string;
  }>;
  object?: {
    kind?: string;
    id?: string;
    title?: string;
    grain?: string;
    coverage?: string;
    readiness?: string;
    access_state?: string;
    provenance?: unknown;
  };
  view?: {
    tab?: string;
    mode?: string;
    visible_fields?: string[];
    filters?: Record<string, unknown>;
    selected_rows?: unknown[];
  };
  capabilities?: {
    available_actions?: string[];
    resource_constraints?: unknown;
  };
  thread?: {
    thread_id?: string;
    session_id?: string;
    conversation_id?: string;
  };
}
```

Exact backend naming may differ, but the functional context must be preserved.

## Structured proposal contract

Ask may explain freely in prose, but a durable product change must be represented as a structured proposal.

```ts
interface AskStructuredProposal {
  id: string;
  workspace: AskWorkspaceContext["workspace"];
  title: string;
  summary: string;
  reason: string;
  consequence: string[];
  reversible: boolean;
  operations: Array<Record<string, unknown>>;
  target_state_hash?: string;
}
```

The centre renders the exact consequence and requires approval when the change is material.

```text
USER TALKS TO ASK
        ↓
ASK EXPLAINS A PROPOSED CHANGE
        ↓
CENTRE SHOWS THE EXACT DIFF
        ↓
USER APPROVES
        ↓
DURABLE STATE CHANGES
```

Routine, low-risk and reversible UI preferences may apply directly. Methodological, sourcing, write, registration, scheduling, destructive, access, profile, or high-cost changes require explicit approval.

## Proactive behavior threshold

Ask should intervene proactively when:

- the query is materially ambiguous;
- two interpretations would produce different research objects;
- selected evidence conflicts with the apparent goal;
- a stronger source or route exists;
- a methodological assumption is consequential;
- the current workspace is not the correct owner of the next step;
- an irreversible, costly, destructive, or write action is proposed;
- a result appears technically available but scientifically inappropriate;
- the system is about to make an assumption that should remain visible.

Ask should remain quiet when:

- the user is simply navigating;
- the action is obvious and reversible;
- commentary would merely narrate visible UI;
- no meaningful recommendation or warning exists;
- the user has already resolved the relevant decision.

Bad proactive output:

```text
You selected three datasets.
```

Good proactive output:

```text
These three assets use different time authorities:
fiscal period, publication date, and market date.
```

## Rail priority by state

The right rail remains `Detail | Ask`, but the default tab may change based on workflow state.

### Ask opens by default when

- a user enters a new intent or search prompt;
- the AI is interpreting an ambiguous request;
- a new Synthesis thread is unformed;
- a structured proposal awaits review;
- a cross-page handoff has just arrived;
- diagnostics require interpretation;
- a natural-language modification is being processed.

### Detail opens by default when

- the user selects a concrete dataset, candidate, source, evidence node, warning, usage item, or registered output;
- the user is inspecting factual object truth;
- the workflow is stable and no interpretation is currently required.

## Home integration

### Role

Home resumes, orients, and routes. It must not become a chat homepage.

### Ask behavior

A Home prompt becomes the first turn of Ask. Ask interprets which workspace owns the task:

- Library search;
- Discover evidence search;
- Synthesis construction;
- existing-project continuation;
- Resources feasibility;
- Preview inspection;
- Profile-context clarification.

### Example

User:

```text
I need evidence for an Ethereum adoption paper.
```

Ask:

```text
This appears to require external historical evidence rather than
only assets already held in Library.

I recommend starting in Discover with an evidence brief covering:
transaction history, address activity, network usage, and market controls.
```

Centre proposal:

```text
RECOMMENDED START
Discover evidence universe

[ OPEN DISCOVER WITH THIS BRIEF ]
```

### Durable consequence

The handoff carries the interpreted evidence need and project context into Discover. Discover does not open empty.

## Library integration

### Ask context

Ask automatically receives:

- active folder or collection;
- current search;
- selected assets;
- selected dataset;
- visible filters;
- ownership and readiness;
- grain and coverage;
- provenance and source identity;
- current preview or selection state.

### Example

User selects:

- MOPS fundamentals;
- TWSE returns;
- analyst revisions.

Ask:

```text
These assets can support a point-in-time panel.

The main methodological risk is that fundamentals may use fiscal-period
dates while revisions use publication dates.
```

Centre suggestion:

```text
3 ASSETS SELECTED

AI SUGGESTION
Create point-in-time research panel

[ COMPARE COVERAGE ] [ START SYNTHESIS ]
```

### Key rule

The user never needs to retype selected asset names into Ask.

### Supported structured actions

- compare coverage and grain;
- inspect time authority;
- explain provenance;
- identify compatibility risks;
- start Synthesis with selected assets;
- open Preview for a selected asset;
- propose a collection or folder action;
- recommend Discover when evidence is missing.

## Discover integration

### Role

Discover asks:

> What evidence exists, and how can the lab obtain it?

Ask must deeply participate in both search/browse and sourcing/acquisition engineering.

### Search prompt behavior

The Discover search box is also the first turn of the Discover Ask thread.

Ask should:

- interpret the evidence need;
- distinguish data shape from topic keywords;
- expand terminology and synonyms;
- identify ambiguity;
- search local and external evidence universes;
- explain ranking;
- compare local coverage with external candidates;
- compare sourcing routes;
- surface access, license, cost, quota, grain, and history constraints;
- turn an accepted candidate into a sourcing plan.

### Example

Query:

```text
Historical Ethereum transactions from 2016
```

Ask interpretation:

```text
You need transaction-level history suitable for constructing an
address-level panel, not aggregate market statistics.

I searched BigQuery public blockchain data, Etherscan historical access,
archival dumps, and existing lab holdings.
```

Centre recommendation:

```text
RECOMMENDED ROUTE
BigQuery = historical transaction spine
Etherscan = targeted address and contract enrichment

[ REVIEW RECOMMENDED ROUTE ]
```

### Supported structured actions

- update interpreted requirements;
- broaden or narrow search;
- compare routes;
- select candidate;
- create sourcing specification;
- probe candidate;
- request collection;
- schedule refresh where execution is genuinely supported;
- return acquired evidence to an active Synthesis thread.

### Honesty requirement

Ask must not invent collection, acquisition, access, schedule execution, or registration success. The centre only shows confirmed durable state.

## Synthesis integration

### Role

Synthesis asks:

> The research asset or measure I need does not cleanly exist. What is the strongest defensible thing the lab can construct?

### Prompt behavior

The large Synthesis prompt is the first message of the durable Synthesis Ask thread.

Ask handles:

- construct interpretation;
- material ambiguity;
- alternative construction comparison;
- evidence-role reasoning;
- method explanation;
- natural-language modifications;
- diagnostic interpretation;
- empirical-use reasoning after registration.

Centre handles:

- research brief;
- selected construction;
- evidence architecture;
- accepted method;
- current material decision;
- preview and verification results;
- build state;
- registered output.

### Canonical flow

```text
USER INTENT
        ↓
ASK INTERPRETS THE RESEARCH OBJECT
        ↓
ASK COMPARES CONSTRUCTION OPTIONS
        ↓
CENTRE SHOWS ONE RECOMMENDED CONSTRUCTION
        ↓
USER ACCEPTS OR CORRECTS
        ↓
ASK PROPOSES METHOD CHANGES
        ↓
CENTRE STORES ACCEPTED METHOD
```

### Natural-language modification example

User:

```text
Make the panel monthly and remove news from the index.
```

Ask:

```text
This changes the target grain from asset-week to asset-month and moves
GDELT to validation-only.

Expected effects:
- fewer output rows;
- monthly aggregation added;
- core weighting changes.
```

Centre diff:

```text
PROPOSED CHANGE

Grain
asset-week → asset-month

GDELT
core component → validation

[ REJECT ] [ APPLY ]
```

## Resources integration

### Role

Resources describes capability, access, capacity, usage, spend, and value. It does not become an operations console.

### Ask context

Ask may reason over:

- available APIs and licenses;
- current storage;
- credits and quotas;
- compute capacity;
- current usage;
- source access;
- related projects;
- existing assets and pipelines;
- demonstrated output value.

### Example

User:

```text
Can we build the complete Ethereum transaction catalogue this month?
```

Ask:

```text
Possible, but not through Etherscan alone.

Recommended route:
BigQuery extraction → filtered partitions → Drive archive.

Current storage appears to be the binding constraint.
```

Centre assessment:

```text
FEASIBLE WITH CONSTRAINTS

Access       available
Compute      sufficient
Storage      shortfall
Best route   BigQuery → archive

[ OPEN SOURCING IN DISCOVER ]
```

### Key rule

Resources explains feasibility and constraints. Discover owns sourcing design and execution. Synthesis owns construction of derived research assets.

## Preview integration

### Ask context

Ask automatically receives:

- dataset identity;
- visible columns;
- selected rows;
- current filters;
- active sample or chart;
- grain and coverage;
- provenance;
- missingness;
- current row-level or field-level focus.

### Example

User:

```text
Can this support a DiD?
```

Ask:

```text
The panel has entity and time dimensions, but this preview does not
establish a treatment date or untreated comparison group.

A DiD may be possible after defining those elements.
```

Centre action:

```text
[ START EMPIRICAL SYNTHESIS ]
```

### Supported structured actions

- explain fields and rows;
- compare selected records;
- assess likely empirical use;
- explain missingness or anomalies;
- inspect provenance;
- create a Synthesis brief from the visible dataset;
- propose filters or derived fields;
- create notebook or analysis handoff when supported.

## Profile integration

### Role

Profile stores transparent researcher context. It must never become hidden personalization machinery.

### Ask behavior

Ask explains how context influences:

- Discover ranking;
- source explanations;
- recommendations;
- current-project context;
- default terminology;
- Synthesis relevance.

Ask may propose profile changes, but the centre must show the exact update and its effect before persistence.

### Example

Ask:

```text
This research interest increases the ranking of crypto-market and
blockchain evidence in Discover. It does not hide unrelated evidence.
```

Centre proposal:

```text
PROPOSED PROFILE UPDATE

Add:
Crypto market structure

Effect:
- influences Discover ranking;
- informs Ask context;
- does not restrict search results.

[ REJECT ] [ APPLY ]
```

## Cross-workspace handoffs

Ask must identify when another workspace owns the next step.

### Library → Synthesis

```text
These selected assets suggest a new point-in-time panel.
[ REVIEW IN SYNTHESIS ]
```

Carries selected dataset identities, roles, current project, and detected methodological risk.

### Synthesis → Discover

```text
One required evidence family is missing.
[ OPEN SOURCING BRIEF IN DISCOVER ]
```

Carries objective, required grain, evidence role, held evidence, missing evidence, and construction thread identity.

### Discover → Synthesis

```text
The source has been acquired and registered.
[ RETURN TO ACTIVE SYNTHESIS ]
```

Carries registered dataset identity and resolves the relevant evidence gap.

### Resources → Discover

```text
The project is feasible through BigQuery, not Etherscan-only collection.
[ OPEN RECOMMENDED SOURCING ROUTE ]
```

Carries capability constraints and preferred source route.

### Preview → Synthesis

```text
This dataset may support an event-response construction.
[ START SYNTHESIS FROM THIS ASSET ]
```

Carries dataset identity, visible schema, current filters, and selected empirical intent.

### Home → any workspace

Carries the interpreted intent and does not open a blank destination.

## Handoff payload

```ts
interface WorkspaceHandoff {
  id: string;
  from_workspace: AskWorkspaceContext["workspace"];
  to_workspace: AskWorkspaceContext["workspace"];
  objective: string;
  reason: string;
  project_id?: string;
  thread_id?: string;
  selected_objects?: AskWorkspaceContext["selected"];
  requirements?: Record<string, unknown>;
  assumptions?: string[];
  unresolved_questions?: string[];
  source_state_hash?: string;
}
```

The destination page must render a visible handoff brief and allow the user to dismiss or modify it.

## Loading, streaming, and background reasoning

Ask may stream prose and progress activity, but progress must remain useful and restrained.

Good activity:

- Inspecting held evidence metadata;
- Comparing historical coverage;
- Evaluating source access routes;
- Checking output-grain compatibility;
- Preparing a construction proposal.

Bad activity:

- Thinking;
- Working;
- Calling tool 4;
- Token or model telemetry;
- infrastructure logs irrelevant to the research task.

If Composer continues asynchronously on the backend, the thread should preserve a visible pending state and update the structured centre only when a proposal or durable result is available.

## Failure behavior

Ask failures must not erase page state.

The interface should distinguish:

- Ask temporarily unavailable;
- interpretation failed;
- source query failed;
- structured proposal failed validation;
- proposed operation unsupported;
- durable state write failed;
- action queued but not executed;
- execution failed after approval.

The centre must retain last confirmed durable state and clearly mark uncommitted conversational suggestions.

## Permission and approval rules

Explicit approval is required for:

- creating or modifying a Synthesis method;
- accepting a material methodological assumption;
- requesting or approving collection;
- scheduling refresh;
- registering or overwriting an output;
- profile changes;
- destructive Library operations;
- access or license actions;
- high-cost queries or builds;
- cross-workspace actions with a durable write consequence.

Ask may answer, compare, inspect, search, and prepare proposals without separate approval.

## Frontend implementation guidance

### Shared rail hook

Create or extend one shared Ask hook rather than page-specific chat implementations.

The hook should support:

- workspace context updates;
- durable thread/session restoration;
- prompt submission from centre or rail;
- streamed answer and progress;
- structured proposal artifacts;
- handoff artifacts;
- job or execution status artifacts;
- proposal review callbacks;
- linked page-state refresh.

### Centre prompt bridge

Every page-level prompt should call the same Ask send path used by the rail.

```ts
sendAskMessage(prompt, {
  source: "centre_prompt",
  displayText: prompt,
  workspaceContext,
});
```

Do not maintain a second independent history.

### Proposal rendering

Each workspace may render its own proposal shape, but proposals must share:

- title;
- rationale;
- consequence;
- affected objects;
- proposed operations;
- approval controls;
- durable-status feedback.

### Context updates

Selecting an object, changing filters, changing tabs, or navigating between related pages must update Ask context without silently starting a new unrelated conversation.

A new thread should begin only when the user starts a distinct project, evidence search, or synthesis objective.

## Backend / agent requirements

The agent layer must receive normalized context and be able to return:

- prose answer;
- interpreted intent;
- suggested prompts;
- structured proposal;
- cross-workspace handoff;
- job/action artifact;
- pending/background status;
- source citations or evidence identities where available.

The backend must validate proposal operations against workspace-specific schemas before the frontend may apply them.

No AI-generated operation should directly mutate durable state without authorization checks and the appropriate approval rule.

## Browser acceptance contracts

### Shared

- Centre prompt appears as the first user message in Ask.
- Ask automatically receives selected object identity.
- Reload restores the linked thread and transcript.
- Ask proposal appears as a structured centre review.
- Reject leaves durable state unchanged.
- Apply persists and survives reload.
- Failed persistence leaves last confirmed state visible.
- Cross-page handoff opens the destination with a visible brief.

### Home

- Prompt recommends an owning workspace.
- Opening the recommendation carries the interpreted brief.

### Library

- Multi-selection is visible in Ask context without restatement.
- Ask can propose Synthesis from selected assets.

### Discover

- Search prompt and Ask share one history.
- Ask interpretation appears before or alongside results.
- Candidate ranking explanation uses actual result context.
- Sourcing handoff preserves evidence requirements.

### Synthesis

- Initial prompt becomes durable Synthesis thread.
- Ask interpretation can be corrected.
- Accepted recommendation updates the centre.
- Natural-language change becomes a structured diff.

### Resources

- Ask feasibility answer uses current resource context.
- Action opens Discover rather than pretending Resources executes sourcing.

### Preview

- Ask understands current dataset, fields, filters, and selected rows.
- Empirical-use handoff opens Synthesis with context.

### Profile

- Proposed context change displays its effect and requires approval.

## Definition of done

The app-wide Ask integration is complete when:

1. Every major centre prompt routes through the same Ask thread.
2. Every page provides normalized live context to Ask.
3. Users never need to restate selected objects or current queries.
4. Ask interpretation is visible when ambiguity is material.
5. Ask can produce structured, workspace-specific proposals.
6. Material changes require visible centre review and approval.
7. Accepted changes persist and survive reload.
8. Cross-page handoffs carry context and never open blank.
9. Detail remains factual while Ask remains intent-oriented.
10. Ask is proactive only when it adds meaningful research or operational value.
11. The browser contracts above pass against real API behavior, not only static mocks.
12. No page falsely claims execution, registration, schedule, collection, or state mutation based only on chat prose.

## Final product principle

> Ask is attached to intent and live context, not merely placed beside the page.

The user expresses a goal through the workspace. Ask interprets and reasons over that goal. The centre makes the accepted result durable. Detail preserves object truth. Together they form one coherent AI-assisted product rather than a collection of pages with an optional chatbot.
