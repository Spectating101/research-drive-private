# Research Drive repository topology

> **Current Discover authority (2026-07-28):**
> [DISCOVER_RELEASE_TOPOLOGY.md](./DISCOVER_RELEASE_TOPOLOGY.md) is the canonical branch,
> PR, worktree, and promotion map for the active Discover redesign. Release coordinates
> below are retained as historical context where they differ.

This document is the repository authority for Research Drive. It separates the intentional public/private boundary from accidental branch and package duplication.

## Three layers

| Layer | Authority | Purpose |
|---|---|---|
| Public product and contract | `Spectating101/yzu-cluster` | React interface, public documentation, visual fixtures, E2E tests, and the executable interoperability reference under `scripts/yzu_cluster/` |
| Private production control plane | `Spectating101/research-drive-private` | Full API, MCP, orchestrator, workers, scrapers, registry writes, archive integration, host configuration, and production data paths |
| Live deployment | Optiplex, Windows workers, and GDrive | Host-specific execution and acceptance evidence; never a separate source-of-truth repository |

Public and private are not fake versus real. The public runtime is an executable reference and behavioral contract. The private runtime is its production adoption inside the existing control plane.

## Current release authorities

### Public

- Canonical branch: `main`
- RC1 merge: `db75061f229048c063c4201b701e4917fcbfe9e3` from PR #41
- Integration hardening merge: `0c65418e95fb3a73be14a6e57795e63b017e56d4` from PR #42
- Rollback branch: `archive/pre-rc1-main-2026-07-20`
- `main` contains the cumulative product line plus bounded request handling, robust NDJSON completion, FastAPI error normalization, and distinct completed/registered/query-ready lifecycle projection.

PRs before #41 are closed development provenance. PR #42 was a focused integration correction, not another product-design lane.

### Private

- Deployment candidate: `research-drive-private#1`
- Candidate branch: `terra/runtime-integration`
- Tested runtime head: `439f302a1394e9dfa9c04c2880d3c8a6a352c0db`
- Current candidate documentation head: `ac69635b7eca9edbdd1c883bc6c5950e29c528c1`
- Target: `main`
- Rollback branch: `archive/pre-runtime-main-2026-07-20`
- PR #1 is the only production runtime candidate until merged or explicitly replaced.

## Canonical paths

### Public

- `drive/src/v2/` — researcher-facing interface
- `e2e/` — browser and rendered-state contracts
- `docs/product/` and stable canon docs — public product contracts
- `scripts/yzu_cluster/` — dependency-free interoperability reference
- `tests/test_yzu_interop_*.py` — public behavioral contracts

The public repository must not contain the complete MCP/query engine, production orchestrator, host workers, scrapers, live registry mutation, credentials, databases, data lake, or GDrive configuration. A facade importing absent private modules is not a runnable public backend.

### Private

Production source edits belong in:

- `drive/scripts/research_data_mcp/`
- `drive/scripts/research_query_engine/`
- `drive/scripts/yzu_cluster/`
- `drive/config/`
- `kernel/`

Compatibility imports or symlinks may remain, but do not create a third physical implementation.

## Branch discipline

1. One active cumulative release PR per repository.
2. Superseded PRs are closed, not deleted.
3. Public work branches from `main`; private runtime fixes land on PR #1 until merge.
4. Agents check the current head before touching another agent's branch.
5. Host fixes require regression coverage.
6. Public interface changes after RC1 require real payload or rendered evidence.

## Remaining release sequence

1. Complete live Optiplex/Windows/GDrive acceptance against private PR #1.
2. Patch only evidenced host defects and repeat CI plus acceptance.
3. Merge private PR #1 with a merge commit.
4. Deploy merged private `main` and repeat the success path.
5. Capture a sanitized golden payload chain.
6. Replay it through public `main` and complete desktop/mobile rendered acceptance.

## Rollback

- Never rewrite shared history for cleanup.
- Revert public RC1 through `db75061f229048c063c4201b701e4917fcbfe9e3` if needed.
- Revert the focused public integration update independently through `0c65418e95fb3a73be14a6e57795e63b017e56d4`.
- The previous public main remains at `archive/pre-rc1-main-2026-07-20`.
- The private release must use a merge commit and remain reversible through one merge revert.

## Product identity chain

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
