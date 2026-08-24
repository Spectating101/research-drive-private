# Research Data Hub Strategy

## Core idea

This project should not become a blind mirror of every dataset we can find.

The useful product is a research data hub that makes datasets:

- discoverable
- explainable
- queryable
- joinable
- validated
- exportable
- reproducible

The operating principle is:

```text
Do not download everything.
Classify every source by the cheapest reliable access mode.
Only archive locally when local ownership creates research value.
```

## Access modes

| Mode | Meaning | Use when |
|---|---|---|
| `download_archive` | Store full or partial source data locally/cloud archive | Source is core, volatile, cheap enough, or needs custom processing |
| `query_remote` | Query remote database/API directly | Source is huge, stable, queryable, and does not need full replication |
| `cache_derived` | Query/download only derived tables | Raw source is too large, but output panels are compact |
| `reference_only` | Store metadata, URL, access notes, schema, and examples | Dataset may be useful later but not needed now |
| `sample_probe` | Pull small samples only | Value is uncertain, expensive, or risky |
| `reject_for_now` | Do not spend work on it | Too noisy, irrelevant, illegal-risky, or impossible to validate |

## Decision rules

Use `download_archive` when:

- the source is directly central to the research question
- remote access may disappear or change
- the source has no good query API
- we need custom scoring, filtering, or enrichment
- the transformed output is much more useful than the raw input
- storage cost is acceptable

Use `query_remote` when:

- the source is already hosted in a database
- SQL/API access is stable
- full replication would be expensive or pointless
- the source is too large but queries are cheap enough
- we only need slices or aggregate panels

Use `cache_derived` when:

- repeated queries are likely
- the final research table is small
- raw data is huge
- we need reproducibility without owning the full raw dataset

Use `reference_only` when:

- the dataset is potentially useful but not yet tied to a project
- licensing or access is unclear
- we only need discovery and notes
- the source is already well preserved elsewhere

Use `sample_probe` when:

- we need to test quality before committing
- the source may be noisy
- the schema is unclear
- the API or download cost is unknown

## Current priority domain

The first serious domain should be:

```text
Crypto / NFT / market behavior + external news shock context
```

Core sources:

- OpenSea
- CoinGecko
- GDELT
- market controls such as VIX, rates, FX, stock indices, and commodities

The product should answer:

- What happened in the crypto/NFT market?
- What external news/macro/policy/geopolitical shocks were present?
- Which datasets can explain the event?
- What tables can a professor export for analysis?
- What are the limitations?

## Source routing matrix

### Discovery and dataset search layer

These are not normal datasets. They are indexes, catalogues, registries, or marketplaces that help us find datasets.

They should power the "data Sci-Hub" discovery experience.

| Source | Best mode | Reason |
|---|---|---|
| Google Dataset Search | `reference_only` + `discovery_connector` | Broad web-scale dataset discovery. It is a search layer, not a storage layer. Use it to find candidate datasets, then catalogue the result. |
| re3data | `reference_only` + `repository_registry` | Registry of research data repositories across disciplines. Use it to discover trusted discipline-specific archives. |
| Dataverse network / Harvard Dataverse | `reference_only` + `sample_probe` | Strong for academic/citable datasets. Download only datasets tied to a project. |
| Zenodo | `reference_only` + `sample_probe` | Good for research deposits and DOI-linked data. Broad but uneven; catalogue metadata first. |
| Figshare | `reference_only` + `sample_probe` | Similar to Zenodo; useful for article-linked datasets and institutional deposits. |
| Dryad | `reference_only` + `sample_probe` | Stronger in biology/ecology/life sciences; likely future expansion rather than first crypto use case. |
| OSF | `reference_only` + `sample_probe` | More project/lifecycle oriented. Useful for research artifacts, not always clean datasets. |
| Kaggle Datasets | `sample_probe` + selective `download_archive` | Good for exploratory datasets and ML workflows, but quality/provenance varies heavily. |
| Hugging Face Datasets | `query_remote` + `sample_probe` + selective `download_archive` | Strong for ML/NLP/audio/vision datasets. Treat as future ML/data source layer. |
| OpenML | `query_remote` + `sample_probe` | Useful for benchmark/ML datasets, less central to professor's current crypto/data work. |
| Papers With Code datasets | `reference_only` | Useful for ML benchmark discovery. Usually points elsewhere for actual access. |
| DataHub / Awesome public datasets lists | `reference_only` | Useful curated lists, but metadata quality is uneven. |
| OpenAlex / Crossref / Semantic Scholar | `query_remote` + `cache_derived` | Not dataset repositories exactly, but useful to connect datasets to papers, authors, fields, and citations. |

Discovery-layer output should be:

