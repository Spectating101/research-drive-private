# Grok mission — Synthesis S-04 backend and execution substrate

Branch: `agent/synthesis-s04-spec`  
Base: `feat/discover-main-converge`  
Date: 2026-07-18

## Mission

Build the backend and execution substrate required by the canonical Synthesis S-04 product specification without redefining the product model or simplifying the user experience to match current implementation limits.

The frontend owner remains responsible for the interaction model, information hierarchy, rendering, Ask integration, and final product review. Grok owns the backend lane described here and should work through explicit contracts, tests, and durable state.

The canonical product source of truth is:

- `docs/product/SYNTHESIS_S04_PRODUCT_SPEC.md`
- `docs/product/ASK_INTEGRATION_APP_WIDE_CONTRACT.md`
- `docs/status/generated/GROK_HANDOFF_SYNTHESIS_S04.md`
- `docs/status/generated/RESEARCH_DRIVE_COMPLETION_MATRIX_2026-07-18.md`

This document is the implementation mission and review contract for Grok.

---

## Product thesis that must remain intact

Synthesis is an intent-first AI research-asset construction workspace.

It must support this durable lifecycle:

```text
research intent
→ AI interpretation
→ recommended construction
→ accepted research brief
→ method design
→ material decisions
→ compiled execution plan
→ bounded preview
→ verification
→ approved execution
→ registration
→ reusable Library asset
→ refresh / duplicate / empirical use
```

The backend must not force the frontend to degrade into:

- a predefined profile browser;
- a two-dataset join screen;
- a manual node editor;
- a chat transcript with hidden consequences;
- an opaque one-shot generator;
- an operations console;
- a fake preview that is actually a full build;
- registration claims without durable proof.

If a target operation is not implemented yet, expose capability truth and an honest unsupported state. Do not silently remove the operation from the product model.

---

## Ownership boundary

### Grok owns

- interpretation and proposal service contracts;
- durable Synthesis thread state on the backend;
- plan compilation;
- supported-operation discovery;
- bounded preview execution;
- preview diagnostics;
- verification contracts;
- execution submission and approval lifecycle;
- job status and persistence;
- source locking and revision binding;
- output materialisation;
- manifest generation;
- Drive/archive proof;
- Library registration;
- retry and failure semantics;
- refresh semantics;
- backend fixtures and contract tests;
- API documentation needed by the frontend.

### Frontend owner owns

- page architecture;
- S-04 visual composition;
- centre / Detail / Ask authority boundaries;
- wording and action hierarchy;
- state presentation;
- responsive behavior;
- browser interaction contracts;
- screenshot review;
- final acceptance of integration behavior.

### Shared integration surface

- exact request and response schemas;
- lifecycle status vocabulary;
- error codes;
- proposal and state-patch grammar;
- capability reporting;
- revision/hash semantics;
- fixture payloads;
- mocked and live integration parity.

Grok should not make unilateral frontend product decisions in backend code, response copy, or API naming when those decisions alter the product model.

---

## Required domain model

A Synthesis thread must be durable and reconstructable.

Minimum thread state:

```json
{
  "thread_id": "syn_...",
  "project_key": "stablecoin-research",
  "title": "Historical stablecoin attention",
  "objective": "Build a defensible weekly measure...",
  "status": "exploring",
  "conversation_id": "conv_...",
  "research_brief": {},
  "evidence_state": {},
  "recommendation": {},
  "accepted_construction": {},
  "method_spec": {},
  "material_decisions": [],
  "compiled_plan": null,
  "preview": null,
  "execution": null,
  "registered_output": null,
  "revision": 1,
  "created_at": "...",
  "updated_at": "..."
}
```

The backend may use a richer internal model, but the frontend must be able to retrieve one coherent thread snapshot.

### Durable lifecycle states

Use one normalized vocabulary across endpoints:

```text
draft
interpreting
exploring
recommendation_ready
construction_accepted
designing
needs_decision
method_ready
compiling
compile_failed
preview_ready
preview_warning
preview_failed
ready_for_execution
pending_approval
approved
queued
running
verifying
registering
registered
failed
cancelled
stale
```

Status names may be adjusted only if a mapping table is supplied and no two states collapse materially different product consequences.

---

## Interpretation contract

The first centre prompt is the first user turn in the linked Ask conversation.

The interpretation service must return structured meaning, not only prose.

Suggested contract:

```http
POST /library/synthesis/threads
```

Request:

```json
{
  "objective": "Reconstruct a defensible weekly measure...",
  "project_key": "stablecoin-research",
  "selected_dataset_ids": ["google_trends", "reddit_activity"],
  "context": {
    "active_page": "synthesis",
    "profile_context_revision": "..."
  }
}
```

