# Synthesis S-04 implementation review protocol

Branch: `agent/synthesis-s04-spec`  
Base: `feat/discover-main-converge`  
Date: 2026-07-18

## Purpose

This protocol defines how Synthesis S-04 implementation work is reviewed, monitored, and accepted.

The goal is to preserve product quality while allowing frontend and backend work to proceed in parallel. GitHub is the control plane for code, contract evidence, render evidence, review findings, and completion state.

The frontend owner remains the final product reviewer for Synthesis and the app-wide Ask integration model.

---

## Sources of truth

Review order:

1. `docs/product/SYNTHESIS_S04_PRODUCT_SPEC.md`
2. `docs/product/ASK_INTEGRATION_APP_WIDE_CONTRACT.md`
3. `docs/status/generated/GROK_HANDOFF_SYNTHESIS_S04.md`
4. `docs/status/generated/GROK_SYNTHESIS_BACKEND_MISSION.md`
5. this review protocol
6. implementation PRs and fixtures

Current implementation behavior is evidence, not a product limitation. Where current code conflicts with the canonical specification, the specification wins unless the product decision is explicitly reopened.

---

## Review authority

### Frontend owner

Responsible for:

- final page hierarchy;
- component and state architecture review;
- Ask / centre authority boundaries;
- action consequences;
- responsive quality;
- copy and status vocabulary;
- visual acceptance;
- browser contract acceptance;
- integration acceptance;
- identifying product regressions even when tests pass.

### Backend owner / Grok

Responsible for:

- backend implementation correctness;
- schema and lifecycle stability;
- deterministic fixtures;
- compiler and runtime behavior;
- preview and verification truth;
- durable state;
- tests and migration evidence;
- explicit unsupported states.

### Merge authority

No slice should be called complete until:

- code is reviewable;
- relevant tests pass;
- required renders exist;
- contract fixtures exist;
- known limitations are documented;
- product review findings are resolved or explicitly accepted.

---

## Required PR structure

Each implementation PR must include:

```markdown
## S-04 lifecycle slice

Explore / Design / Test / Build / Registered / Ask integration

## Product consequence

What durable user-visible behavior now exists?

## Contracts

Endpoints, schemas, fixtures, status vocabulary, and error codes.

## Screens / states

Which canonical states are implemented?

## Evidence

Tests, screenshots, recordings, artifacts, and fixture paths.

## Known gaps

Unsupported operations, temporary mocks, degraded states, or follow-up work.

## Review focus

The exact areas requiring product review.
```

Large PRs that mix unrelated surfaces should be split before detailed review.

---

## Frontend PR render requirements

Every Synthesis frontend PR must provide render evidence from the actual implementation, not only CLI wireframes.

### Required desktop screenshots

Target viewport: approximately `1440 × 900` or the project's canonical desktop size.

Required states:

1. new Synthesis / intent entry;
2. interpretation ready;
3. recommendation ready — canonical S-04 Explore;
4. alternatives comparison open;
5. construction accepted;
6. Design summary;
7. one material decision open in Ask;
8. proposed-change diff;
9. method ready;
10. compile blocked / unsupported operation;
11. Test preview ready;
12. Test preview with one warning;
13. Test preview failure;
14. execution approval required;
15. queued or running;
16. verification running;
17. registered output;
18. execution failure and retry;
19. stale source / refresh assessment;
20. empty, loading, blocked, and generic error states where relevant.

### Required mobile screenshots

Target viewport: approximately `390 × 844` or the project's canonical mobile size.

At minimum:

1. intent entry;
2. recommendation ready;
3. Design decision;
4. Test warning;
5. Build running;
6. Registered output;
7. Ask open;
8. Detail open;
9. failed state.

### Screenshot quality rules

Screenshots must:

- show the full browser viewport;
- use realistic content and fixture lengths;
- include the right rail where relevant;
- show scroll position intentionally;
- avoid hidden overflow;
- avoid dev overlays;
- identify branch and commit in the artifact name or PR description;
- be regenerated after material UI changes.

### Optional but preferred

- short interaction recording for the full vertical slice;
- Playwright trace;
- visual regression snapshots;
- before/after comparison for major refinements.

---

## Render review rubric

Each canonical state is reviewed against the following questions.

### 1. Immediate comprehension

Within five seconds, can the user tell:

- what object they are working on;
- what stage/state they are in;
- what the AI recommends;
- whether anything has changed;
- what action advances the work?

### 2. Hierarchy