```text
candidate dataset cards
source/repository metadata
access notes
license notes
schema if available
size estimate
download/query/API route
research relevance score
decision: ignore / watch / sample / download / query
```

The important product idea:

```text
Google Dataset Search finds datasets.
re3data finds repositories.
Dataverse/Zenodo/Kaggle/HuggingFace host datasets.
Our system decides whether a dataset is worth using, how to access it, and how it joins our research tables.
```

### Already-owned or active project sources

| Source | Best mode | Reason |
|---|---|---|
| OpenSea scraping/database | `download_archive` + `cache_derived` | Core professor source. Needs local ownership, entity logic, collection-level tables, and reproducibility. |
| CoinGecko pipeline | `query_remote` + `cache_derived` | API/source is live. We need regular snapshots and derived price/volume panels, not every possible raw response forever. |
| GDELT GKG Asia shock dataset | `download_archive` + `cache_derived` | Downloading is justified because we apply custom Asia filtering, taxonomy scoring, and daily-country panel generation. |
| Spectator/upwork/104 scraping data | `download_archive` + `reference_only` | Valuable as historical scraping examples and labor-market datasets, but not central to crypto unless a separate labor-market project exists. |

### Crypto and blockchain sources

| Source | Best mode | Reason |
|---|---|---|
| Etherscan | `query_remote` + `sample_probe` | Good validation/API source. Bad as a full historical bulk source unless paid and scoped. |
| Ethereum USDT transfers via BigQuery public/blockchain tables | `query_remote` + `cache_derived` | Better than scraping Etherscan. Use SQL for panels and export monthly Parquet only if needed. |
| Ethereum RPC logs | `query_remote` + `cache_derived` | Best for live updater after historical table exists. Not ideal for full historical backfill. |
| Blockscout | `query_remote` + `sample_probe` | Useful for validation and explorer comparisons, not primary full archive. |
| NFT collection metadata | `download_archive` if from our scraping, otherwise `query_remote` | Core if tied to OpenSea research; otherwise cache derived metadata only. |
| Exchange labels / wallet entity labels | `sample_probe` first | Potentially valuable but hard, incomplete, often proprietary. Do not promise before scope is confirmed. |

### News, macro, and event context

| Source | Best mode | Reason |
|---|---|---|
| GDELT GKG | `download_archive` + `cache_derived` | Good for custom news shock panels. Already underway. |
| GDELT DOC/API | `query_remote` | Good for ad-hoc article search and recent examples. Not a replacement for our local scored panels. |
| Google Trends | `query_remote` + `cache_derived` | Useful attention proxy. Query slices and cache panels. |
| Wikipedia pageviews | `query_remote` + `cache_derived` | Useful attention/event proxy. Compact derived tables are enough. |
| Event registries / current events timelines | `reference_only` + `sample_probe` | Useful for validation labels, not primary quantitative data. |

### Market and economic controls

| Source | Best mode | Reason |
|---|---|---|
| FRED | `query_remote` + `cache_derived` | Stable API, compact time series. No need to mirror everything. |
| Yahoo Finance/Stooq/market data alternatives | `query_remote` + `cache_derived` | Good for quick controls. Cache only selected tickers/assets. |
| IMF / World Bank / OECD | `query_remote` + `cache_derived` | Stable public institutional data. Use selected indicators. |
| VIX, DXY, rates, gold, oil, equity indices | `cache_derived` | Small, high-value controls for crypto/event studies. |
| Refinitiv/Bloomberg/WRDS/CRSP | `reference_only` unless licensed | High value but access-controlled. Catalogue access notes, do not build around unauthorized copies. |

### General research repositories

| Source | Best mode | Reason |
|---|---|---|
| Harvard Dataverse / Dataverse repositories | `reference_only` + `sample_probe` | Good citable datasets. Download only project-relevant datasets. |
| Zenodo | `reference_only` + `sample_probe` | Broad research deposits. Download selected records only. |
| Figshare / Dryad / OSF | `reference_only` + `sample_probe` | Useful discovery/preservation sources, not bulk mirrors. |
| Hugging Face Datasets | `query_remote` + `sample_probe` + selective `download_archive` | Excellent for ML/NLP datasets. Download only selected datasets with clear use. |
| Kaggle | `sample_probe` + selective `download_archive` | Useful but quality varies. Treat as exploratory unless provenance is strong. |
| OpenML | `query_remote` + `sample_probe` | Good ML benchmark source. Not central unless ML benchmark work starts. |

### Cloud public data

| Source | Best mode | Reason |
|---|---|---|
| BigQuery public datasets | `query_remote` + `cache_derived` | Public datasets are already stored in BigQuery. Query/export selected outputs rather than mirror full tables. |
| AWS Open Data Registry | `query_remote` or `sample_probe` | Many datasets are directly accessible through S3/HTTPS. Download only if project-critical. |
| Google Cloud public data / Earth Engine | `query_remote` + `cache_derived` | Best for geospatial/environmental work. Avoid full replication. |

