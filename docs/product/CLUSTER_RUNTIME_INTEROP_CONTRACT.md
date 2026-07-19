# Research Drive cluster runtime interoperability contract

**Status:** implementation contract  
**Applies to:** Discover, Synthesis, Library, Resources, Detail | Ask, and the YZU control plane  
**Compatibility:** additive; existing payloads remain valid

## 1. Purpose

Research Drive already owns the researcher-facing product and the YZU control plane. External systems such as connector frameworks, lineage emitters, metadata catalogs, versioning systems, or alternate executors must integrate behind stable Drive contracts rather than introduce new faculty-facing products.

The shared path is:

```text
Discover source/access truth
→ capability-aware YZU job
→ execution lifecycle proof
→ Synthesis verification and registration
→ Library asset authority
→ shared Detail | Ask context
```

This document defines the optional fields that make that path interoperable and honest.

## 2. Global truth rules

1. Missing data remains unknown. Do not infer availability, progress, verification, registration, compatibility, or query readiness.
2. `completed` means execution ended successfully. It does not mean the output was archived, registered, or query-ready.
3. `registered` requires an explicit registration/materialisation state or registry proof.
4. Progress is displayed only from an explicit percentage or an authoritative `current / total` pair.
5. A worker is incompatible only when its capabilities were reported and do not satisfy the job. Missing capability telemetry is `unknown`, not `blocked`.
6. `Query-ready` is distinct from `Registered`, which is distinct from `Metadata only`.
7. Source verification is independent from readiness. A query-ready self-provided asset may remain unverified.
8. External integration identifiers and backend telemetry stay subordinate to the existing seven-page product.

## 3. Connector and acquisition contract

A Discover candidate or Resources source route may add:

```json
{
  "connector_id": "mops-api",
  "source_id": "mops",
  "source_name": "MOPS",
  "endpoint": "https://mops.twse.com.tw/...",
  "access_state": "available",
  "credential_required": false,
  "credential_profile": null,
  "license": "Open Government",
  "terms_url": null,
  "sync_mode": "incremental",
  "cursor_field": "published_at",
  "state_token": "2026-07-19T00:00:00Z",
  "refresh_policy": "weekly",
  "last_synced_at": "2026-07-19T03:00:00Z",
  "schema_discovered": true,
  "schema_fields": ["issuer_id", "published_at", "filing_type"],
  "primary_key": ["issuer_id", "published_at", "filing_type"],
  "rate_limit": "60/min",
  "quota_remaining": 5000,
  "estimated_bytes": 2147483648,
  "max_retries": 4,
  "probe_required": false,
  "retryable": true,
  "supported": true
}
```

Canonical access states:

```text
available
credential_required
rate_limited
unavailable
unknown
```

Canonical sync modes:

```text
incremental
stream
snapshot
unknown
```

An Airbyte connector, custom scraper, public API adapter, or direct-file collector may emit this shape. The frontend does not depend on Airbyte itself.

## 4. Worker capability and routing contract

A worker may report:

```json
{
  "id": "spectator",
  "pool": "spectator",
  "status": "online",
  "busy": false,
  "capabilities": ["browser", "python", "http"]
}
```

A job may request:

```json
{
  "job_type": "scraper_run",
  "requirements": {
    "capabilities": ["browser"],
    "cpu_cores": 2,
    "memory_mb": 4096,
    "staging_bytes": 10737418240
  }
}
```

Canonical capability names include:

```text
browser
python
http
archive
pipeline
windows
gpu
high_disk
```

Aliases may be normalized internally, for example:

```text
Puppeteer / Playwright / CDP → browser
rclone / GDrive              → archive
CUDA                          → gpu
```

Canonical routing states:

```text
satisfied            assigned worker explicitly satisfies requirements
assigned_unverified  worker assigned but capability telemetry absent
eligible             one or more suitable online workers exist
unknown              inventory or capability telemetry absent
blocked              reported inventory proves no valid route
not_required         job declares no material capability requirement
```

## 5. Execution lifecycle contract

A YZU job may add:

```json
{
  "run_id": "job-attention-v1",
  "status": "validating",
  "worker": "optiplex",
  "worker_pool": "optiplex",
  "attempt": 1,
  "heartbeat_at": "2026-07-19T06:30:00Z",
  "started_at": "2026-07-19T06:20:00Z",
  "progress": {
    "current": 4,
    "total": 5
  },
  "inputs": ["reddit-engagement", "wikipedia-pageviews"],
  "outputs": ["stablecoin_attention_weekly_v1"],
  "manifest_id": "manifest-attention-v1",
  "archive_verified": false,
  "registry_verified": false,
  "rows": 3120,
  "fields": 14,
  "entities": 29,
  "retryable": true,
  "events": [
    {
      "event_type": "START",
      "timestamp": "2026-07-19T06:20:00Z"
    },
    {
      "event_type": "validating",
      "timestamp": "2026-07-19T06:29:00Z"
    }
  ]
}
```