Response:

```json
{
  "thread": {},
  "interpretation": {
    "intended_object": "longitudinal_attention_measure",
    "target_grain": ["asset_id", "week"],
    "target_period": {"start": "2021-01-01", "end": null},
    "intended_uses": ["panel_analysis", "event_response"],
    "assumptions": [],
    "material_ambiguities": [],
    "confidence": "high",
    "can_continue_without_clarification": true
  }
}
```

If ambiguity is material, return exactly the ambiguity and available branches. Do not ask for information that is routine, reversible, or inferable.

---

## Recommendation contract

The AI should compare multiple possible research constructions internally and expose one recommended construction by default.

Suggested endpoint:

```http
POST /library/synthesis/threads/{thread_id}/recommend
```

Required output:

```json
{
  "recommendation_id": "rec_...",
  "title": "Composite weekly attention index",
  "construct": {
    "name": "historical_stablecoin_attention",
    "description": "...",
    "construct_boundary": "observable public attention proxy"
  },
  "evidence_roles": [
    {
      "dataset_id": "google_trends",
      "role": "core",
      "semantic_role": "search_intent",
      "grain": ["asset_id", "week"],
      "availability": "held"
    }
  ],
  "validation_evidence": [],
  "unavailable_ideal_evidence": [],
  "method_outline": [],
  "expected_output": {
    "dataset_id": "stablecoin_attention_weekly",
    "grain": ["asset_id", "week"],
    "coverage": {},
    "destination": "library"
  },
  "resolved_routine_decisions": [],
  "deferred_material_decisions": [],
  "main_limitation": "...",
  "why_recommended": [],
  "alternatives": []
}
```

Alternatives must remain queryable for comparison, but the default response should make the recommended option clear.

---

## Proposal and state-patch contract

Ask may propose changes conversationally, but durable state must change only through explicit accepted proposals.

Minimum proposal shape:

```json
{
  "proposal_id": "prop_...",
  "thread_id": "syn_...",
  "base_revision": 4,
  "summary": "Change grain to asset-month and keep GDELT validation-only",
  "operations": [
    {
      "op": "update_spec",
      "path": "/method_spec/target_grain",
      "before": ["asset_id", "week"],
      "after": ["asset_id", "month"]
    }
  ],
  "effects": [],
  "warnings": [],
  "status": "proposed"
}
```

Apply endpoint:

```http
POST /library/synthesis/threads/{thread_id}/proposals/{proposal_id}/accept
```

Must reject stale `base_revision` with a structured conflict response.

No silent mutation from chat text.

---

## Method design contract

After the construction is accepted, generate a complete method specification while surfacing only material decisions to the user.

The method must distinguish:

- semantic research method;
- executable operations;
- verification requirements;
- output contract;
- limitations;
- unresolved material decisions.

Suggested structure:

```json
{
  "method_spec": {
    "inputs": [],
    "entity_alignment": {},
    "time_alignment": {},
    "transforms": [],
    "availability_rules": {},
    "derived_fields": [],
    "validation": {},
    "output": {},
    "limitations": []
  },
  "routine_decisions": [],
  "material_decisions": [
    {
      "decision_id": "weighting",
      "question": "How should core components contribute?",
      "recommended_option": "equal",
      "options": [],
      "effects": [],
      "status": "open"
    }
  ]
}
```

One material decision may be highlighted at a time in the frontend, but the backend may hold multiple open decisions.

---

## Compiler requirements

The compiler converts the accepted semantic method into a deterministic, revision-bound execution plan.

Suggested endpoint:

```http
POST /library/synthesis/threads/{thread_id}/compile
```

Minimum execution vocabulary:

```text
read registered dataset
select fields
filter rows
rename fields
map entities
aggregate time
resample frequency
join
as-of join
point-in-time join
event alignment
window transform
normalize within source
winsorize / clip
fill / exclude according to explicit policy
calculate derived field
aggregate metrics
validate constraints
emit lineage
write output
register output
```

The compiler response must include:

```json
{
  "thread_id": "syn_...",
  "compiled_from_revision": 8,
  "plan_id": "plan_...",
  "plan_hash": "sha256:...",
  "supported": true,
  "supported_operations": [],
  "unsupported_operations": [],
  "material_decisions_remaining": [],
  "execution_spec": {},
  "output_contract": {},
  "verification_contract": {},
  "estimated_cost": {},
  "estimated_runtime_class": "small"
}
```

If unsupported, return the precise unsupported operation and potential fallback. Do not pretend that a semantic state change is executable data logic.

