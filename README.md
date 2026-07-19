# YZU Cluster — Research Drive

Public GitHub home for the **YZU Research Drive** product: researcher-facing UI, design canon, visual-review evidence, interoperability contracts, and a dependency-free executable reference runtime.

This repository is **not the deployed lab control plane**. The production API, MCP, orchestrator, workers, scrapers, registry writes, host configuration, and `data_lake/` live in the private repository `Spectating101/research-drive-private`.

Public and private are not fake versus real:

- **Public** publishes the interface and executable behavioral contract.
- **Private** adopts that contract inside the real Research Drive control plane.
- **Live hosts** prove the private implementation on Optiplex, Windows workers, and GDrive.

Read [`docs/REPOSITORY_TOPOLOGY.md`](docs/REPOSITORY_TOPOLOGY.md) before changing repository boundaries or starting a new release branch.

## What this is

| Promise | What professors get |
|---------|---------------------|
| **Organized lab data** | Library catalog mapped to vault partitions |
| **Procurement assistant** | Composer + MCP — search, query, collect, register |
| **Research-asset construction** | Synthesis turns research intent into validated, reusable assets |

**Not** alpha trading and not SolarPunk — those are separate products.

## Public authorities

| Path | Role |
|---|---|
| `drive/src/v2/` | Research Drive interface |
| `e2e/` | Browser and rendered-state contracts |
| `docs/product/` | Public product and interoperability contracts |
| `scripts/yzu_cluster/` | Executable dependency-free reference runtime |
| `tests/test_yzu_interop_*.py` | Reference runtime behavioral tests |

The public reference runtime is intentionally framework-neutral. It does not contain the private host, archive, credential, or production-data environment.

## Live surfaces

| Surface | URL |
|---------|-----|
| **GitHub Pages** — static UI + demo seed | https://spectating101.github.io/yzu-cluster/ |
| **Full desk** — private API + chat + workers | Run from the private Research Drive checkout |

Static Pages shows the v2 shell and offline/demo data. Composer chat and live registry require the private API.

## Run locally

### Frontend and public fixtures

```bash
npm install
npm run dev
# proxy → :8765 when a private API is available
```

### Full desk

From the private `research-drive-private`/Sharpe-Renaissance checkout:

```bash
bash drive/scripts/run_yzu_cluster.sh
# UI → http://127.0.0.1:5178
# API → http://127.0.0.1:8765
```

Do not infer that a Python facade in this public history is the deployed backend. A public module that imports absent private packages is transitional and not a runnable authority.

## Validation

```bash
npm run build
npm run test:runtime-contract
python -m unittest discover -s tests -p "test_yzu_interop_*.py" -v
```

Rendered review uses the Playwright suites under `e2e/` and, when the private desk is available, the live integration capture scripts.

## Canon docs

- [`docs/REPOSITORY_TOPOLOGY.md`](docs/REPOSITORY_TOPOLOGY.md) — repository and release authority
- [`docs/UI_PRODUCT_AUTHORITY.md`](docs/UI_PRODUCT_AUTHORITY.md) — interface authority
- [`docs/RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](docs/RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md) — Detail | Ask rail
- [`docs/product/SYNTHESIS_S04_PRODUCT_SPEC.md`](docs/product/SYNTHESIS_S04_PRODUCT_SPEC.md) — Synthesis product model
- [`docs/product/CLUSTER_RUNTIME_INTEROP_CONTRACT.md`](docs/product/CLUSTER_RUNTIME_INTEROP_CONTRACT.md) — public/private runtime contract

## Publishing discipline

The public repository may receive UI, public docs, fixtures, screenshots, E2E coverage, and reference-contract code. It must not receive credentials, host inventory, databases, local datasets, GDrive configuration, or the production control plane.

Historical and superseded PR branches remain available for archaeology, but only one cumulative public release PR should remain active.

## Share line

> Research Drive is a lab data desk for YZU: organized vault catalog, live query registry, and a Composer-backed procurement loop — search what we have, collect what we don't, construct defensible research assets, and register them for next time.
