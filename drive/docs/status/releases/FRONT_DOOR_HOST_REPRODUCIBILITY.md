# Optiplex front-door host layout (reproducibility)

**Audience:** operators redeploying the Tailscale-internal Research Drive front door  
**Private baseline this document freezes against:** post-RC2 host repairs that previously lived only as manual rituals

## What must be true for a clean host to match the accepted desk

1. Front door Python provides an importable `cursor_sdk` (`YZU_PYTHON_BIN`).
2. `CURSOR_API_KEY` is set **and** `cursor_composer_available()` can import `cursor_sdk` (health is not key-only).
3. When the worker/controller promote into a separate runtime-integration store, the front-door checkout binds that store via `YZU_RUNTIME_DRIVE_ROOT`.
4. Newly collected procured assets have local bytes at the registry `local_path` (hydrate from acquisition staging when needed).
5. Worker-control `:8780` stays Tailscale-bound; the Windows worker token matches the controller token.

## Environment (outside git)

Copy `drive/config/optiplex-front-door.env.example` to `~/.config/research-drive/front-door.env` (`chmod 600`).

Required for Composer + authority linking:

```bash
YZU_PYTHON_BIN=/absolute/path/to/venv/bin/python   # must import cursor_sdk
YZU_RUNTIME_DRIVE_ROOT=/absolute/path/to/.../Sharpe-Renaissance-runtime-integration/drive
SHARPE_REGISTRY_PATH=drive/config/research_query_registry.json
```

Never commit real tokens. Keep `YZU_DESK_ACCESS_TOKEN`, `CURSOR_API_KEY`, and `YZU_WORKER_CONTROL_TOKEN` host-local.

## Deterministic linking

`drive/scripts/research_query_engine/link_front_door_host_config.sh` always links `config/*.json` → `drive/config/*.json`.

When `YZU_RUNTIME_DRIVE_ROOT` is set it also binds:

| Front-door path | Runtime authority |
|---|---|
| `drive/config/research_query_registry.json` | `$YZU_RUNTIME_DRIVE_ROOT/config/research_query_registry.json` |
| `data_lake/procured` | `$YZU_RUNTIME_DRIVE_ROOT/data_lake/procured` |
| `data_lake/yzu_cluster` | `$YZU_RUNTIME_DRIVE_ROOT/data_lake/yzu_cluster` |

The front-door launcher already invokes this script before start. A stale private registry copy without the runtime bind is what produced `receipt_only` / query `not_found` after a successful Windows collect.

## Staging → procured hydration

If archive+registry succeeded but `GET /query/<dataset_id>` returns no files:

```bash
export PYTHONPATH="$PWD:$PWD/kernel:$PWD/drive"
python drive/scripts/research_query_engine/hydrate_procured_from_acquisition.py \
  --repo-root "$YZU_RUNTIME_DRIVE_ROOT" \
  --job-id <job_id>
```

`--repo-root` must be the store that owns `data_lake/yzu_cluster/acquisitions/<job_id>/` (typically `$YZU_RUNTIME_DRIVE_ROOT`). The helper refuses to overwrite mismatched existing files.

## Queue hygiene (optional)

Denied job types and fixture stuck runs can be drained without touching `:8780`:

```bash
python -m scripts.yzu_cluster.triage_pending_jobs --cancel-noise --dry-run
python -m scripts.yzu_cluster.triage_pending_jobs --cancel-noise
```

## Smoke after clean deploy

```text
GET /health                 → composer_configured true only if cursor_sdk imports
GET /library/catalog        → 200
GET /datasets/<registered>  → backend not receipt_only after runtime bind
GET /query/<registered>?limit=2 → rows when local_path hydrated
:8780                       → still Tailscale-only
```
