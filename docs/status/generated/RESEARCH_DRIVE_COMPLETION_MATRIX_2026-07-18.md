# Research Drive completion matrix — 2026-07-18

Branch: `agent/synthesis-s04-spec`  
Base: `feat/discover-main-converge`

## Executive judgment

Research Drive is now close to **product-definition complete**, but it is not implementation-complete or validation-complete.

The major page family has been designed at full-screen scale:

- Home;
- Library;
- Discover;
- Synthesis;
- Resources;
- Profile;
- Preview;
- shared Detail / Ask rail.

That means the product no longer has a major undefined destination or missing primary workspace.

However, three material layers remain:

1. implement the canonical Synthesis S-04 lifecycle;
2. perform a horizontal Ask-integration polish across the other pages;
3. validate rendered pixels and end-to-end behavior after implementation.

The honest summary is:

```text
PRODUCT MAP                 essentially complete
PAGE PURPOSES               essentially complete
FULL-SCREEN DESIGN COVERAGE essentially complete
SYNTHESIS SPECIFICATION     strong canonical direction
ASK PRODUCT MODEL           corrected, not yet propagated everywhere
FRONTEND IMPLEMENTATION     incomplete
BACKEND CAPABILITY          incomplete for target Synthesis
VISUAL VALIDATION           incomplete for Synthesis
END-TO-END VALIDATION       incomplete
```

## Completion definitions

### Product-definition complete

The workspace has a stable purpose, governing question, object model, information hierarchy, interaction model, and relationship to other pages.

### Visual-design complete

Canonical desktop and responsive compositions have been rendered, reviewed, revised, and explicitly accepted.

### Implementation complete

The frontend and backend deliver the designed behavior with durable state and honest consequences.

### Validation complete

Rendered screenshots, browser contracts, backend tests, failure cases, persistence, and cross-page handoffs have been verified.

## Page matrix

| Surface | Product definition | Visual direction | Implementation | Validation | Current judgment |
|---|---|---|---|---|---|
| Home | Frozen | Iteration 10 frozen | Present | Previously reviewed | Complete enough; revisit only for Ask integration polish |
| Library | Frozen | Frozen | Present | Previously reviewed | Complete enough; needs horizontal Ask pass |
| Discover | Frozen core grammar | Frozen primary states | Present and extensive | CI/browser contracts exist | Strong; needs horizontal Ask pass and continued sourcing-mode buildout where missing |
| Synthesis | Canonical S-04 documented | S-04 opening is current best; later states specified | Current implementation does not match target | Not validated | Main remaining product build |
| Resources | Frozen Iteration 05 | Frozen | Present | Previously reviewed | Complete enough; needs horizontal Ask pass |
| Profile | Product/data model grounded | Polish candidate exists; not fully re-frozen | Present | Partial | Secondary polish candidate |
| Preview | Product behavior defined | Implemented composition | Implemented | CI green; no final manual screenshot audit | Functionally complete, visually not explicitly frozen |
| Detail / Ask rail | Global grammar frozen | Visually established | Present | Partial | Structural shell complete; intelligence integration requires cross-page pass |

## Frozen product roles

```text
HOME
Resume, orient, and intelligently route.

LIBRARY
Remember and organize the lab's owned research-data estate.

DISCOVER
Understand what evidence exists and how the lab can obtain it.

SYNTHESIS
Construct defensible research meaning and reusable derived assets.

RESOURCES
Explain available capability, usage, spend, and value.

PROFILE
Store transparent researcher context.

ASK
Reason around current intent, workspace, objects, and institutional context.
```

## Synthesis status

Synthesis was the final major undefined product surface.

The canonical direction is now documented in:

- `docs/product/SYNTHESIS_S04_PRODUCT_SPEC.md`;
- `docs/status/generated/GROK_HANDOFF_SYNTHESIS_S04.md`.

S-04 establishes:

- intent-first creation;
- centre prompt and Ask as one durable thread;
- AI interpretation before construction;
- one recommended construction by default;
- compact semantic evidence-to-output diagram;
- alternatives collapsed until compared;
- exact consequence for `ACCEPT & DESIGN METHOD`;
- one material decision at a time;
- compiler and preview requirements;
- verified build and Library registration;
- refresh, duplicate, and empirical-use behavior.

This resolves the product model. It does not mean the page is implemented or frozen in rendered pixels.

## Ask status

A major late-stage correction was identified:

> Ask had been visually present across the product, but too detached from the primary page interactions.

The corrected app-wide contract is now documented in:

- `docs/product/ASK_INTEGRATION_APP_WIDE_CONTRACT.md`.

The contract is:

