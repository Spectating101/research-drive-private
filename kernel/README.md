# Sharpe kernel

Thin shared contract between **drive** (procurement) and **alpha** (research engine).

## Modules

| Module | Role |
|--------|------|
| `sharpe_kernel/paths.py` | Repo root, data lake, registry path resolution |
| `sharpe_kernel/platform_bridge.py` | Registry → parquet resolver; news overlays for alpha |

## Rules

- **Drive** writes registry rows and vault paths.
- **Alpha** reads panels through `platform_bridge` only.
- No imports from `drive.scripts` or `alpha.scripts` inside kernel.

PYTHONPATH must include `kernel/` (set automatically by `scripts/lib/platform_env.sh`).
