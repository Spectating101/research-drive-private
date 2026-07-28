# Research Drive (procurement)

Acquire, catalog, vault, and serve datasets for the professor desk.

## Owns

- `drive/scripts/yzu_cluster/` — job queue, Windows fleet, worker
- `drive/scripts/research_data_mcp/` — MCP tools, Composer chat, flywheel
- `drive/scripts/research_query_engine/` — HTTP API `:8765`
- `drive/src/v2/` — Research Drive React UI (Vite `:5178`)
- `drive/config/` — registry (write), collection queue, GDrive partitions, GDELT fleet
- `drive/docs/` — **canonical desk documentation** (databank state, activation backlog)

## Documentation

| Doc | Role |
|-----|------|
| [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) | **Start here** — product direction, truth rules, and authority map |
| [`docs/DOCUMENTATION_GUIDE.md`](docs/DOCUMENTATION_GUIDE.md) | Documentation classes and cleanup rules |
| [`docs/DATABANK_STATE.md`](docs/DATABANK_STATE.md) | **What we have** — equal-weight inventory, paths, coverage |
| [`docs/DESK_ACTIVATION.md`](docs/DESK_ACTIVATION.md) | Historical activation backlog; verify against live state before acting |
| `docs/status/generated/platform_progress.json` | Machine-readable progress + incomplete items |

Refresh: `python3 drive/scripts/sync_drive_platform_state.py`

API: `GET /library/platform/state` · `GET /health` (cluster block includes doc pointers)

## Entry points

```bash
bash drive/scripts/run_yzu_cluster.sh          # API + UI + worker
bash drive/scripts/run_research_query_engine.sh
bash drive/scripts/run_research_data_mcp.sh
python3 drive/scripts/sync_drive_platform_state.py
python3 drive/scripts/run_data_collection_queue.py
```

Legacy paths under `scripts/` are symlinks into this tree.

## Contract with Alpha

- **Writes** `drive/config/research_query_registry.json` (symlinked at `config/`)
- **Writes** `data_lake/collection/` and bulk panels on Transcend
- Alpha **reads** registry only via `kernel/sharpe_kernel/platform_bridge.py`

See `../REPO_LAYOUT.md`.
