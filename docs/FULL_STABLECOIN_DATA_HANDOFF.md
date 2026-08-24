# Full Stablecoin Research Data Handoff

**Audience:** ChatGPT / independent auditor reconstructing longitudinal security & community-growth measures for Professor De-Rong Kong (Yuan Ze University).  
**Frozen professor package build:** `20260707`  
**Audit generated:** 2026-07-12 / 2026-07-13  
**Stance of this document:** descriptive and factual. It does **not** defend `attention_proxy_index`. It does **not** prescribe a new research question. It does **not** rebuild or delete data.

**Repo root:** `Sharpe-Renaissance/`  
**Machine-readable companions:** `docs/status/generated/stablecoin_full_audit/*.csv|json`

---

## 0. Original research need vs what public data provides

### What Professor Kong wanted (longitudinal)

1. **Stablecoin security / audit history over time**
2. **Stablecoin community growth over time** (especially X/Twitter follower growth)

### What is consistently unavailable for the 71-coin Skynet leaderboard universe

| Desired series | Availability in this substrate |
|----------------|--------------------------------|
| Historical CertiK / Skynet security-score panel (weekly/monthly 2021–2026) | **Not found.** Harvests are point-in-time API dumps (~2026-06). `code_security_score` / `skynet_score` are snapshots. |
| Lifetime official X/Twitter follower history | **Not available** from public X API. Skynet visual harvest provides only ~**2026-05-08 → 2026-06-22** daily followers for ~68 coins. |
| Skynet `holdersCountHistory` arrays | Present in schema but **empty** in harvested JSON. |
| Rich dated audit reports per coin | Skynet `project.audits` mostly empty stubs (13 entries across 9 coins; weak fields). |

### What was shipped to the professor instead

`professor_simple/` export: cross-section + weekly panel with:

- `code_security_score` = engineered **snapshot** control (repeated on every week)
- `attention_proxy_index` = rename of `community_growth_index` = within-entity z-score average of Trends / Reddit / sparse Twitter WoW / sparse holder WoW

Known engineering issue (confirmed): `_z_scores` maps zero-stdev series to `0.0`, so **21 coins with constant-zero Trends** still show dense non-null attention (often exactly 0). See `professor_simple/QA_ATTENTION_PROXY_ZEROS.md`.

---

## 1. Full data inventory (summary)

Complete file-level inventory: `docs/status/generated/stablecoin_full_audit/inventory_datasets.csv` (also `.json`).

### 1.1 CertiK / Skynet raw harvests

| Path | Collection | Contents | Notes |
|------|------------|----------|-------|
| `stablecoin_skynet/data/harvest_20260622T132438Z/` | 2026-06-22 | **Canonical** 71 project JSON | Used by research build (`lineage.json`) |
| `harvest_20260622T132030Z`, `…T132233Z`, `harvest_20260623T173150Z`, `…T173915Z` | Jun 22–23 2026 | Alternate/partial harvests | Opportunity: compare scores across runs for mini snapshot panel |
| `visual_harvest_20260622T141625Z/`, `screenshots_*` | 2026-06-22 | Visual / Recharts extracts | Source of short Twitter follower series |

**Per-project JSON shape (canonical):** `slug`, `harvested_at`, `endpoints{info, governance_strength, milestones, pulses, website_scan, …}`, `token_extras`.

**Endpoint presence (71 coins):** see `skynet_endpoint_presence.csv`.

Notable endpoint coverage:

| Endpoint | Coins with data |
|----------|----------------:|
| info, website_scan, milestones, vote_results, pulses | 71 |
| governance_strength | 64 |
| price_bars_1y | 52 |
| exchange_listing | 40 |
| funding_history / summary / price (skynet scores) | 9 |
| risky_smart_contracts | 3 |
| security_incidents | 1 (`alchemix-usd`) |

Extracted tables:

- `skynet_audits_extracted.csv` — 13 stub audit rows
- `skynet_scores_snapshot.csv` — 9 coins with score components
- `skynet_governance_flags_extracted.csv` — chain-level flags
- `skynet_milestones_extracted.csv` — **277** timed milestone events
- `skynet_milestones_security_keyword.csv` — 11 keyword-flagged (audit/license/security language; keyword heuristic only)
- `skynet_security_incidents_extracted.csv` — sparse

### 1.2 Community / attention raw + intermediate

Root: `stablecoin_skynet/data/community/` (~8.7 MB)