- Is there one dominant centre object?
- Is the primary action obvious?
- Are alternatives and technical detail subordinate?
- Does Ask complement rather than repeat the centre?
- Does Detail explain selected object truth?

### 3. AI assistance

- Has AI reduced user work?
- Is the interpretation visible?
- Are routine decisions handled automatically?
- Are only material decisions surfaced?
- Can the user correct the AI without restarting?

### 4. Authority and honesty

- Is every mutation previewed before application?
- Are write effects explicit?
- Are preview and full build clearly different?
- Are warnings visible?
- Are registration claims backed by proof?
- Are unsupported operations honest?

### 5. Density

- Does the page remain calm at rest?
- Are method details available without becoming default clutter?
- Does the right rail avoid becoming a second full page?
- Does mobile preserve comprehension rather than merely stack everything?

### 6. Lifecycle coherence

- Does each state naturally lead to the next?
- Are stage labels used only after a real construction exists?
- Does reloading preserve the same durable state?
- Does failure recovery return the user to a sensible point?

---

## Code review checklist — frontend

### State model

- [ ] one durable thread identity;
- [ ] explicit lifecycle state;
- [ ] selected recommendation identity;
- [ ] accepted construction revision;
- [ ] material decisions stored separately from routine decisions;
- [ ] plan and preview hash/revision retained;
- [ ] execution and registration proof retained;
- [ ] no duplicated centre and Ask histories.

### Ask integration

- [ ] centre prompt becomes first Ask turn;
- [ ] Ask receives current thread/object context automatically;
- [ ] Ask proposals do not silently mutate state;
- [ ] exact diff rendered before apply;
- [ ] stale proposal conflict handled;
- [ ] Ask quick questions are contextual, not decorative;
- [ ] conversation survives reload;
- [ ] Ask can initiate cross-page handoffs with context.

### S-04 visual grammar

- [ ] one recommended construction by default;
- [ ] semantic construction visual, not manual graph editor;
- [ ] alternatives collapsed until requested;
- [ ] no stage bar before acceptance;
- [ ] exact `ACCEPT & DESIGN METHOD` consequence;
- [ ] one material decision emphasized at a time;
- [ ] Test shows AI verdict before raw diagnostics;
- [ ] Build emphasizes durable consequence over worker telemetry;
- [ ] Registered emphasizes asset, proof, refresh, and reuse.

### Accessibility

- [ ] native controls where possible;
- [ ] keyboard navigation;
- [ ] visible focus;
- [ ] accessible labels;
- [ ] status changes announced;
- [ ] diagrams have text alternatives;
- [ ] no meaning encoded by color alone.

### Responsive behavior

- [ ] no horizontal overflow in standard states;
- [ ] rail behavior is intentional on narrow screens;
- [ ] primary action remains reachable;
- [ ] long evidence names wrap correctly;
- [ ] tables simplify or scroll locally;
- [ ] semantic diagram remains legible;
- [ ] modals and overlays fit mobile viewport.

---

## Code review checklist — backend and contracts

- [ ] structured interpretation response;
- [ ] recommendation plus alternatives;
- [ ] durable thread revision;
- [ ] explicit proposal operations;
- [ ] stale revision conflict;
- [ ] complete method spec;
- [ ] material decisions represented explicitly;
- [ ] compiler reports supported and unsupported operations;
- [ ] plan hash and revision binding;
- [ ] real bounded preview;
- [ ] diagnostics and verification results are structured;
- [ ] approval before write effect;
- [ ] durable job status;
- [ ] manifest and registration proof;
- [ ] source revision lock;
- [ ] failure and retry;
- [ ] refresh assessment;
- [ ] deterministic frontend fixtures.

---

## Browser contract requirements

The Synthesis vertical slice must have automated browser coverage.

Minimum tests:

```text
creates thread from centre intent
shows Ask interpretation
shows one recommendation
compares alternatives without replacing default state
accepts construction
shows Design state after acceptance
resolves one material decision
applies conversational proposal only after confirmation
rejects stale proposal
compiles method
shows unsupported operation honestly
runs bounded preview
shows ready verdict
shows warning verdict
opens detailed diagnostics
submits execution
requires approval
polls queued/running state
persists after reload
shows registered proof
opens Library asset
shows failed execution
retries successfully
assesses refresh after source revision change
```

Cross-page tests:

```text
Library selection → Synthesis with selected assets
Discover evidence gap → sourcing handoff
Discover registration → return to active Synthesis
Registered output → Library asset
Preview asset → empirical Synthesis
Resources feasibility → Discover brief
```

