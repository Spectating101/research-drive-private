# Research Drive — repository authority (canonical)

**Last updated:** 2026-07-23  
**Rule:** one backend authority. Do not dual-push desk/runtime code.

## Authority table

| Concern | Canonical | Agents / Sols |
|---|---|---|
| Desk backend, craft, MCP, cluster Python, registry | **`Spectating101/research-drive-private`** (`main` + runtime branches) | Backend PRs → **private** |
| FE / RC3 / visual / synthesis UI lanes | **`Spectating101/yzu-cluster`** | FE PRs → **yzu** (unchanged) |
| Live Optiplex process cwd (`:8765`) | Checkout `research-drive-private-front-door` tracking **private/main** | Do not retarget systemd mid-flight |
| Runtime bytes (jobs DB, procured, vault staging) | `Sharpe-Renaissance-runtime-integration` via `YZU_RUNTIME_DRIVE_ROOT` | **Data bind only** — never `git clean` / reset for “sync” |
| UI static dist served by desk | `yzu-cluster-front-door-ui` → cache path in front-door env | FE product tree |

## Hard rules

1. **Canonical backend GitHub repo = `research-drive-private`.** Land craft, query, orchestrator, MCP, and `drive/config` there.
2. **`yzu-cluster` is FE/Sol product only** for overlapping work. Do **not** land desk backend commits there “for convenience.”
3. **Front-door checkout = live deploy root.** Prefer editing + pushing from that tree (or a worktree of the same remote). Keep `WorkingDirectory` stable.
4. **Runtime-integration = data/runtime bind**, not a second code authority. Sync *code files* only when hashes diverge; never wipe `data_lake/` or jobs.
5. Internal **`drive/` vs `alpha/`** layout inside one repo is fine (see `REPO_LAYOUT.md`). That is not an excuse for two GitHub remotes for the same backend.

## Local map (Optiplex)

```
research-drive-private-front-door/     # private/main — LIVE desk
Sharpe-Renaissance/                    # origin → private; yzu-fe → FE only
Sharpe-Renaissance-runtime-integration/# YZU_RUNTIME_DRIVE_ROOT (data)
yzu-cluster-front-door-ui/             # Sol visual product
```

## Prove divergence

```bash
bash drive/scripts/ops/repo_authority_check.sh
```

Fails if critical `drive/` files differ across front-door / Sharpe / runtime-integration code paths.

## Push policy (backend)

```bash
# From front-door or Sharpe after backend commits:
git push origin HEAD          # research-drive-private
# Do NOT: git push yzu-fe HEAD   for desk/backend changes
```

FE Sols keep using `yzu` / `yzu-fe` remotes for UI branches.

## See also

- [REPOSITORY_TOPOLOGY.md](./REPOSITORY_TOPOLOGY.md) — runtime contracts
- [SOL_REMOTE_HANDOFF.md](./SOL_REMOTE_HANDOFF.md) — short Sol remote rules
