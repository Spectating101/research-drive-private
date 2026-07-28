# Discover release topology

**Canonical as of 2026-07-28.** This is the current-state handoff for the Discover redesign. It supersedes older Discover branch and worktree coordinates; older documents remain historical provenance.

## Two repositories, not one branch graph

| Lane | GitHub authority | Current base | Current review head | PR |
|---|---|---|---|---|
| Public product and interface | `Spectating101/yzu-cluster` | `feat/showcase-terra-port` (`2863b0e`) | `feat/discover-evidence-verdict-cdf` (implementation anchor `51c42d6`) | `yzu-cluster#59` |
| Private production control plane | `Spectating101/research-drive-private` | `main` (`f25c9d2`) | `reconcile/discover-evidence-main` (assessment anchor `f954a0e`) | `research-drive-private#21` |

The repositories have independent root histories. They are **contract-coupled, not merge-coupled**. Never merge or rebase a branch from one repository into the other.

Private PR #20 retains the original feature-lineage implementation for provenance. Its base is 95 commits behind private `main`, so it is **not** the promotion candidate.

## Authority boundary

### Public/UI lane

Owns the React product, interaction contracts, browser fixtures, rendered evidence, and public interoperability reference.

### Private/backend lane

Owns `/library/discover/intents`, held-evidence assessment, MCP, approval-gated jobs, workers, acquisition execution, archive verification, registry promotion, and production host integration.

`DiscoverIntentStore` is the procurement authority. The unserved research-needs experiment is not part of either release head.

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

1. Review and merge private PR #21 into `research-drive-private/main`.
2. Review and merge public PR #59 into `feat/showcase-terra-port`.
3. Run shared API-payload and browser contracts against private `main` plus the merged public feature head.
4. Promote the public feature base toward `yzu-cluster/main`.
5. Deploy only merged private `main` plus an explicitly selected public build.

Private PR #21 is currently **0 commits behind and 3 commits ahead** of private `main`; its compare contains only the bounded assessment port. PR #20's feature base is **95 commits behind and 4 commits ahead**, including a large research-engine tree. Keep PR #20 as provenance and do not promote or cross-merge it.

The public feature base is currently **0 commits behind and 41 commits ahead** of public `main`; PR #59 adds the bounded Discover frontend commits on top.

## Local worktree authority

| Worktree | Status for this release |
|---|---|
| `/tmp/rd-discover-evidence-main` | Canonical private PR #21 worktree |
| `/tmp/rd-discover-evidence-cdf` | Canonical public PR #59 worktree |
| `/tmp/rd-discover-evidence-backend` | PR #20 feature-lineage provenance; not a release source |
| `Sharpe-Renaissance/` | Dirty omnibus checkout; inspect only, never use as the Discover merge source |
| `/tmp/rd-discover-evidence-frontend` | Superseded earlier frontend experiment; read-only provenance |
| `Sharpe-Renaissance-discover-converge/` | Superseded cross-lane convergence attempt; do not merge |
| front-door and runtime-integration checkouts | Deployment/runtime roles only; not design-authoring worktrees |

Do not delete historical worktrees until their owners and uncommitted changes are mapped.

## Required checks

```bash
bash drive/scripts/ops/discover_topology_check.sh
```

Then run held-evidence assessment, intent-state, HTTP-router, and frontend payload/browser contracts at the exact paired heads.
