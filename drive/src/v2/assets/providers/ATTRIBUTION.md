# Provider marks — provenance & license notes

Local, sanitized assets for the Resources **Source capabilities** ledger.
Runtime loads only these bundled files (no remote logo CDNs).

Marks identify third-party data routes. They do not imply endorsement or partnership.
Trademarks remain the property of their respective owners.

| File | Provider | Source | Notes |
| --- | --- | --- | --- |
| `lseg.svg` | LSEG / Refinitiv | Official site static asset `lseg.com` …/logos/bespoke/lseg-logo.svg | Trademark of London Stock Exchange Group. Identification use in faculty desk UI. |
| `wrds.png` | WRDS | Official WRDS site media `WRDS_Logo.original.png` | Wharton Research Data Services mark. Identification use. |
| `crsp.svg` | CRSP | Official `crsp.org` favicon SVG | Center for Research in Security Prices mark. |
| `moveit.png` | Progress MOVEit | Official `progress.com` favicon (largest ICO frame) | Progress / MOVEit trademark; used for CRSP MOVEit Cloud route. |
| `capital-iq.svg` | S&P Capital IQ | Compact desk mark using S&P Global red `#C8102E` + market bars | Not the official SPGI wordmark; identification-only glyph (official favicon CDN was blocked). |
| `sec-edgar.png` | SEC EDGAR | Google favicon service snapshot for `sec.gov` (bundled) | U.S. SEC identification; seal/logo rights remain with the agency. |
| `twse.png` | TWSE | Official `twse.com.tw` favicon | Taiwan Stock Exchange. |
| `mops.svg` | MOPS Taiwan | Original desk filings glyph (TWSE favicon unavailable for MOPS host) | Not an official MOPS wordmark; orange filings mark for Taiwan disclosures route. |
| `yahoo-finance.png` | Yahoo Finance | Google favicon service snapshot for `finance.yahoo.com` (bundled) | Yahoo trademark. |
| `bigquery.svg` | Google BigQuery | Official Google Cloud core product icons | Follow Google brand guidance. |
| `datacite.svg` | DataCite | Official DataCite Schwoop / Design Manual asset | DataCite trademark. |
| `huggingface.svg` | Hugging Face | Official brand asset `huggingface_logo-noborder.svg` | Hugging Face trademark. |
| `zenodo.svg` | Zenodo | `about.zenodo.org` icon | Zenodo / CERN trademark. |
| `openalex.png` | OpenAlex | GitHub org avatar snapshot (bundled) | OurResearch / OpenAlex identity. |
| `coingecko.png` | CoinGecko | Official site favicon | Prefer Brand Kit SVGs when replacing. |
| `playwright.svg` | Playwright | Official `playwright.dev` logo SVG | Microsoft Playwright mark. |
| `tavily.png` | Tavily | Official `tavily.com` favicon | Used for web-discover tooling identity. |
| `duckduckgo.svg` | DuckDuckGo | Official header logo SVG | Used for Web discover route. |
| `web-arbitrary.svg` | Web (arbitrary) | Original desk globe glyph | Neutral public-web route. |
| `vault-dictionary.svg` | Vault dictionary | Original desk icon | Internal lab route. |
| `registry-catalog.svg` | Registry catalog | Original desk icon | Internal lab route. |
| `discover-search.svg` | Discover search | Original desk icon | Internal lab route. |
| `source-probe.svg` | Source probe | Original desk icon | Internal lab route. |
| `direct-http.svg` | Direct HTTP | Original desk icon | Internal lab route. |
| `cluster-jobs.svg` | Cluster jobs | Original desk icon | Internal lab route. |
| `generic-route.svg` | Fallback | Original desk icon | Last-resort neutral glyph. |
| `google-drive.png` | Google Drive | Official Google Drive product icon (`gstatic` drive_2020q4) | Capacity · Google Drive vault. |
| `transcend-cache.svg` | Bulk cache | Original desk USB/cache glyph | Capacity · Transcend bulk cache (not a Transcend Corp wordmark). |
| `cursor.png` | Cursor | Official `cursor.com` favicon (largest ICO frame) | Capacity · Cursor Ask. |
| `query-engine.svg` | Query engine | Original desk icon | Capacity · research library API. |

## Sanitization

SVGs were stripped of scripts, external hrefs, and doctype noise before commit.
PNGs were resized locally (≈64px) for compact 18–22px UI presentation.
