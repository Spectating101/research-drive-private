# Discover Acquisition Lifecycle — visual notes

Backend status map (authoritative):

| Backend | User lifecycle | Terminal |
|---|---|---|
| `pending_approval` | Approval required | no |
| `queued` | Queued | no |
| `running` | Running | no |
| `failed` | Failed | yes |
| `completed` + no `registered_dataset_id` | Collection complete · Registration pending | yes |
| `completed` + `registered_dataset_id` | Registered in lab | yes |
| + catalog `analysis_readiness` instant/queryable | In lab · Query ready | yes |

Linkage: exact `candidate_key` or exact `connector_id` only.

## Screenshots

### 01 — pre-submit acquisition available
- **Evidence:** no exact job
- **Decision:** acquire after probe
- **Primary:** Add to lab
- **Not claimed:** queued/running

### 02 — submitting
- **Evidence:** frontend submitting flag before job response
- **Decision:** wait; do not double-submit
- **Primary:** Submitting…
- **Not claimed:** queued before response

### 03 — approval required
- **Evidence:** `pending_approval`
- **Decision:** approve or track
- **Primary:** Review approval
- **Not claimed:** running

### 04 — queued
- **Evidence:** `queued`
- **Decision:** wait for worker
- **Primary:** Track in Resources
- **Not claimed:** running

### 05 — running
- **Evidence:** `running` + optional stage
- **Decision:** monitor
- **Primary:** Track in Resources
- **Not claimed:** fake %

### 06 — failed
- **Evidence:** `failed` + error
- **Decision:** review failure
- **Primary:** Track in Resources
- **Not claimed:** acquisition available

### 07 — registration pending
- **Evidence:** `completed` without `registered_dataset_id`
- **Decision:** wait for registry
- **Not claimed:** In lab / Query ready

### 08 — registered
- **Evidence:** `registered_dataset_id` without query-readiness evidence
- **Primary:** Open in Library
- **Not claimed:** Query ready

### 09 — query ready
- **Evidence:** `registered_dataset_id` + `result.query_ready` / `analysis_readiness: instant` (or catalog readiness)
- **Primary:** Open in Library

### 10 — Resources deep-link
- **Evidence:** exact `job.id` row key `job-{id}`
- **Decision:** approve/operate in Resources

### 11–16
Tablet/mobile variants of running, failed, approval, registered.

## Gaps
- `output_manifest_id` usually null — kept null when absent
- Archive/GDrive completion is a follow-on job — not claimed as parent completion
- No Sharpe-Renaissance changes in this pass

## Scope
Sufficiency / Equivalence not started. Final Responsive not started.
Evaluation Surface visual language preserved.
