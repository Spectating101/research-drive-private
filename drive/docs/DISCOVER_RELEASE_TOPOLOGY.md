# Discover release topology

**Canonical as of 2026-07-28.** This is the current-state handoff for the Discover redesign. It supersedes older Discover branch and worktree coordinates; older documents remain historical provenance.

## Two repositories, not one branch graph

| Lane | GitHub authority | Current base | Current review head | PR |
|---|---|---|---|---|
| Public product and interface | `Spectating101/yzu-cluster` | `feat/showcase-terra-port` (`2863b0e`) | `feat/discover-evidence-verdict-cdf` (`51c42d6`) | `yzu-cluster#59` |
| Private production control plane | `Spectating101/research-drive-private` | `feat/discover-fe-be-integration` (`9d2313e`) | `feat/discover-evidence-verdict` (`744336b`) | `research-drive-private#20` |

The repositories have independent root histories. They are **contract-coupled, not merge-coupled**. Never merge or rebase a branch from one repository into the other.

## Authority boundary

### Public/UI lane

Owns the React product, interaction contracts, browser fixtures, rendered evidence, and public interoperability reference.

### Private/backend lane

Owns `/library/discover/intents`, held-evidence assessment, MCP, approval-gated jobs, workers, acquisition execution, archive verification, registry promotion, and production host integration.

`DiscoverIntentStore` is the procurement authority. The unserved research-needs experiment is not part of either review head.

## Durable identity contract

```text
question / keyword
→ candidate_key
→ durable intent_id
→ reviewed route_id
→ approval-gated job_id
→ output_manifest_id when emitted
→ registered_dataset_id
→ Library asset
```

`completed`, `registered`, and `query_ready` remain distinct.

## Promotion order

1. Merge private PR #20 into `feat/discover-fe-be-integration`.
2. Merge public PR #59 into `feat/showcase-terra-port`.
3. Run shared API-payload and browser contracts against those merged heads.
4. Promote the public feature base toward `yzu-cluster/main`.
5. Reconcile the private feature base with `research-drive-private/main` through a separate release PR.
6. Deploy only merged private `main` plus an explicitly selected public build.

The private feature base is currently **95 commits behind and 4 commits ahead** of private `main`. Its ahead set includes a large research-engine commit. Do not resolve this with an automatic merge, rebase, or wholesale cherry-pick. The private release owner must explicitly approve the included commit set.

The public feature base is currently **0 commits behind and 41 commits ahead** of public `main`; PR #59 adds six commits on top.

## Local worktree authority

| Worktree | Status for this release |
|---|---|
| `/tmp/rd-discover-evidence-backend` | Canonical private PR #20 worktree |
| `/tmp/rd-discover-evidence-cdf` | Canonical public PR #59 worktree |
| `Sharpe-Renaissance/` | Dirty omnibus checkout; inspect only, never use as the Discover merge source |
| `/tmp/rd-discover-evidence-main` | Superseded reconciliation experiment; read-only provenance |
| `/tmp/rd-discover-evidence-frontend` | Superseded earlier frontend experiment; read-only provenance |
| `Sharpe-Renaissance-discover-converge/` | Superseded cross-lane convergence attempt; do not merge |
| front-door and runtime-integration checkouts | Deployment/runtime roles only; not design-authoring worktrees |

Do not delete historical worktrees until their owners and uncommitted changes are mapped.

## Required checks

```bash
bash drive/scripts/ops/discover_topology_check.sh
```

Then run the held-evidence, intent-state, HTTP-router, and frontend payload-contract suites at the exact paired heads.
