# Private Runtime Adoption (historical architecture record)

> **Historical adoption record:** This captures the architecture and acceptance assumptions of the private-runtime adoption pass. It does not establish the current release candidate, deployment status, worker inventory, or remaining gate. Start with [CURRENT_STATE.md](CURRENT_STATE.md) and verify Git, CI, live API, and host evidence directly.

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

Synthesis and Drive-first generic collection finalise to Drive before canonical
promotion. A materialised output must also carry a manifest that proves its
exact output dataset identity. Archive proof, manifest identity, and registry
read-back are required before the runtime may expose a registered or
query-ready asset.

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

Completed in this private branch:

1. Added namespaced `cluster_*` runtime tables beside legacy `jobs` and
   `events`, with no destructive schema migration.
2. Bound new legacy submissions to stable idempotent runtime runs and projected
   runtime facts through existing job payloads.
3. Routed controller execution through capability-aware claims, leases, attempt
   fencing, and truthful completion/registration stages. The controller now
   maintains a runtime heartbeat and refreshes immediately before a local
   claim; browser work remains queued until a live browser-capable worker joins.
4. Added attempt-scoped lease renewal around synchronous executor work. A long
   execution keeps its own lease alive and stops renewal before terminal state
   recording.
5. Corrected Drive-first collection ordering to validate, archive, verify,
   require a matching manifest, promote, read back the registry, then compact
   local staging. An archived output without a valid manifest cannot mutate the
   canonical Library registry.
6. Projected authoritative `lifecycle`, `execution`, archive proof, registration
   identity, and outputs onto the legacy job payload expected by the public
   frontend normalizers. Resources now carries the runtime worker, freshness,
   reservation, usage, and run rollups alongside existing legacy fields.
7. Moved semantic indexing, flywheel, campaign, and thread presentation work to
   a best-effort post-registration hook. Failure there records a warning without
   rewriting a registered execution as failed.
8. Added legacy/runtime reconciliation after lease recovery and conflict-safe
   legacy idempotent submission. A private GitHub Actions workflow now runs the
   full non-HMM suite, the 32 reference interop tests, and runtime compilation.

Recorded local verification at adoption time:

```text
217 passed, 9 deselected
```

The nine deselected tests are unrelated trading HMM tests. They require the
optional `hmmlearn` dependency, which is not installed in this runtime
environment.

## Remaining live-adoption gate

The code has not yet proven a real Windows/GDrive run. That needs the actual
worker hosts, authenticated worker transport, and the configured Drive remote:

1. Register one Windows worker with measured capabilities and capacity.
2. Run an approved public-source collection through its heartbeat/lease path.
3. Verify the archived bytes, registry read-back, Library readiness, and
   Resources/Synthesis projection from the same run ID.
4. Stop the worker heartbeat, confirm retry, and confirm the old attempt is
   rejected.

Do not mark this branch deployment-ready until those host-level facts are
captured. The existing HTTP router does not yet expose an authenticated worker
control-plane endpoint, so that transport must be introduced with a secret held
outside Git rather than opening worker claims to unauthenticated callers.

The current private configuration still contains machine-specific inventory and
SSH defaults for operational compatibility. Keep this repository private; move
those values behind deployment-specific local configuration before any wider
access is considered.
