# Research Drive public product slice

This `drive/` tree in `Spectating101/yzu-cluster` is the **public product and review slice** of Research Drive.

It does not own or deploy the production control plane. The full API, MCP, orchestrator, workers, scrapers, registry mutation, archive integration, and lab data paths live in the private repository `Spectating101/research-drive-private`.

See [`../docs/REPOSITORY_TOPOLOGY.md`](../docs/REPOSITORY_TOPOLOGY.md) for the canonical public/private boundary.

## Public authorities in this tree

- `src/v2/` — Research Drive React interface
- public demo and fixture configuration
- public design, product, and rendered-review material
- frontend contract tests and browser evidence

The executable public interoperability reference lives at repository root under:

- `../scripts/yzu_cluster/`
- `../tests/test_yzu_interop_*.py`

## Not authoritative here

Historical branches may contain copied or transitional Python facades under `drive/scripts/`. They are not the deployed backend and must not be treated as a second control plane.

Production source edits belong in the private repository under:

- `drive/scripts/research_data_mcp/`
- `drive/scripts/research_query_engine/`
- `drive/scripts/yzu_cluster/`
- `drive/config/`
- `kernel/`

A public facade that imports packages absent from this repository is transitional, not runnable product authority.

## Frontend entry point

```bash
npm install
npm run dev
```

The Vite frontend can use mock/demo fixtures by itself. Live Composer, Library, Resources, Synthesis execution, and registry state require the private API on port `8765`.

## Release rule

Only the cumulative public release candidate may change the product surface. Older page-specific branches and PRs are retained as history, not as parallel product authorities.