```text
PAGE INPUT
search · prompt · selection · filters · current object
        │
        ▼
ASK AUTOMATICALLY UNDERSTANDS INTENT
        │
        ├── interprets
        ├── identifies ambiguity
        ├── recommends
        ├── explains
        └── proposes supported actions
        │
        ▼
CENTRE SHOWS STRUCTURED CONSEQUENCE
        │
        ▼
USER APPROVES MATERIAL CHANGES
```

Synthesis now embodies this relationship in its canonical spec.

The other pages still need a focused horizontal pass so that:

- Home prompts become Ask routing turns;
- Library selections automatically inform Ask;
- Discover search and Ask share one intent thread;
- Resources questions use live capacity context;
- Profile explains and proposes transparent context changes;
- Preview Ask inherits visible fields, rows, filters, grain, coverage, and provenance.

This should be a refinement pass, not a page-purpose redesign.

## What is complete now

### 1. Whole-product architecture

The application is no longer being treated as one linear workflow or a chat application with tabs.

The stable thesis is:

> workspace-specific excellence with shared intelligence

### 2. Primary page ownership

Each page has a distinct responsibility and durable consequence.

### 3. Shared shell

The `Navigation | Centre | Detail / Ask` grammar is established.

### 4. Main visual language

The pages have a coherent Research Drive visual family rather than unrelated feature screens.

### 5. Core object truth

Identity, readiness, provenance, grain, coverage, access state, ownership, and actions are shared across workspaces.

### 6. Honest state language

The product avoids claiming query readiness, execution, registration, or empirical validity without evidence.

### 7. Synthesis destination

The final major product surface now has a coherent end-to-end definition.

### 8. App-wide Ask integration contract

The relationship between page input, Ask interpretation, structured proposals, approval, durable consequences, and cross-page handoffs is now explicitly defined.

## What is not complete

### 1. Synthesis implementation

The current Synthesis frontend remains narrower than S-04. The required compiler, preview engine, verification engine, and generalized operator runtime are not proven complete.

### 2. Synthesis rendered review

The S-04 wireframe has not yet been implemented and evaluated through actual screenshots.

### 3. Design-stage proof

The opening is strong, but the real usability test is whether Design, Test, Build, and Registered remain equally restrained after implementation.

### 4. Cross-page Ask integration

The corrected Ask relationship has not yet been propagated and validated across every page.

### 5. Profile final polish

Profile is grounded, but not as explicitly frozen as Home, Library, Discover, and Resources.

### 6. Preview final visual freeze

Preview is functionally CI-green, but no final manual screenshot review was performed.

### 7. Complete responsive audit

Each final implemented state still needs desktop and mobile screenshot review.

## Recommended remaining sequence

### Phase A — build Synthesis S-04

1. objective + Ask unification;
2. interpretation and recommendation;
3. accepted construction state;
4. method design and material decisions;
5. compiler and bounded preview;
6. build, verification, and registration;
7. refresh and empirical-use guidance;
8. desktop/mobile visual review;
9. browser and backend tests.

### Phase B — horizontal Ask polish

Apply the corrected Ask contract to:

1. Discover;
2. Library;
3. Home;
4. Resources;
5. Preview;
6. Profile.

Do not reopen each page from zero. Preserve its frozen centre composition and integrate Ask into its primary inputs, selections, recommendations, and consequences.

### Phase C — final coherence audit

Review:

- blurred-screenshot hierarchy;
- repeated patterns;
- copy consistency;
- status vocabulary;
- action consequences;
- right-rail density;
- mobile behavior;
- loading, empty, blocked, failed, and stale states;
- cross-page identity preservation.

## Approximate completion assessment

These are directional product judgments, not measured engineering percentages.

```text
WHOLE PRODUCT DEFINITION       90–95%
PRIMARY PAGE VISUAL COVERAGE   90–95%
FROZEN VISUAL ACCEPTANCE       75–85%
CURRENT FRONTEND DELIVERY      65–75%
TARGET BACKEND DELIVERY        50–65%
END-TO-END PRODUCT VALIDATION  45–60%
```

The first two are high because the full application has now been reasoned through and rendered at page scale.

The later figures remain lower because Synthesis and the Ask integration correction create meaningful implementation work.

## Decision

It is reasonable to stop inventing new primary pages and stop reopening the whole architecture.

It is not reasonable to declare the product finished.

The correct statement is:

> Research Drive's product architecture and page family are essentially complete. The remaining work is to implement the final moat surface, propagate the corrected Ask interaction model, and validate the resulting product end to end.

## Exit criteria for the design phase

The design phase can be considered complete after:

1. Synthesis S-04 is implemented and visually reviewed;
2. Design/Test/Build/Registered states survive the same quality bar as Explore;
3. the horizontal Ask pass is completed;
4. Profile and Preview receive their final visual decisions;
5. one final whole-product coherence audit passes;
6. all canonical states are documented and linked from an implementation handoff.

Until then, the product is **architecturally complete but not delivery-complete**.