---

## Bounded preview requirements

Preview must be a real bounded execution against locked input revisions.

Suggested endpoint:

```http
POST /library/synthesis/threads/{thread_id}/preview
```

Request:

```json
{
  "plan_id": "plan_...",
  "plan_hash": "sha256:...",
  "limits": {
    "max_rows": 5000,
    "max_entities": 50,
    "date_window": null
  }
}
```

Response must include:

```json
{
  "preview_id": "preview_...",
  "plan_hash": "sha256:...",
  "input_revisions": [],
  "sample_rows": [],
  "schema": [],
  "coverage": {},
  "join_diagnostics": {},
  "missingness": {},
  "verification_results": [],
  "warnings": [],
  "overall_verdict": "ready_with_warning",
  "materialized": false
}
```

Do not use a full registered build and label it preview.

Preview should support at least:

- output row sample;
- schema and type inference;
- key uniqueness;
- entity match rate;
- join match rate;
- coverage before and after transforms;
- missingness by field;
- component availability;
- field-level lineage;
- custom verification rules;
- warnings with actionable interpretations.

---

## Verification requirements

Verification is a first-class contract, not just logs.

Every verification result should include:

```json
{
  "check_id": "unique_asset_week",
  "category": "output_key",
  "status": "pass",
  "severity": "error",
  "summary": "Output key is unique",
  "observed": {"duplicate_rows": 0},
  "expected": {"duplicate_rows": 0},
  "evidence": {},
  "suggested_responses": []
}
```

Required categories:

- input availability;
- schema compatibility;
- entity resolution;
- temporal compatibility;
- join coverage;
- output key integrity;
- missingness;
- lineage completeness;
- source-version consistency;
- point-in-time leakage where relevant;
- custom construct-specific checks.

Warnings must not be collapsed into generic success.

---

## Execution and approval lifecycle

Execution must be revision-bound and approval-aware.

Suggested submission endpoint:

```http
POST /library/synthesis/threads/{thread_id}/executions
```

Request:

```json
{
  "plan_id": "plan_...",
  "plan_hash": "sha256:...",
  "preview_id": "preview_...",
  "accepted_thread_revision": 8,
  "accepted_warnings": ["component_domination"]
}
```

Response:

```json
{
  "job_id": "job_...",
  "status": "pending_approval",
  "write_effect": {
    "creates_dataset_id": "stablecoin_attention_weekly",
    "registers_library_asset": true
  }
}
```

Approval:

```http
POST /library/jobs/{job_id}/approve
```

Polling must preserve durable state after reload.

Execution must fail if:

- thread revision changed after compilation;
- plan hash changed;
- input revision no longer matches unless explicitly refreshed;
- required approval is absent;
- output identity conflicts without an explicit overwrite/version policy.

---

## Registration proof

A registered result must expose durable proof:

```json
{
  "dataset_id": "stablecoin_attention_weekly",
  "version_id": "ver_...",
  "row_count": 13827,
  "field_count": 7,
  "coverage": {},
  "manifest_id": "manifest_...",
  "manifest_hash": "sha256:...",
  "drive_verified": true,
  "library_query_ready": true,
  "source_revisions": [],
  "accepted_plan_hash": "sha256:...",
  "registered_at": "..."
}
```

The frontend must be able to reopen the Library asset and recover the Synthesis provenance.

---

## Refresh semantics

Refresh should not silently rerun stale logic.

Required behavior:

1. compare current source revisions against locked source revisions;
2. report what changed;
3. identify whether recompilation is necessary;
4. preserve the accepted method revision;
5. run preview again when changes affect schema, coverage, or compatibility;
6. create a new output version rather than silently overwriting unless the contract explicitly allows overwrite;
7. preserve prior manifests.

Suggested endpoint:

```http
POST /library/synthesis/threads/{thread_id}/refresh-assessment
```

---

## Error contract

Every endpoint must return stable machine-readable errors.

Minimum fields:

```json
{
  "error_code": "SYNTHESIS_PLAN_STALE",
  "message": "The thread changed after this plan was compiled.",
  "recoverable": true,
  "recommended_action": "recompile",
  "details": {}
}
```

Required error families:

```text
THREAD_NOT_FOUND
THREAD_REVISION_CONFLICT
INTERPRETATION_BLOCKED
RECOMMENDATION_FAILED
MATERIAL_DECISION_REQUIRED
UNSUPPORTED_OPERATION
PLAN_COMPILE_FAILED
PLAN_STALE
PREVIEW_FAILED
PREVIEW_STALE
APPROVAL_REQUIRED
EXECUTION_FAILED
REGISTRATION_FAILED
OUTPUT_ID_CONFLICT
SOURCE_REVISION_CHANGED
CAPABILITY_UNAVAILABLE
```

