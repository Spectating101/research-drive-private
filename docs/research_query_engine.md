# Research Query Engine

Registry-driven **search lane** — query datasets that are already registered.

**Procurement lane** (collect new data): [`PROCUREMENT_PIPELINE.md`](PROCUREMENT_PIPELINE.md)  
**MCP tools:** [`research_data_mcp.md`](research_data_mcp.md)

## What it solves

The engine separates two questions:

```text
What dataset exists?
Can we analyze it now without downloading?
```

It supports local derived tables, metadata catalogues, and remote APIs behind one registry-driven interface.

## Current datasets

- `gdelt_asia_daily_country_panel`: local GDELT daily country panel CSVs.
- `gdelt_high_priority_urls`: local GDELT high-priority URL samples.
- `cross_asset_fused_primary_panel`: country-week fused news/crypto/macro panel (`fused_20260610_v2`).
- `ticker_week_country_broadcast_panel`: phase-1 ticker broadcast panel (`ticker_20260610`).
- `ticker_week_entity_market_panel`: phase-2 entity-resolved ticker panel (`ticker_20260610`).
- `collection_queue_status`: local data collection queue ops snapshot.
- `datacite_local_harvest_status`: DataCite harvest lane checkpoints.
- `external_dataset_catalog`: metadata-only external dataset catalogue seed.
- `coingecko_simple_price`: remote CoinGecko simple price API connector.

## CLI examples

List datasets:

```bash
python3 scripts/research_query_engine_cli.py datasets
```

Search external catalogue:

```bash
python3 scripts/research_query_engine_cli.py query external_dataset_catalog q=blockchain limit=20
```

Query GDELT panel:

```bash
python3 scripts/research_query_engine_cli.py query gdelt_asia_daily_country_panel country=TWN start_date=2020-01-01 end_date=2020-12-31 order_by=market_relevant_rows descending=true limit=20
```

Query fused cross-asset panel:

```bash
PYTHONPATH=scripts python3 scripts/research_query_engine_cli.py query cross_asset_fused_primary_panel country=TWN limit=10
```

Query ticker entity panel:

```bash
PYTHONPATH=scripts python3 scripts/research_query_engine_cli.py query ticker_week_entity_market_panel ticker=2330.TW limit=20
```

Check collection queue / DataCite harvest status:

```bash
PYTHONPATH=scripts python3 scripts/research_query_engine_cli.py query collection_queue_status
PYTHONPATH=scripts python3 scripts/research_query_engine_cli.py query datacite_local_harvest_status lane=y2025
```

Search high-priority GDELT URLs:

```bash
python3 scripts/research_query_engine_cli.py query gdelt_high_priority_urls q=bitcoin country=SGP limit=20
```

Query CoinGecko current prices:

```bash
python3 scripts/research_query_engine_cli.py query coingecko_simple_price ids=bitcoin,ethereum vs_currencies=usd
```

## HTTP server

Start:

```bash
python3 -m scripts.research_query_engine.server --host 127.0.0.1 --port 8765
```

Endpoints:

```text
GET /health
GET /datasets
GET /datasets/{dataset_id}
GET /query/{dataset_id}?key=value&key2=value2
```

Examples:

```text
/query/external_dataset_catalog?q=blockchain&limit=10
/query/gdelt_asia_daily_country_panel?country=TWN&start_date=2020-01-01&end_date=2020-12-31&order_by=market_relevant_rows&descending=true&limit=10
/query/gdelt_high_priority_urls?q=bitcoin&country=SGP&limit=10
/query/coingecko_simple_price?ids=bitcoin,ethereum&vs_currencies=usd
```

## MCP gateway

The same registry and engine power the MCP server (`scripts/research_data_mcp/server.py`) via `ResearchDataGateway`. MCP adds procurement job lifecycle, DataCite live search, and BigQuery guards on top of this engine. See `docs/research_data_mcp.md`.

## Design rule

Every dataset gets capability flags:

```text
access_shape
analysis_readiness
backend
capabilities
join_keys
limitations
```

This prevents the system from pretending that a metadata-only source is as usable as a local table.

## Why this is valuable

The value is not a prettier file browser. The value is a research workbench that can answer:

```text
Can this dataset be analyzed now?
If yes, query it.
If no, what ingestion/cache step is required?
How does it join with OpenSea, CoinGecko, GDELT, or market controls?
```

This is worth building because professor-facing research data usually fails in the gap between raw collection and usable empirical tables. The engine is the control layer over that gap.

## Research source planning

The virtual dataset `research_source_plan` turns a research need into candidate sources and access decisions.

Example:

```bash
python3 scripts/research_query_engine_cli.py query research_source_plan q="BYD brand awareness and marketing effectiveness" limit=20
```

Example API:

```text
/query/research_source_plan?q=BYD%20brand%20awareness%20and%20marketing%20effectiveness&limit=20
```

It returns:

```text
expanded search queries
candidate datasets/sources
promotion score/tier
query/download/scrape recommendation
whether scraping/downloading is initially needed
```

This is the core professor-facing workflow:

```text
Research question -> source plan -> query/cache/download/scrape decision -> exportable panel
```

The system should answer "what can we already measure?" before anyone designs a survey or asks for a new scrape.