| File / dir | Source | Frequency | Coverage (approx) | Raw/xform |
|------------|--------|-----------|-------------------|-----------|
| `registry.json` | manual+Skynet | n/a | 71 coins; Trends queries, Reddit queries, Twitter handles | config |
| `accounts.csv` / `accounts.json` | Skynet | cross-section | Twitter handles + current followers | xform |
| `follower_growth_panel.csv` | Skynet visual Recharts | daily | 68 slugs; **2026-05-08 → 2026-06-22**; 2326 rows | raw-ish |
| `holder_growth_panel.csv` | Skynet | daily | 61 slugs; **2026-05-22 → 2026-06-22**; 1871 rows | raw-ish |
| `pulses.jsonl` | Skynet pulses | event | curated news-like items | raw |
| `google_trends/` + `google_trends_panel.csv` | Google Trends (pytrends) | weekly native | 18340 rows; query per slug | raw+panel |
| `reddit/` + `reddit_monthly_panel.csv` | PullPush | **monthly** | 683 rows | raw+panel |
| `coingecko/` | CoinGecko | snapshot | community scores / social counts | raw |
| `community_attention_panel.csv` | merge builder | daily-ish | Trends + Reddit + Skynet series merged | transformed |
| `mendeley_raw/` | optional external | — | influencer DB placeholder | mostly unused |
| `METHODOLOGY.md`, `PROFESSOR_HANDOFF.md` | docs | — | early framing of proxy strategy | doc |

Collectors:

- `stablecoin_skynet/export_community.py`
- `stablecoin_skynet/community/harvest_google_trends.py`
- `stablecoin_skynet/community/harvest_reddit_attention.py`
- `stablecoin_skynet/community/harvest_coingecko_snapshot.py`
- `stablecoin_skynet/community/build_proxy_panel.py`
- `stablecoin_skynet/community/registry.py`

### 1.3 DeFiLlama / peg / supply

| Path | Notes |
|------|-------|
| `stablecoin_skynet/data/derived/defillama/` | ~**211 MB** API cache (too large for default zip; factors in package include rolled panels) |
| `config/stablecoin_defillama_map.json` | entity map overrides |
| Package factors: `adoption_panel_daily.csv`, `adoption_panel_weekly.csv`, `trust_stress_panel_*.csv` | supply + peg rolled |

Builder: `stablecoin_skynet/defillama_panel.py`

### 1.4 Wikipedia

| Path | Notes |
|------|-------|
| `config/stablecoin_wikipedia_articles.json` | explicit entity→article map (subset) |
| `stablecoin_skynet/data/derived/wikipedia/` | pageview cache |
| Package: `factors/wikipedia_panel_daily.csv`, `wikipedia_panel_weekly.csv` | ~20% of professor weekly rows non-null |

Builder: `wikipedia_panel.py`, `wikipedia_probe.py`

### 1.5 GDELT / news

| Path | Notes |
|------|-------|
| `lineage.json` → `gdelt_overlay_root` under `data_lake/news_shock_taxonomy/derived/gdelt_crypto_overlay` | Asia-biased upstream collection |
| `config/stablecoin_gdelt_aliases.json` | phrase aliases |
| Package factors: `gdelt_entity_panel_*`, `gdelt_sector_panel_*` | entity + sector |
| `stablecoin_skynet/data/derived/gdelt_entity_panel_daily.csv` | derived copy |

Builder: `gdelt_panel.py`

### 1.6 GitHub

| Path | Notes |
|------|-------|
| `config/stablecoin_github_repos.json` | sparse map |
| `stablecoin_skynet/data/derived/github/` | activity cache |
| Package: `factors/github_security_activity_weekly.csv`, `reference/github_repo_map.csv` | few entities |

Builder: `github_activity_panel.py`; script `harvest_stablecoin_github_activity.py`

### 1.7 Incidents / sector shocks / security events (curated)

| Path | Role |
|------|------|
| `config/stablecoin_curated_incidents.json` | hand-curated depegs/incidents |
| `config/stablecoin_sector_shocks.json` | FTX/SVB/UST-type weeks |
| `config/stablecoin_security_events.json` | few dated security/legal events |
| Package: `incidents.csv`, `sector_shocks.csv`, `security_events.csv` | published tables |
| Factors: `incident_panel_weekly.csv` | weekly flags |

Builders: `incidents_panel.py`, `sector_shock_panel.py`

### 1.8 Etherscan / on-chain scrapes

