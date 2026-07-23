# Repo layout (drive + alpha split)

Sharpe-Renaissance is one git repo with two products and a shared kernel.

```
Sharpe-Renaissance/
  drive/          Research Drive — procurement, catalog, vault, faculty UI
  alpha/          Alpha engine — signals, backtests, paper trading, IDN
  kernel/         Shared registry bridge + path helpers
  config/         Symlinks to drive/config and alpha/config (legacy paths)
  data_lake/      Shared runtime data (gitignored)
  backtests/      Alpha outputs
  scripts/        Root shims + lib/platform_env.sh (legacy entrypoints)
  src/v2          Symlink → drive/src/v2 (Vite alias uses drive/src)
```

## Integration surface

1. **`drive/config/research_query_registry.json`** — drive writes, alpha reads
2. **`kernel/sharpe_kernel/platform_bridge.py`** — alpha-side resolver + overlays
3. **`data_lake/`** — shared mount (Transcend + GDrive vault); not split by git

## Environment

`scripts/lib/platform_env.sh` exports:

- `SHARPE_REPO_ROOT` / `SR_DIR` — repo root
- `DRIVE_DIR`, `ALPHA_DIR`, `KERNEL_DIR`
- `PYTHONPATH` — includes kernel, drive, alpha, root

## Migration

Run once after pull:

```bash
python3 scripts/migrate_repo_split.py
```

Idempotent; creates symlinks at legacy paths.

## What stayed at root

- `.venv`, `systemd/`, `tests/`, `docs/`, `e2e/`
- Ambiguous or legacy scripts not yet classified (safe to move later)
- FinSight `src/api/` shims (point at `alpha/api/` over time)

## Next steps (optional)

- Move remaining root `scripts/*.py` into drive or alpha
- Split `pyproject.toml` extras: `[drive]` vs `[alpha]` dependencies
- Two remotes only when kernel is published as a versioned package

## GitHub remotes (authority)

See `drive/docs/REPO_AUTHORITY.md`. Backend → `research-drive-private`. FE/Sol → `yzu-cluster`.
