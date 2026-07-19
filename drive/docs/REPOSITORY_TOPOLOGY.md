# Research Drive private repository topology

This repository is the production control-plane authority for Research Drive. It contains the real orchestrator, MCP, workers, scrapers, registry mutation, archive integration, and host-facing runtime.

## Current authority

- Canonical deployment candidate: PR #1
- Candidate branch: `terra/runtime-integration`
- Tested runtime head: `439f302a1394e9dfa9c04c2880d3c8a6a352c0db`
- Target branch: `main`
- Pre-runtime rollback branch: `archive/pre-runtime-main-2026-07-20`
- Current `main` is the pre-runtime baseline and is not the production-candidate tip.
- The branch name is historical; no additional Terra implementation lane is implied.

Until PR #1 is merged or explicitly replaced, all production runtime work belongs on this candidate branch and must preserve its tested contracts.

## Relationship to the public repository

`Spectating101/yzu-cluster` publishes:

- the researcher-facing interface;
- public product and interaction contracts;
- mock and rendered E2E coverage;
- an executable dependency-free interoperability reference under `scripts/yzu_cluster/`.

This repository adopts those behaviors inside the real control plane. The public package is a reference and contract implementation, not the deployed controller. The private package is the production implementation, not a separate product model.

## Canonical source paths

Production source edits belong in:

- `drive/scripts/research_data_mcp/`
- `drive/scripts/research_query_engine/`
- `drive/scripts/yzu_cluster/`
- `drive/config/`
- `kernel/`

The import namespace may appear as `scripts.*` when `drive/` is on `PYTHONPATH`. Legacy root paths may be symlinks or compatibility entrypoints. Do not create another physical implementation under a third package root.

## Runtime authority rules

1. Existing legacy `jobs` and `events` remain compatibility storage.
2. Namespaced `cluster_*` tables are authoritative for runtime lifecycle, leases, attempts, workers, resources, usage, and registration proof.
3. Compatibility payloads project runtime truth; they do not independently invent lifecycle state.
4. `completed`, `registered`, and `query_ready` remain distinct.
5. Canonical registry mutation requires a matching manifest, verified archive, registry read-back, a process-safe update lock, and atomic file replacement.
6. Old attempts cannot heartbeat, report usage, upload artifacts, complete, fail, or register over a newer attempt.
7. Attempt lease renewal remains active through execution, artifact transfer, archive verification, promotion, read-back, and terminal recording.
8. Remote artifacts are streamed in bounded chunks, incrementally hashed, fenced to one worker attempt, and committed atomically only after complete transfer.
9. Unknown capacity and progress remain unknown.

## Host boundary

The repository may contain deployment tooling, but secrets and mutable host state must remain outside Git:

- tokens and `.env` files;
- OAuth and GDrive credentials;
- rclone configuration;
- SSH private keys;
- databases and journals;
- local datasets and `data_lake/` contents;
- machine-generated logs, caches, and artifacts.

Host inventory should be configuration-driven and private. Do not copy production host material into the public repository.

## One-PR rule

- PR #1 is the only active production runtime release candidate.
- Host-specific fixes discovered during acceptance are added to PR #1 with regression coverage.
- Do not open a competing runtime PR unless PR #1 is explicitly abandoned.
- Do not force-push shared candidate history.

## Acceptance and merge order

1. Run the Optiplex controller and one Windows worker at the exact PR head.
2. Prove one public `http_manifest` job through streamed artifact transfer, materialisation, GDrive verification, registry read-back, and Library readiness.
3. Prove real lease expiry, attempt increment, and rejection of every stale-attempt write.
4. Record sanitized evidence and any host-specific fixes.
5. Preserve the pre-runtime `main` SHA.
6. Merge PR #1 using a merge commit.
7. Deploy merged `main` and repeat the success smoke path.

## Rollback

The runtime release must remain reversible through one merge revert. Database migrations must be additive; rollback must never require deleting legacy job or event history.