| Path | Notes |
|------|-------|
| `lineage.json` → `scrapes_root` (`data_lake/spectator_engine/scrapes`) | Etherscan stablecoin list scrapes |
| Package `entities.csv` / `reference/entities.csv` | join Skynet↔Etherscan; `etherscan_join_suspect` flag |
| MCP helper: `drive/scripts/research_data_mcp/synthesis/skynet_etherscan.py` | join utilities |

### 1.9 Published research package `20260707` (~45 MB)

Path: `data/datasets/stablecoin_trust_engagement/20260707/` (`latest` → same)

| Area | Contents |
|------|----------|
| Root curated | `panel_weekly.csv`, `panel_latest.csv`, `entities.csv`, incidents/shocks/events, `manifest.json`, `lineage.json` |
| `panels/` | full-width daily/weekly/monthly (+ full_history quarantine) |
| `factors/` | per-source blocks before merge |
| `reference/` | security snapshots, maps |
| `validation/` | missingness, correlations, event studies |
| `professor_simple/` | faculty CSVs + methods/QA notes |

### 1.10 Not found / not collected (important negatives)

- Wayback/archive.org historical CertiK score scrapes
- LunarCrush time series (docs note paid tier; not present)
- Discord/Telegram historical member counts (CoinGecko may have snapshot counts only)
- Contract upgrade / proxy implementation change logs as a dedicated panel
- Multisig / admin key change event panel
- Continuous Etherscan verified-source history panel

---

## 2. Source lineage (final variables)

Machine-readable: `variable_lineage.csv`.

### 2.1 Professor simple weekly

| Final column | Internal | Raw → transform → final |
|--------------|----------|-------------------------|
| `attention_proxy_index` | `community_growth_index` | `community_attention_panel.csv` → `rollup_engagement_weekly` → `_attach_growth_index_by_entity` / `_z_scores` → rename in `professor_simple.py` |
| `google_trends_index` | `google_trends_index_mean` | Trends harvest → attention panel → weekly mean |
| `code_security_score` | same | Skynet `governance_strength` → `code_security.py` → latest/security snapshot → **repeated every week** |
| `peg_deviation` | `peg_deviation_abs_max` | DeFiLlama prices → weekly max abs deviation |
| `supply_usd` / `supply_growth` | `supply_usd_end` / `supply_growth_wow_pct` | DeFiLlama supply → weekly end + wow |
| `incident_count`, `depeg_dummy` | same | curated incidents → weekly flags |
| `sector_shock_flag` | same | sector shock JSON → week flag |
| `security_event_flag` | same | security events JSON → week flag |
| `gdelt_entity_mention_rows` | same | GDELT overlay + aliases → weekly count |
| `wikipedia_pageviews_sum` | same | Wikimedia pageviews → weekly sum |

**Not inputs to `attention_proxy_index`:** Wikipedia, GDELT, peg, supply, security scores.

### 2.2 Attention / community growth index inputs (weekly)

From `rollup_engagement_weekly` + `_attach_growth_index_by_entity`:

1. `google_trends_index_mean`
2. `reddit_submissions_sum` (from monthly source)
3. `twitter_followers_wow_pct`
4. `holder_wow_pct`

Then within-entity z-scores; mean of available z’s; **if stdev==0 → emit z=0.0** (`research_dataset.py`).

### 2.3 Builder entrypoints

| Script | Role |
|--------|------|
| `scripts/build_stablecoin_research_dataset.py` / `drive/scripts/build_stablecoin_research_dataset.py` | main package build |
| `stablecoin_skynet/research_dataset.py` | panels, growth index, merges |
| `stablecoin_skynet/professor_simple.py` | faculty export |
| `stablecoin_skynet/unified_dataset.py` | Skynet↔Etherscan spine |
| `stablecoin_skynet/collect_skynet_stablecoins.py` | API harvest |
| `drive/scripts/harvest_stablecoin_external_sources.py` | external refresh |
| `scripts/export_stablecoin_professor_simple.py` | professor pack export |
| `scripts/freeze_stablecoin_handoff_bundle.py` | freeze dated build |

---

## 3. Security-history reconstruction assets

### 3.1 What cannot be reconstructed from current Skynet scores alone

A true historical `scoreCodeSecurity(t)` panel for 2021–2026 is **not** in the harvest. Snapshot fields:

- Engineered `code_security_score` (governance flags → penalty/reward; worst-chain)
- Sparse official `skynetScore.*` on ~9 coins
- `website_scan` deduction scores (snapshot)
- `risky_smart_contracts` (3 coins)

Repeating snapshot scores across 2021–2026 weeks is **pseudo time series** (temporal leakage if treated as history).