Canonical stages:

```text
pending_approval
queued
assigned
retrying
running
validating
archiving
registering
registered
completed
blocked
failed
```

Recommended emission boundaries:

```text
submission       queued
worker lease     assigned + worker + pool + heartbeat
execution start  running + started_at
bounded phase    progress and research-relevant event
validation       validating + provisional output shape
archive          archiving + manifest_id
registration     registering
success          registered + archive_verified + registry_verified
failure          failed/blocked + error + retryable
```

Low-level CPU, memory, queue, and log telemetry belongs in Resources or technical logs. Synthesis receives only research-relevant progress and proof.

## 6. Synthesis execution binding

A Synthesis thread continues to own its durable state. Its execution record may include the lifecycle fields above:

```json
{
  "state": {
    "execution_spec": {
      "input_dataset_ids": ["reddit-engagement", "wikipedia-pageviews"],
      "output_dataset_id": "stablecoin_attention_weekly_v1"
    },
    "execution": {
      "job_id": "job-attention-v1",
      "status": "completed",
      "worker": "optiplex",
      "manifest_id": "manifest-attention-v1",
      "drive_verified": true,
      "rows": 3120,
      "field_count": 14,
      "output_dataset_id": "stablecoin_attention_weekly_v1"
    }
  },
  "materialisation": "registered"
}
```

`materialisation: registered` is the explicit boundary that permits the registered view and `Open in Library` action. A completed job without registration proof remains completed, not registered.

## 7. Library asset authority contract

A durable dataset may add:

```json
{
  "dataset_id": "stablecoin_attention_weekly_v1",
  "registry_id": "registry:stablecoin_attention_weekly_v1",
  "revision_id": "rev-1",
  "analysis_readiness": "query_ready",
  "source": {
    "name": "Derived from registered evidence",
    "version": "2026-07-19"
  },
  "verification": {
    "state": "partial",
    "summary": "29 of 30 entities matched",
    "checked_at": "2026-07-19T06:35:00Z"
  },
  "lineage": {
    "inputs": ["reddit-engagement", "wikipedia-pageviews"],
    "source_snapshots": ["reddit@2026-07-19", "wikipedia@2026-07-19"],
    "method_revision": "method-rev-4"
  },
  "manifest_id": "manifest-attention-v1",
  "checksum": "sha256:...",
  "vault_path": "gdrive:Machine_Archive/...",
  "drive_verified": true,
  "refresh_policy": "weekly",
  "last_refreshed_at": "2026-07-19T06:35:00Z",
  "next_refresh_at": "2026-07-26T06:35:00Z",
  "row_count": 3120,
  "field_count": 14,
  "entity_count": 29,
  "grain": "asset-week",
  "coverage": "2024-W01–2026-W28"
}
```

Canonical readiness states:

```text
metadata_only
registered
query_ready
unavailable_unverified
unknown
```

Canonical source-verification states:

```text
verified
matched
partial
unverified
not_checked
```

## 8. Detail | Ask projection

The frontend projects these contracts into the existing rail context. Ask may receive:

```text
connector access, credentials, schema, sync and limits
job stage, worker, route, progress, retries, inputs and outputs
manifest, archive and registry proof
asset identity, revision, readiness, source, verification and lineage
refresh and output-shape facts
```

Ask may explain or propose supported actions. It may not invent missing fields or convert proposals into durable changes without the existing review boundary.

## 9. Integration strategy

External systems should map into these contracts:

| External primitive | Drive boundary |
|---|---|
| Airbyte-compatible connector | connector and sync contract |
| OpenLineage/Dagster event | execution lifecycle event |
| DataHub/OpenMetadata object | Library asset authority and lineage |
| DVC/DataLad revision | revision, checksum, source snapshots, manifest |
| Galaxy/Renku executor | worker capability plus execution lifecycle |
| Dataverse/InvenioRDM/OSF deposit | registration identity and preservation proof |

Drive does not expose those systems as new navigation destinations. The current frontend remains the product authority.

## 10. Current implementation files

```text
drive/src/v2/connectorContract.js
drive/src/v2/workerRouting.js
drive/src/v2/executionLifecycle.js
drive/src/v2/assetAuthority.js
drive/src/v2/railContext.js
drive/src/v2/resourcesLedger.js
```

Contract verification:

```bash
npm run test:runtime-contract
npm run build
```
