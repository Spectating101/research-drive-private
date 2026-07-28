# Discover release topology

**Canonical as of 2026-07-28.** This is the current-state handoff for the Discover redesign. It supersedes older Discover branch and worktree coordinates; older documents remain historical provenance.

## Two repositories, not one branch graph

| Lane | GitHub authority | Current base | Current review head | PR |
|---|---|---|---|---|
| Public product and interface | `Spectating101/yzu-cluster` | `feat/showcase-terra-port` (`2863b0e`) | `feat/discover-evidence-verdict-cdf` (`51c42d6`) | `yzu-cluster#59` |
| Private production control plane | `Spectating101/research-drive-private` | `feat/discover-fe-be-integration` (`9d2313e`) | `feat/discover-evidence-verdict` (`744336b`) | `research-drive-private#20` |

The two repositories have independent root histories. They are **contract-coupled, not merge-coupled**. Never merge or rebase one repository's branch into the other repository.

## Ownership boundary

### Public/UI lane

Owns:

- `drive/src/v2/` interface composition;
- browser fixtures and Playwright evidence;
- public product and interaction contracts;
- the dependency-free public interoperability reference.

Does not own production secrets, registry mutation, workers, scrapers, archive promotion, or host deployment state.

### Private/backend lane

Owns:

- `/library/discover/intents` and held-evidence assessment APIs;
- MCP, workers, acquisition execution, approval and registration;
- registry mutation, archive verification, and production host integration.

The committed `DiscoverIntentStore` is the procurement authority. The unserved research-needs experiment is not part of either release head.

## Discover identity and workflow contract

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

1. Review and merge private PR #20 into `feat/discover-fe-be-integration`.
2. Review and merge public PR #59 into `feat/showcase-terra-port`.
3. Run the shared payload and browser contract against those exact merged heads.
4. Promote the public feature base toward `yzu-cluster/main`.
5. Reconcile the private feature base with `research-drive-private/main` in a separate release PR.
6. Deploy only merged private `main` plus an explicitly selected public build.

The private base is currently **95 commits behind and 4 commits ahead** of private `main`. One of those four commits carries a large research-engine tree. Do not resolve that divergence by an automatic merge, rebase, or wholesale cherry-pick. A private release owner must explicitly approve the included commit set.

The public base is currently **0 commits behind and 41 commits ahead** of public `main`; PR #59 adds six commits on top.

## Local worktree authority

| Worktree | Status for this release |
|---|---|
| `/tmp/rd-discover-evidence-cdf` | Canonical public PR #59 worktree |
| `/tmp/rd-discover-evidence-backend` | Canonical private PR #20 worktree |
| `Sharpe-Renaissance/` | Dirty omnibus checkout; inspect only, never use as the Discover merge source |
| `/tmp/rd-discover-evidence-main` | Superseded reconciliation experiment; read-only provenance |
| `/tmp/rd-discover-evidence-frontend` | Superseded earlier frontend experiment; read-only provenance |
| `Sharpe-Renaissance-discover-converge/` | Superseded cross-lane convergence attempt; do not merge |
| live front-door and runtime-integration checkouts | Deployment/runtime roles only; not design-authoring worktrees |

Do not delete historical worktrees until their owners and uncommitted changes are mapped. Their existence does not grant them release authority.

## Required checks

Run:

```bash
bash scripts/discover_topology_check.sh
npm run build
npm run test:candidate-key
```

Then run the focused Discover Playwright journey. A mergeable PR is necessary but not sufficient; the base branch and remote must also match this document.