### 3.2 Event / state assets that *do* exist

| Asset | Time-varying? | Strength | In professor panel? |
|-------|---------------|----------|---------------------|
| Curated incidents (`incidents.csv` / config) | Yes (event dates) | High for major depegs; sparse | Yes (flags) |
| Sector shocks | Yes | Market-wide | Yes |
| Security events config | Yes | Very few events | Yes (flag) |
| Skynet `security_incidents` endpoint | Yes | Almost empty (1 coin) | Partially via incidents pipeline |
| Skynet **milestones** (277 events) | Yes (timestamps) | Mixed (growth/expansion/institutional); some audit/regulatory headlines | **No — unexploited** |
| Skynet audits list | Weak | Stub metadata | No |
| Governance flags | Snapshot | Contract posture now | Via code_security_score only |
| GitHub security activity weekly | Thin | Few repos | Full package factors only |
| Peg deviation / supply stress | Yes | Trust stress, not “audit history” | Yes |
| Multi-harvest directories | Pseudo | Possible mini snapshot panel if scores differ by harvest time | Not built |

**Implication for auditors:** a longitudinal `security_state` / `security_event` process is more supported by **event streams** (incidents, milestones, curated security events, peg breaks) than by fabricating historical CertiK scores.

Extracted milestones + keyword subset are in the audit_summaries folder for inspection.

### 3.3 Opportunities not yet exploited (security)

See `unexploited_or_partial_assets.csv`. Highest leverage already-on-disk:

1. Structure Skynet milestones into a dated event panel (all categories + security/regulatory subset).
2. Compare `harvest_*` runs for any score/governance drift (short calendar span only).
3. Expand curated security/audit event library beyond the handful in `stablecoin_security_events.json`.
4. Peg-break and supply-outflow episodes as observable trust/security-adjacent states.
5. Wayback CertiK pages — **not collected** (external opportunity).

---

## 4. Community-growth reconstruction assets

Explicit construct split (do not collapse yet):

| Construct | Candidates in substrate | Longitudinal? |
|-----------|-------------------------|---------------|
| **Community size** | Twitter followers (short window); CoinGecko twitter/reddit/telegram counts (snapshot); holder_count (short window); supply_usd (adoption scale) | Mostly short / snapshot / adoption |
| **Community growth** | follower daily change (May–Jun 2026); holder wow; supply_growth | Short window strong; long window weak for social |
| **Community activity** | Reddit monthly submissions; Skynet pulses | Reddit monthly historical sample; pulses event-like |
| **Public attention** | Google Trends; Wikipedia pageviews; GDELT mentions | Trends densest long panel; Wiki/GDELT thinner |
| **Information demand** | Google Trends; Wiki pageviews | Yes |
| **Adoption** | DeFiLlama supply; holder counts; exchange listings (Skynet) | Supply strongest long panel |

### 4.1 Long-window attention vs short-window true growth

- **Long window (~2021–2026):** Trends (with zero-inflation problem), Reddit monthly, Wiki subset, GDELT subset, supply/peg.
- **Short window (~May–Jun 2026):** official Twitter followers & holders from Skynet — closest to “community growth” literally requested, but **not** a multi-year panel.

### 4.2 Ambiguous search terms

Registry: `community_registry_terms.csv` (from `registry.json`).

Trends queries are often coin **names** (e.g. “Alchemix USD”). Risk of contamination for generic names / tickers. Constant-zero Trends for 21 coins may indicate failed/low-volume queries rather than true zero attention — semantics are ambiguous (`missingness_semantics.csv`).

---

## 5. Missingness and coverage audit

Primary tables:

- `coverage_variable.csv` — research weekly columns
- `coverage_per_coin.csv`
- `coverage_per_year.csv`
- `constant_or_all_zero_series.csv` (**116** flags; includes 21 all-zero Trends)
- `missingness_semantics.csv`
- `professor_simple_weekly_coverage.csv`

Professor simple weekly non-null shares (approx): attention 98.3%, Trends 98.2%, code_security ~90%, peg ~55%, supply ~53%, Wikipedia ~20%, GDELT ~13%.

**Ambiguous zeros:** Trends `0.0`, attention `0.0` after stdev==0 branch, Reddit absence vs zero posts, GDELT “no alias hit” vs “no news”.

---

## 6. Temporal-grain audit

See `temporal_grain_audit.csv`. Critical issues:

