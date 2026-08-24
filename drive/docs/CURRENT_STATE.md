# Research Drive Current State

**Updated:** 2026-07-27  
**Use this document first.** It identifies the authority for current product, runtime, and deployment facts. It intentionally does not repeat volatile counts, branch heads, job state, or host inventory.

## Product

Research Drive is a faculty research-data procurement environment:

```text
research question
→ held-evidence assessment
→ external source evaluation
→ bounded route decision
→ approval-gated collection
→ archive verification
→ Library registration and reuse
```

The researcher-facing navigation remains:

```text
Home · Library · Discover · Synthesis · Resources
```

Discover owns `Explore | History`. Do not introduce a permanent acquisition-plan destination. A route comparison is a temporary Explore state, and History owns durable requests, runs, recovery, and registered outputs.

## Truth Rules

```text
completed != registered != query_ready
provider-reported != observed
AI-inferred != verified backend capability
unknown remains unknown
```

Every consequential collection must retain a durable identity from source/candidate through job, archive evidence, registry identity, and Library asset.

## Authority

| Concern | Source of truth |
| --- | --- |
| Private runtime, jobs, workers, archive, registry, MCP | `Spectating101/research-drive-private` |
| Public frontend, interaction contracts, visual tests | `Spectating101/yzu-cluster` |
| Local runtime bytes and databases | The configured runtime data root, never Git cleanup commands |
| Current branch, PR, CI, deployment, host state | Verify directly before acting; no document is a substitute |

See [REPO_AUTHORITY.md](REPO_AUTHORITY.md) for remote and local-checkout rules.

## Current Design Direction

The next Discover iteration is an evidence landscape, not a catalogue landing page:

```text
question
→ coverage verdict
→ held evidence
→ unresolved gap
→ viable offerings
→ temporary route comparison
```

`Detail | Ask` are two exclusive views of the selected asset, candidate, gap, or job. Ask may explain and open a visible route comparison, but it must not silently submit procurement or become a second persistent workspace.

## Documentation Map

| Document | Use |
| --- | --- |
| [REPO_AUTHORITY.md](REPO_AUTHORITY.md) | Remote, checkout, and push authority |
| [REPOSITORY_TOPOLOGY.md](REPOSITORY_TOPOLOGY.md) | Runtime contracts and source layout |
| [SOL_REMOTE_HANDOFF.md](SOL_REMOTE_HANDOFF.md) | Short agent remote/push rules |
| [WINDOWS_WORKER_ACCEPTANCE.md](WINDOWS_WORKER_ACCEPTANCE.md) | Repeatable Windows-worker acceptance procedure |
| [DATABANK_STATE.md](DATABANK_STATE.md) | Historical inventory snapshot, not live status |
| [DESK_ACTIVATION.md](DESK_ACTIVATION.md) | Historical activation backlog, not current product authority |
| `status/generated/` | Generated reports; use their timestamps and regenerate rather than edit |

## Working Rules

1. Check live API, Git, CI, and deployment state before claiming current status.
2. Do not merge or deploy from the broadly dirty integration checkout.
3. Make product changes in bounded branches with browser evidence.
4. Preserve historical documents for provenance; mark them dated rather than deleting them without an explicit retention decision.