---

## Capability discovery

The frontend must be able to distinguish target product concepts from currently executable operations.

Suggested endpoint:

```http
GET /library/synthesis/capabilities
```

Response:

```json
{
  "compiler_version": "...",
  "operations": {
    "join": {"supported": true},
    "as_of_join": {"supported": false, "reason": "not installed"}
  },
  "preview": {
    "supported": true,
    "limits": {}
  },
  "verification_checks": [],
  "registration": {"supported": true}
}
```

Unsupported capabilities must not cause the frontend to claim a build is ready.

---

## Test requirements

Grok's PR is not reviewable without tests and fixtures.

### Contract tests

- create thread from objective;
- return structured interpretation;
- produce one recommendation plus alternatives;
- accept construction with revision increment;
- produce method spec;
- resolve a material decision;
- compile supported method;
- reject unsupported method honestly;
- reject stale plan;
- run bounded preview;
- return diagnostics;
- submit execution;
- require approval;
- persist running state;
- register output;
- preserve proof after reload;
- fail and retry;
- assess refresh.

### Golden fixtures

Commit deterministic fixtures for at least:

1. stablecoin attention index;
2. point-in-time fundamentals panel;
3. event-aligned security panel;
4. unsupported multi-source construction;
5. preview warning;
6. execution failure;
7. registered output proof.

Fixtures should be consumable by frontend mocks.

### Integration proof

Each backend PR must include:

- endpoint list;
- schema links;
- test command and result;
- sample request/response;
- known unsupported operations;
- migration notes;
- fixture commit paths.

---

## Branch and PR discipline

Recommended backend branch:

```text
feat/synthesis-runtime
```

Recommended slices:

1. `feat/synthesis-thread-contracts`
2. `feat/synthesis-interpret-recommend`
3. `feat/synthesis-method-compiler`
4. `feat/synthesis-bounded-preview`
5. `feat/synthesis-verification`
6. `feat/synthesis-execution-registration`
7. `feat/synthesis-refresh`

Smaller reviewable PRs are preferred over one opaque mega-PR.

Every PR must link the public implementation tracker and state which S-04 lifecycle slice it implements.

---

## Required handoff back to frontend owner

For every completed slice, provide:

```text
1. Exact endpoint and schema.
2. Stable fixture payload.
3. Error codes.
4. Lifecycle status changes.
5. Unsupported cases.
6. Test evidence.
7. Migration requirement.
8. Whether the public frontend can integrate immediately.
```

Do not hand back only prose such as “backend is ready.”

---

## Non-goals for Grok

Do not independently:

- redesign Synthesis;
- replace S-04 with the current profile browser;
- add a permanent node editor;
- change the page navigation model;
- make Ask a separate chat history;
- expose internal worker telemetry as the default UI;
- write user-facing product copy into backend responses;
- skip preview and jump directly to build;
- claim empirical validity from correlation or descriptive checks;
- collapse warnings into pass;
- register outputs without manifest and revision proof.

---

## Review gates

A backend slice is accepted only when:

- its contract matches the S-04 product state;
- the frontend can consume deterministic fixtures;
- unsupported behavior is explicit;
- revision and hash binding are enforced;
- failure states are testable;
- durable state survives reload;
- no endpoint claims a consequence it cannot prove;
- integration evidence is posted in GitHub.

The frontend owner will review contracts, code diffs where accessible, fixtures, CI evidence, and rendered integration behavior before the product slice is considered complete.

---

## Access limitation and evidence requirement

The current GitHub connector can directly inspect `Spectating101/yzu-cluster`. It does not currently provide direct access to the private `Sharpe-Renaissance/drive` backend repository.

Until that access changes, Grok must mirror enough implementation evidence into the public tracker or an accessible PR for independent review:

- commit or PR reference;
- schema diff;
- fixture payloads;
- test output;
- capability matrix;
- known limitations;
- integration instructions.

Without this evidence, the backend work cannot be treated as independently reviewed even if it is reported as complete.

---

## Completion statement

Grok's lane is complete when the backend can support a real S-04 vertical slice from thread creation through registered output with durable state, preview diagnostics, approval, proof, failure recovery, and frontend-consumable contracts.

The product is not complete merely because endpoints exist. The final acceptance occurs after the frontend owner integrates the runtime, reviews desktop and mobile renders, validates browser contracts, and confirms that the implemented behavior preserves the S-04 product model.
