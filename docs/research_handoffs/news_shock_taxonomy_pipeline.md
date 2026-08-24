# News Shock Taxonomy Pipeline

Drive-first dataset pipeline for a country/company investability and pattern-intelligence radar. The paper ideas are optional; the durable asset is the evidence-preserving dataset.

Drive root:

`gdrive:Machine_Archive/molina_workbench/Sharpe-Renaissance-data/news_shock_taxonomy/`

## Dataset Layers

1. Raw headline/URL layer
   - Source: GDELT DOC 2.0.
   - Script: `scripts/news_shock_taxonomy/backfill_gdelt_doc_headlines_drive.py`.
   - Output:
     - `raw/gdelt_doc_headlines/{ISO3}/{YYYY-MM}.jsonl.gz`
     - `normalized/gdelt_doc_headlines/{ISO3}/{YYYY-MM}.csv.gz`
   - Purpose: preserve the raw country-month-query evidence and normalized headline/URL index.

2. URL enrichment layer
   - Source: URLs discovered by the headline layer.
   - Script: `scripts/news_shock_taxonomy/enrich_gdelt_doc_urls_drive.py`.
   - Output:
     - `enriched/url_pages/by_country_month/{ISO3}/{YYYY-MM}.jsonl.gz`
     - `enriched/url_pages_failures/by_country_month/{ISO3}/{YYYY-MM}.jsonl.gz`
   - Purpose: fetch article pages politely and extract canonical title, OG title, meta description, H1, source language, final URL, status, hashes, and a bounded text excerpt.
   - Note: this is the permanent Drive-first version of the useful Oversight idea. The sibling `../crates/oversight` system has collectors and content extraction, but it is Redis/Docker-oriented and short-retention by default. This project uses the same `aiohttp` + `BeautifulSoup` extraction pattern while writing durable gzip JSONL to Drive.

3. AI classification layer
   - Planned output:
     - `classified/article_patterns/{ISO3}/{YYYY-MM}.jsonl.gz`
   - Classify both negative and positive patterns:
     - dysfunction: apology/clarification loops, denial/allegation cycles, corruption, policy reversal, institutional conflict, protest/unrest, FX stress
     - constructive signals: reform momentum, investment inflow, infrastructure delivery, export boom, credible policy coordination, disinflation progress, rating improvement, supply-chain relocation
   - Required fields: `pattern_type`, `domain`, `direction`, `severity`, `credibility`, `scope`, `entity`, `country`, `investment_implication`, `time_horizon`, `confidence`.

4. Panel/index layer
   - Planned output:
     - `processed/country_month_pattern_index.parquet`
     - `processed/entity_month_pattern_index.parquet`
     - `processed/source_domain_coverage.parquet`
   - Purpose: country-month, company-month, and sector-month signals for research, dashboards, and strategy exploration.

## Queued Services

`crypto-landscape-history-backfill.service`

- Current upstream job for the crypto archive.
- The news jobs wait behind it so Drive/network load stays controlled.

`news-shock-headline-backfill.service`

- Waits for the crypto historical backfill to finish successfully.
- Runs the GDELT DOC headline/URL country-month backfill.

`news-shock-url-enrichment.service`

- Waits for the headline backfill to finish successfully.
- Runs URL enrichment on the normalized headline/URL files.

## Why Oversight Is Useful Here

The sibling Oversight system already contains the right primitives:

- source registry in `../crates/oversight/config.toml`
- async news/RSS collectors
- content extraction logic
- pattern/claim-analysis concepts

But it should not be used as-is for this dataset because its existing collectors rely on Redis and short expiry windows. For this research dataset, the correct adaptation is Drive-first, resumable, partitioned, and permanent.

So the rule is:

- borrow Oversight's collector/extractor architecture
- do not depend on its Redis runtime for the archival dataset
- preserve every layer needed to audit the final signal
