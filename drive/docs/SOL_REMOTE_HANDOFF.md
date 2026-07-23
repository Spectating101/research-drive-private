# Sol remote handoff (do not dual-push backend)

## Where to push

| Work | GitHub repo | Remote name (typical) |
|---|---|---|
| Desk backend / craft / MCP / cluster / registry / `drive/scripts` | `Spectating101/research-drive-private` | `origin` (or `private`) |
| FE / RC3 / synthesis UI / visual Sol lanes | `Spectating101/yzu-cluster` | `yzu` / `yzu-fe` |

## Do

- Open **backend** PRs against **`research-drive-private`**.
- Keep **FE** branches on **`yzu-cluster`** — no forced remote migration this pass.
- Treat Optiplex front-door checkout as live deploy of **private/main**.
- Treat `Sharpe-Renaissance-runtime-integration` as **data bind** (`YZU_RUNTIME_DRIVE_ROOT`), not a second code fork.

## Do not

- Dual-push the same desk/backend commit to both remotes.
- Delete or force-push Sol `agent/*` branches on `yzu-cluster`.
- `git clean` / hard-reset runtime-integration `data_lake/` or jobs to “sync code.”
- Land named-vendor product modules as desk capability (craft-generic doctrine).

## Authority doc

See [REPO_AUTHORITY.md](./REPO_AUTHORITY.md). Prove local trees with:

```bash
bash drive/scripts/ops/repo_authority_check.sh
```