Tests must assert durable consequences, not only visible text.

---

## Backend fixture requirements

Frontend integration must not wait for a live runtime to begin.

Backend owner must provide stable fixtures for:

- interpretation;
- recommendation;
- alternatives;
- accepted construction;
- method summary;
- material decision;
- proposal diff;
- compile success;
- compile unsupported;
- preview success;
- preview warning;
- preview failure;
- pending approval;
- running;
- verifying;
- registered;
- failed;
- retry success;
- stale refresh.

Fixture identifiers and status vocabulary must match the live contract.

---

## Severity model for review findings

### P0 — product integrity blocker

Examples:

- silent mutation;
- fake preview;
- false registration claim;
- data loss;
- security boundary failure;
- inaccessible core workflow;
- wrong output identity.

Must be fixed before merge.

### P1 — major experience or correctness defect

Examples:

- Ask detached from centre state;
- user cannot understand primary action;
- lifecycle state lost after reload;
- warnings hidden;
- plan revision not enforced;
- mobile core flow unusable;
- incorrect diagnostics.

Must normally be fixed before merge.

### P2 — material polish defect

Examples:

- excess density;
- duplicated copy;
- weak hierarchy;
- inconsistent status vocabulary;
- secondary responsive defect;
- confusing but recoverable copy.

May merge only with explicit follow-up tracking.

### P3 — minor refinement

Examples:

- spacing;
- minor label refinement;
- non-blocking visual consistency;
- low-impact code cleanup.

May be deferred.

---

## Monitoring procedure

When an implementation PR is opened:

1. identify lifecycle slice and owner;
2. inspect changed files and contracts;
3. inspect CI status and failures;
4. inspect screenshots or downloadable render artifacts;
5. compare rendered states against canonical S-04;
6. inspect browser tests and fixtures;
7. leave actionable GitHub review findings;
8. classify findings P0–P3;
9. verify subsequent commits resolve findings;
10. update the implementation tracker;
11. only mark the slice accepted after code, render, and behavior agree.

The review record should live in GitHub comments and review threads so it remains available to any future builder.

---

## CI and artifact expectations

Preferred frontend CI outputs:

- unit tests;
- lint/type checks;
- Playwright tests;
- screenshots for canonical states;
- Playwright traces on failure;
- optional visual-diff report;
- build artifact.

Preferred backend CI outputs:

- contract tests;
- compiler tests;
- preview tests;
- verification tests;
- migration tests;
- fixture validation;
- integration smoke test.

A green CI run does not replace visual review.

---

## Private backend review limitation

The current connector directly exposes the public `Spectating101/yzu-cluster` repository. It does not currently expose the private `Sharpe-Renaissance/drive` repository.

Therefore one of the following is required for direct backend code monitoring:

1. grant the connected GitHub app access to the private repository; or
2. open an accessible mirror PR containing the relevant contract/runtime changes; or
3. publish patch, schema, fixture, and test artifacts into the public implementation tracker.

Until one of these is done, backend review is limited to the evidence Grok posts publicly. This limitation must not be mistaken for backend approval.

---

## Render acceptance

A page is not visually accepted from CLI alone.

A Synthesis state is accepted only after:

- actual implementation screenshot is reviewed;
- desktop hierarchy passes;
- mobile hierarchy passes;
- right rail behavior passes;
- no unsupported capability is visually claimed;
- action consequences match backend behavior;
- any P0/P1 findings are resolved.

The canonical S-04 wireframe is the implementation target, not proof of completion.

---

## Final integration audit

Before Synthesis is considered delivery-complete, review the full workflow in one continuous session:

```text
create intent
→ inspect interpretation
→ compare alternatives
→ accept construction
→ resolve method decision
→ compile
→ preview
→ inspect warning
→ approve execution
→ observe build
→ inspect registration proof
→ open Library asset
→ return to Synthesis
→ assess refresh
```

Audit:

- state continuity;
- object identity;
- no repeated prompts;
- copy consistency;
- status vocabulary;
- Ask context;
- error recovery;
- responsive behavior;
- performance;
- accessibility;
- actual durable consequences.

---

## Completion rule

No individual agent may declare Synthesis complete based solely on its own lane.

Backend complete means the runtime and contracts are ready.

Frontend complete means canonical states and interactions are implemented.

Product complete means both are integrated, rendered, tested, reviewed, and accepted against this protocol.
