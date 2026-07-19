# Grok: start here — Synthesis S-04

Date: 2026-07-18  
Control board: GitHub issue #33  
Canonical spec PR: #32

## Your role

You are the backend/runtime owner for Synthesis S-04.

The frontend/product owner remains responsible for:

- the Synthesis interface;
- centre / Detail / Ask authority;
- visual hierarchy;
- responsive behavior;
- final integration and acceptance.

Do not redesign the frontend or reduce the target product to the current backend surface.

## Read these first

1. `docs/product/SYNTHESIS_S04_PRODUCT_SPEC.md`
2. `docs/status/generated/GROK_SYNTHESIS_BACKEND_MISSION.md`
3. `docs/status/generated/SYNTHESIS_IMPLEMENTATION_REVIEW_PROTOCOL.md`
4. `docs/product/ASK_INTEGRATION_APP_WIDE_CONTRACT.md`
5. GitHub issue #33

## First backend deliverable

Build and document the contract foundation before the compiler/runtime.

Required first slice:

```text
create durable Synthesis thread
→ link Ask conversation
→ return structured interpretation
→ generate one recommended construction + alternatives
→ accept construction with revision binding
→ generate method spec + material decisions
```

Recommended branch:

```text
feat/synthesis-thread-contracts
```

## First-slice endpoints

Implement or propose equivalent stable contracts for:

```http
POST /library/synthesis/threads
GET  /library/synthesis/threads/{thread_id}
POST /library/synthesis/threads/{thread_id}/recommend
POST /library/synthesis/threads/{thread_id}/recommendations/{id}/accept
POST /library/synthesis/threads/{thread_id}/design
POST /library/synthesis/threads/{thread_id}/proposals/{id}/accept
```

## First-slice required fixtures

Commit deterministic payloads for:

1. thread created from objective;
2. high-confidence interpretation;
3. material ambiguity;
4. recommended stablecoin attention construction;
5. two alternatives;
6. accepted construction;
7. method summary;
8. one material decision;
9. conversational proposal diff;
10. stale-revision rejection.

These fixtures must be frontend-consumable and use the planned live status vocabulary.

## Required first PR evidence

Your PR must include:

- exact endpoint list;
- request/response schemas;
- fixture paths;
- test command and result;
- revision behavior;
- stable error codes;
- known unsupported behavior;
- migration notes;
- link to issue #33.

## Second deliverable

Compiler and capability layer:

```text
semantic method
→ supported-operation check
→ deterministic execution plan
→ plan hash
→ revision/source binding
→ unsupported-operation explanation
```

## Third deliverable

Real bounded preview and structured verification:

```text
sample rows
schema
coverage
entity/join diagnostics
missingness
key integrity
lineage
warnings
verdict
```

Preview must not be a full registered build relabeled as preview.

## Fourth deliverable

Execution, approval, registration, failure/retry, and refresh.

## Do not do

- Do not replace S-04 with a profile browser.
- Do not expose a manual graph editor.
- Do not make the Ask thread separate from the Synthesis thread.
- Do not mutate durable state from chat without an accepted proposal.
- Do not hide unsupported operations.
- Do not skip preview.
- Do not register without manifest and revision proof.
- Do not declare the product complete from backend work alone.

## Coordination

Post every implementation PR and evidence bundle to issue #33.

For private backend work, provide an accessible PR or mirror, or attach:

- schema diff;
- fixture payloads;
- test evidence;
- commit references;
- capability matrix;
- known gaps.

The frontend/product owner will review the contracts and integrate the runtime. Final product acceptance occurs only after actual desktop/mobile renders and the end-to-end workflow pass review.
