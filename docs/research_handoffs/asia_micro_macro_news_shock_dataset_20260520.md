# Asia Micro-Macro News Shock Dataset

Date: 2026-05-20

This pivots the news-shock project away from US-first equity infrastructure and toward Asia-first investability research.

## Core Direction

The dataset should not mean "business news only." It should cover all public news and official publications that can plausibly affect country, sector, FX, equity, credit, or capital-flow risk.

Relevant shock families:

1. Macro policy: central-bank communication, inflation, fiscal policy, tax, subsidy, debt, capital controls.
2. Trade and supply chain: tariffs, export controls, sanctions, reshoring, port disruption, logistics stress.
3. Governance and corruption: corruption probes, legal/regulatory failures, institutional conflict, policy reversals.
4. Political instability: elections, protests, coups, legislative deadlock, resignation/dismissal cycles.
5. Geopolitical/security: war, border conflict, terrorism, sanctions, military escalation.
6. Health/disaster/environment: pandemics, epidemics, earthquakes, floods, energy shocks, climate disruption.
7. Financial stress: FX pressure, bank stress, debt/default language, reserves, rate shocks.
8. Corporate micro shocks: guidance, accounting issues, lawsuits, governance, shutdowns, supply-chain exposure.

Excluded by default:

1. Celebrity and entertainment.
2. Sports.
3. Pure lifestyle articles.
4. Generic market commentary without country/entity/event content.

## Country Focus

Primary Asia market universe:

- Indonesia
- Taiwan
- South Korea
- Japan
- China
- Hong Kong
- Singapore
- Malaysia
- Thailand
- Philippines
- Vietnam
- India
- Australia

Config:

`config/news_shock_asia_universe.json`

## Source Strategy

Use three layers.

### Layer 1: Broad News Backbone

Source: GDELT GKG bulk files.

Why:

- It is broad, multilingual/translated, and global.
- It includes themes, locations, organizations, persons, URLs, source domains, and tone fields.
- Bulk files are better for large-scale collection than the DOC API, which already rate-limited the earlier pilot.

Output target:

```text
data_lake/news_shock_taxonomy/raw/gdelt_gkg_asia_bulk/
data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/
```

### Layer 2: Official Publications

This should be added after the GDELT bulk pilot:

- Taiwan: MOPS/TWSE material information, monthly revenue, financial reports.
- Korea: OpenDART disclosures.
- Singapore: SGX company announcements.
- Hong Kong: HKEXnews listed-company publications.
- Indonesia: IDX disclosures and OJK/BI policy publications where accessible.
- Macro: central banks, finance ministries, statistics agencies, trade ministries.

Why:

- Cleaner timing than media articles.
- Better for event studies.
- Better legal/compliance footing.

### Layer 3: Enriched Article/Page Text

Only enrich URLs after the headline/index layer proves useful.

Fields:

```text
document_id
published_at
source
source_domain
country_iso3
country_name
matched_country_terms
source_type
themes
shock_hints
tone_avg
url
title_or_names
organizations
persons
locations
market_mapping
quality_flags
```

## Research / Investment Use

This dataset should answer:

1. Which political/macro/publication shocks lead equity drawdowns or FX stress in Asia?
2. Which countries show repeated policy confusion, corruption, protest, or institutional conflict cycles?
3. Which positive signals matter: reform momentum, credible policy coordination, investment inflow, export boom?
4. Which shocks are priced immediately and which drift over one week, one month, or one quarter?
5. Which country/sector pairs are fragile to geopolitical, trade, and governance shock clusters?

## Implementation Rule

Do not run a huge full backfill until the pilot passes validation.

Pilot sequence:

1. GDELT GKG Asia bulk smoke test: 1-2 recent files.
2. Validate country/theme filtering.
3. Run a 7-day local-only batch.
4. Build daily/country shock counts and tone summaries.
5. Compare with Asia ETF/FX returns already in `data_lake/markets`.
6. Only then schedule full historical backfill and Drive sync.

## Why This Is Better Than More Price Data

Price data is already available and mostly commoditized. The edge, if any, comes from mapping narrative/event formation into market behavior:

```text
news/publication shock -> country/sector/entity mapping -> market response window -> repeatable signal
```

That is the actual durable research asset.

## 2026-05-20 Pilot Result

The first 24-hour GDELT GKG pilot is usable as a broad radar layer, but not as a final signal by itself.

Run:

```text
asia_gkg_24h_pilot_20260520T155311Z
```

Raw GKG filter output:

- 96 GDELT 15-minute GKG files processed.
- 129,516 raw GKG rows scanned.
- 31,818 Asia/shock-filtered rows kept.
- 23,202 canonical URLs after URL normalization.
- Normalized CSV: `data_lake/news_shock_taxonomy/normalized/gdelt_gkg_asia_bulk/asia_gkg_24h_pilot_20260520T155311Z/asia_gkg_filtered.csv.gz`

Scored layer added:

```text
scripts/news_shock_taxonomy/score_gdelt_gkg_asia.py
```

Outputs:

```text
data_lake/news_shock_taxonomy/processed/asia_gkg_24h_pilot_20260520T155311Z/asia_gkg_scored.csv.gz
data_lake/news_shock_taxonomy/processed/asia_gkg_24h_pilot_20260520T155311Z/url_enrichment_queue.csv.gz
data_lake/news_shock_taxonomy/processed/asia_gkg_24h_pilot_20260520T155311Z/daily_country_shock_panel.csv
data_lake/news_shock_taxonomy/processed/asia_gkg_24h_pilot_20260520T155311Z/scoring_summary.json
```

Scoring summary:

- 7,862 rows have high primary-country confidence.
- 4,234 rows have weak country confidence and should not be used without enrichment/classification.
- 535 rows are high market-relevance by URL/entity evidence.
- 66 rows are strict high-priority URL enrichment candidates.
- 2,350 rows are medium-priority keepers.
- 5,109 rows are broad context keepers.
- 19,096 rows are low-priority archive.

Local URL enrichment pilot added:

```text
scripts/news_shock_taxonomy/enrich_gdelt_gkg_urls_local.py
```

High-priority title/snippet enrichment result:

- 66 URLs selected.
- 60 downloaded successfully.
- 5 returned HTTP errors, mostly site blocking.
- 1 fetch error.

Output:

```text
data_lake/news_shock_taxonomy/processed/asia_gkg_24h_pilot_20260520T155311Z/url_enrichment_enrich_high_priority.csv.gz
data_lake/news_shock_taxonomy/processed/asia_gkg_24h_pilot_20260520T155311Z/url_enrichment_enrich_high_priority.jsonl.gz
```

The enriched titles show real usable items: rupee record low, India treasury-bill yields, Korean foreign-investor stock outflows, Samsung chip disruption risk, Singapore trading offences, PSEi selloff, and RBA property-market cooling. This confirms the architecture:

```text
GDELT GKG broad radar -> score/triage -> title/snippet enrichment -> later LLM/event classification
```

## Active 7-Day Pilot

Started after the 24-hour pilot passed validation:

```text
scripts/run_news_shock_gkg_7d_pipeline.sh
```

Active run:

```text
asia_gkg_7d_pilot_20260520T162450Z
```

Log:

```text
logs/news_shock_taxonomy/asia_gkg_7d_pilot_20260520T162450Z.pipeline.log
```

The script fetches 7 days of GDELT GKG, scores the normalized file, then enriches up to 500 strict high-priority URLs.
