# Private Runtime Adoption

## Current architecture

The faculty service is assembled by `scripts.research_data_mcp.bootstrap.create_stack`:

```text
HTTP router -> JobService -> YzuOrchestrator -> YzuExecutor
                         -> RegistryPromoter / Drive-first finalisation
                         -> ResearchQueryEngine / Composer-facing gateway
```

`YzuOrchestrator` currently persists legacy jobs in
`data_lake/yzu_cluster/jobs/jobs.sqlite3`. `YzuJobStore` owns two existing
tables:

```text
jobs(id, created_at, updated_at, status, title, request_json, plan_json,
     result_json, error)
events(id, job_id, created_at, level, message)
```

The controller currently executes one queued job at a time. Windows workers
are dispatched by the controller and are not yet lease-owning runtime workers.

## Verified truth boundaries

Synthesis already finalises to Drive before promotion and records a failed
finalisation back to the synthesis thread. Generic collection currently
promotes before Drive verification, so it must be corrected before a promoted
asset is exposed as registered or query-ready.

```text
completed != registered != query_ready
```

## Adoption strategy

The public `InteropStore` reference cannot be imported directly into the
existing database: it defines an incompatible `events` table. The private
runtime will add namespaced runtime tables to the existing database and keep
legacy `jobs` and `events` intact.

```text
jobs / events                         legacy compatibility projection
cluster_runs / cluster_events         authoritative runtime lifecycle
cluster_workers                        capability, freshness, capacity
cluster_requirements / reservations    resource-aware claims
cluster_usage                          accounting
cluster_connectors                     Discover probe and checkpoint state
cluster_assets                         proof-gated Library registration
```

The implementation must preserve the public PR #41 behavioral contract:

* stable idempotent submission;
* capability and capacity-aware claims;
* worker heartbeats, leases, retries, and stale-worker visibility;
* attempt fencing for heartbeats, usage, lifecycle events, and registration;
* explicit progress only;
* archive proof before registry promotion;
* registration proof matching the declared output; and
* compatibility payloads for existing Discover, Resources, Synthesis, Library,
  and Detail | Ask consumers.

## Delivery order

1. Add the namespaced schema, migration checks, and runtime adapter tests.
2. Bind legacy job IDs to idempotent runtime runs without changing routes.
3. Route worker claims and lifecycle writes through the runtime adapter.
4. Correct generic collection to validate, archive, verify, promote, then
   expose the registered asset.
5. Add a Windows worker heartbeat/capacity endpoint and prove one live run plus
   one expired-lease retry.