| Issue | Variables | Risk |
|-------|-----------|------|
| Snapshot repeated into past weeks | `code_security_score`, sparse skynet scores | **Severe** if interpreted as history |
| Monthly Reddit painted onto weeks | `reddit_submissions_sum` | Pseudo-replication / leakage within month |
| Weekly Trends expanded on daily attention panel | Trends-related | Mild alignment issues |
| Balanced 263-week grid from 2021-W24 | all entities | Pre-launch / pre-active rows may exist with empty fundamentals |
| Short social series absent historically | twitter/holders | Missing ≠ zero growth |

---

## 7. Identity and active-life audit

- Universe: 71 Skynet leaderboard slugs (`entities.csv`).
- Upstream unified spine larger (Etherscan-only rows exist in reference; handoff universe filtered to 71).
- `identity_active_life.csv`: first supply/peg/trends weeks inside the research weekly panel.
- `etherscan_join_suspect` flags bad title joins.
- Panel is **balanced** (71×263): inclusion of weeks before first supply/price is a design choice, not proof the coin was active.

Rebrands / aliases: partial via registry names, GDELT aliases, DeFiLlama map — not a complete corporate-action database.

---

## 8. Pipeline and code (locations)

All relevant Python is under:

- `stablecoin_skynet/*.py`
- `stablecoin_skynet/community/*.py`
- `drive/scripts/*stablecoin*`
- `scripts/*stablecoin*`
- `config/stablecoin_*.json`

Included in the audit zip under `source/` and `config/`.

Key function for attention issues: `research_dataset._z_scores` / `_attach_growth_index_by_entity` / `rollup_engagement_weekly`.

---

## 9. Existing research / professor context documents

| Document | What it records |
|----------|-----------------|
| `stablecoin_skynet/data/community/PROFESSOR_HANDOFF.md` | Early explicit proxy strategy; cites Terra Twitter papers; admits no lifetime followers |
| `stablecoin_skynet/data/community/METHODOLOGY.md` | Skynet Twitter ~4–6 weeks; holder series; pulses |
| `professor_simple/README_FOR_PROFESSOR.md` | What was delivered vs requested |
| `professor_simple/METHODS_ATTENTION_PROXY.md` | Weekly z-score composite formula |
| `professor_simple/QA_ATTENTION_PROXY_ZEROS.md` | Constant-zero Trends coverage inflation |
| `docs/STABLECOIN_RESEARCH_DATASET.md` | Full package documentation |
| `docs/STABLECOIN_PROFESSOR_HANDOFF.md` | Email thread + revised reply draft + prior ChatGPT context |
| `panels/METHOD.md`, `START_HERE_PROFESSOR.md` | Package methods / entry |
| Email thread (summarized in STABLECOIN_PROFESSOR_HANDOFF) | Chris delivery 2026-07-07; De-Rong asks about attention construction / monthly vs weekly 2026-07-11 |

Proxy decisions already considered in-repo: Trends + Reddit + short Skynet social as stand-ins; optional Mendeley/LunarCrush noted; professor simple deliberately narrow.

---

## 10. Machine-readable audit outputs

Directory: `docs/status/generated/stablecoin_full_audit/`

| File | Purpose |
|------|---------|
| `audit_summary.json` | high-level counts |
| `inventory_datasets.csv/json` | file inventory |
| `variable_lineage.csv` | lineage |
| `coverage_*.csv` | coverage |
| `constant_or_all_zero_series.csv` | constant/zero flags |
| `missingness_semantics.csv` | missingness meanings |
| `temporal_grain_audit.csv` | frequency/leakage |
| `identity_active_life.csv` | IDs / first obs |
| `community_registry_terms.csv` | Trends/Reddit queries |
| `skynet_*.csv` | harvest extracts |
| `unexploited_or_partial_assets.csv` | gaps / opportunities |
| `skynet_harvest_runs.csv` | harvest directory list |

---

## 11. Question this package is meant to answer (for ChatGPT)

> Given all data already collected, what is the strongest defensible way to reconstruct longitudinal stablecoin **security/audit evolution** and longitudinal **community growth** for Professor Kong’s original research objective?

Constraints for the auditor:

- Do not treat repeated `code_security_score` as historical audits.
- Do not treat `attention_proxy_index` as validated community growth.
- Distinguish size / growth / activity / attention / adoption.
- Prefer event-based security state if scores cannot be recovered.
- Prefer multi-indicator unbalanced growth measurement if follower history cannot be recovered.
- Call out unexploited on-disk assets (especially milestones + short true follower panel + multi-harvest snapshots).

---

*End of handoff. Data not modified.*