### Government and institutional data

| Source | Best mode | Reason |
|---|---|---|
| data.gov / national open data portals | `reference_only` + `sample_probe` | Huge variety. Catalogue, then download only relevant datasets. |
| SEC EDGAR | `query_remote` + `cache_derived` | Good for filings and corporate events. Build selected derived tables. |
| OpenAlex / Crossref / Semantic Scholar | `query_remote` + `cache_derived` | Useful for literature metadata and citation graphs. Query and cache selected views. |
| ORCID / ROR | `query_remote` + `cache_derived` | Useful metadata registries. No need to mirror everything. |

## Website product model

The website should expose four asset types.

### 1. Dataset cards

Each dataset card should include:

- name
- source
- access mode
- status
- coverage
- schema
- available tables
- update frequency
- storage location
- query examples
- known limitations
- owner/contact
- related datasets

### 2. Query workspace

The query layer should support:

- local DuckDB/Parquet tables
- remote API connectors
- BigQuery SQL templates
- cached result tables
- CSV/Parquet export
- saved query recipes

### 3. Validation reports

Each important dataset needs:

- coverage report
- row-count report
- schema report
- source/provenance report
- sample inspection
- known false positives
- known missing periods
- recommended and not-recommended uses

### 4. AI data navigator

The AI assistant should not pretend to know the raw data.

It should answer from:

- dataset cards
- schemas
- manifests
- validation reports
- query results
- source notes

It should help with:

- finding datasets
- explaining variables
- suggesting joins
- writing SQL
- generating export panels
- warning about limitations

## First build sequence

### Phase 1: Catalogue and routing

Create a registry table:

```text
datasets
dataset_sources
dataset_tables
dataset_access_modes
dataset_links
dataset_status
```

Minimum fields:

```text
dataset_id
name
domain
source_type
access_mode
source_url
local_path
remote_query_surface
coverage_start
coverage_end
refresh_frequency
status
owner
notes
known_limitations
```

### Phase 2: Local research tables

Prioritize:

- GDELT daily country panel
- GDELT high-priority URL index
- CoinGecko price/volume panels
- OpenSea collection/day or sale/event tables

### Phase 3: Connectors

Build connectors for:

- local DuckDB
- local Parquet
- Google Drive archive paths
- CoinGecko API
- BigQuery SQL templates
- GDELT DOC/API
- Google Dataset Search-style metadata ingestion
- re3data repository registry ingestion
- Dataverse API / metadata ingestion
- Zenodo API / metadata ingestion
- Hugging Face dataset metadata ingestion
- Kaggle metadata/search ingestion where access is available

### Phase 4: Professor-facing interface

Initial pages:

- dataset library
- dataset detail page
- coverage report
- query/export page
- pipeline status page
- AI helper panel

## Immediate recommendations

Do now:

- finish GDELT backfill
- package GDELT into unified Parquet/DuckDB tables
- catalogue OpenSea, CoinGecko, and GDELT as the first three first-class datasets
- build dataset cards and validation reports
- implement query/export for local panels

Do later:

- BigQuery USDT prototype
- Google Trends/Wikipedia attention proxies
- FRED/VIX/FX/rates controls
- Dataverse/Hugging Face/Kaggle discovery connectors
- Google Dataset Search / re3data-style dataset discovery index
- paper-to-dataset linking through OpenAlex/Crossref/Semantic Scholar

Do not do yet:

- mirror arbitrary Kaggle/Hugging Face datasets
- scrape Etherscan pages as the primary architecture
- promise Refinitiv/Bloomberg replacement
- build a generic all-internet dataset crawler
- store huge raw files without a research use case

## Short positioning statement

```text
This is not a pirate mirror and not a generic file drive.
It is a research data hub for messy, live, scraped, API, and public datasets.
The value is turning sources into documented, validated, queryable research tables.
```

## Source references

- Google BigQuery Public Datasets: https://docs.cloud.google.com/bigquery/public-data
- AWS Open Data Registry: https://aws.amazon.com/en/publicdatasets/
- Google Dataset Search: https://datasetsearch.research.google.com/
- re3data: https://www.re3data.org/
- Harvard Dataverse: https://dataverse.harvard.edu/
- Hugging Face Datasets: https://huggingface.co/datasets
- Kaggle Datasets: https://www.kaggle.com/datasets
- Zenodo: https://zenodo.org/
- GDELT GKG files: https://data.gdeltproject.org/gkg/index.html
- GDELT DOC 2.0 API notes: https://blog.gdeltproject.org/gdelt-doc-2-0-api-debuts/
