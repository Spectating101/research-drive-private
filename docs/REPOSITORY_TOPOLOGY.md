# Research Drive repository topology

This document is the repository authority for Research Drive. It separates the intentional public/private boundary from the accidental branch and package duplication that accumulated during Synthesis and cluster integration.

## Three layers

| Layer | Authority | Purpose |
|---|---|---|
| Public product and contract | `Spectating101/yzu-cluster` | React interface, public product documentation, visual fixtures, E2E tests, and the executable interoperability reference under `scripts/yzu_cluster/` |
| Private production control plane | `Spectating101/research-drive-private` | Full API, MCP, orchestrator, workers, scrapers, registry writes, archive integration, host configuration, and production data paths |
| Live deployment | Optiplex, Windows workers, and GDrive | Host-specific execution and acceptance evidence; never a separate source-of-truth repository |

Public and private are not fake versus real. The public runtime is an executable reference implementation and behavioral contract. The private runtime is the production adoption of that contract inside the existing Research Drive control plane.

## Current release authorities

### Public

- Release candidate PR: `yzu-cluster#41`
- Candidate branch: `agent/cluster-runtime-truth`
- Target branch: `main`
- The branch contains the cumulative interface line from Synthesis S-04 through Discover, Synthesis thread truth, Library, Resources, Home, and interoperability contracts.

PRs preceding #41 are development provenance, not parallel release candidates.

### Private

- Deployment candidate PR: `research-drive-private#1`
- Candidate branch: `terra/runtime-integration`
- Target branch: `main`
- The branch name is historical. PR #1 is the only production runtime candidate until it is merged or explicitly replaced.

## Canonical paths

### Public repository

Allowed product/runtime authorities:

- `drive/src/v2/` — researcher-facing interface
- `e2e/` — browser and rendered-state contracts
- `docs/product/` and stable canon docs — public product contract
- `scripts/yzu_cluster/` — dependency-free interoperability reference runtime
- `tests/test_yzu_interop_*.py` — public behavioral contracts

Not a public authority:

- full MCP or query-engine implementations
- production orchestrator and worker entrypoints
- scrapers and host provisioning
- registry mutation backed by real lab data
- credentials, host inventories, databases, `data_lake/`, or GDrive configuration

A Python facade that imports modules absent from this repository is not a runnable public backend and must not be presented as one.

### Private repository

Canonical production source paths:

- `drive/scripts/research_data_mcp/`
- `drive/scripts/research_query_engine/`
- `drive/scripts/yzu_cluster/`
- `drive/config/`
- `kernel/`

The private runtime may retain compatibility symlinks or import namespaces, but source edits belong in `drive/scripts/...`. Do not create a third implementation path.

## Branch and PR discipline

1. One active cumulative release PR per repository.
2. Experimental and superseded PRs are closed, not deleted; their branches and commits remain available for archaeology or selective recovery.
3. New work branches from the current cumulative candidate or merged `main`, never from an older page-specific branch.
4. No agent pushes to another agent's active branch without first checking the current head.
5. Host-specific fixes remain on the private candidate and require automated coverage before acceptance is repeated.
6. Public interface changes after RC creation must be driven by real payload or rendered evidence, not a new broad redesign cycle.

## Merge order

1. Complete live Optiplex/Windows/GDrive acceptance against private PR #1.
2. Patch only evidenced host defects and rerun private CI and acceptance.
3. Merge private PR #1 with a merge commit after preserving the pre-runtime `main` SHA.
4. Capture a sanitized golden production payload chain.
5. Replay that payload through the public interface and complete desktop/mobile rendered acceptance.
6. Merge the public cumulative RC with a merge commit.

## Rollback

- Never rewrite shared history to perform normal cleanup.
- Preserve pre-merge SHAs in the release record.
- Prefer merge commits so either release can be reverted with one merge revert.
- Closing a PR or removing a transitional file does not delete its branch history.

## Product identity chain

The same identifiers must survive across repositories and surfaces:

```text
Discover source
→ job ID / run ID / attempt
→ Resources worker and usage
→ Synthesis execution
→ manifest and verified archive
→ registry ID
→ Library asset
→ Detail | Ask grounding
```

`completed`, `registered`, and `query_ready` remain distinct at every layer.
