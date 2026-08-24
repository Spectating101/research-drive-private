# Sharpe-Renaissance documentation index

## Research desk (professor library + procurement)

| Doc | Purpose |
|-----|---------|
| **[`DESK_STATUS.md`](DESK_STATUS.md)** | **Start here** — two promises, flywheel, what to run |
| **[`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md)** | **Sole current UX authority** — current interface amendment, product grammar, surfaces, workflows, visual system, responsive rules, acceptance |
| **[`UI_IMPLEMENTATION_PROGRAM.md`](UI_IMPLEMENTATION_PROGRAM.md)** | **Frontend execution packets** — supervised Foundation + Discover sequence and review gates |
| **[`RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md)** | **Interface integration spine** — rail context, entity contracts, backend mapping |
| [`design/TOKENS.md`](design/TOKENS.md) | Visual tokens only (colors, spacing) |
| [`PROCUREMENT_PIPELINE.md`](PROCUREMENT_PIPELINE.md) | Backend modules, routes, flows |
| [`PROCUREMENT_CAPABILITY_STATUS.md`](PROCUREMENT_CAPABILITY_STATUS.md) | Release gate, proven capabilities |
| [`PROFESSOR_PROFILING.md`](PROFESSOR_PROFILING.md) | Profile tab / faculty registry |
| [`STORAGE_ARCHITECTURE.md`](STORAGE_ARCHITECTURE.md) | GDrive / USB / NVMe tiers |
| [`COLLECTION_ARCHITECTURE.md`](COLLECTION_ARCHITECTURE.md) | Partition map vs legacy folders |
| [`research_data_mcp.md`](research_data_mcp.md) | MCP tools (developer) |
| [`research_library_backend.md`](research_library_backend.md) | HTTP `/library/*` routes |
| [`research_query_engine.md`](research_query_engine.md) | Query engine backends |
| [`yzu_cluster.md`](yzu_cluster.md) | Job queue and workers |

## Trading / alpha (separate product)

| Doc | Purpose |
|-----|---------|
| [`../CLAUDE.md`](../CLAUDE.md) | Alpha pipeline, paper trading, tests |
| [`RESEARCH_INTEGRITY.md`](RESEARCH_INTEGRITY.md) | DSR, PBO, attribution |

## UI docs — do not implement from these

| Doc | Status |
|-----|--------|
| [`RESEARCH_DRIVE_UI_CANON.md`](RESEARCH_DRIVE_UI_CANON.md) | Superseded 2026-07-11 by `UI_PRODUCT_AUTHORITY.md` |
| [`RESEARCH_DRIVE_UI_CONTRACT.md`](RESEARCH_DRIVE_UI_CONTRACT.md) | Legacy `main.jsx` + Playwright only |
| [`RESEARCH_DRIVE_UI_V2.md`](RESEARCH_DRIVE_UI_V2.md) | Archived stub → canon |
| [`RESEARCH_DRIVE_UI_BLUEPRINT.md`](RESEARCH_DRIVE_UI_BLUEPRINT.md) | Archived stub → canon |

## Legacy (do not wire to production)

| Item | Note |
|------|------|
| `research_data_library.html` + `research_data_library_server.py` | Static prototype; not `create_stack()` |
| `src/main.jsx` (monolith) | Replace via `VITE_UI_V2` + `src/app/` |
| `research_handoffs/*` | Point-in-time snapshots |


## Historical UX redirects

`RESEARCH_DRIVE_UI_CANON.md`, `RESEARCH_DRIVE_UI_V2.md`, and `RESEARCH_DRIVE_UX_HANDOFF_2026-07-14.md` are retained only for old links and history. They never override `UI_PRODUCT_AUTHORITY.md`. `RESEARCH_DRIVE_UI_CONTRACT.md` is legacy-only until the legacy surface and its tests are retired.
