# Stablecoin professor package — full handoff (ChatGPT / ops / faculty)

**Purpose of this document:** one place that explains what was delivered to Professor De-Rong Kong (Yuan Ze University), how every major column was built, what questions she asked, and how to continue work without prior chat context.

**Frozen build:** `data/datasets/stablecoin_trust_engagement/20260707/`  
**Symlink:** `…/latest` → `20260707`  
**Upload zip companion:** `data/datasets/stablecoin_trust_engagement/chatgpt_context_stablecoin_professor_20260707.zip` (professor files + this handoff pack)

---

## 0. How to use this pack (ChatGPT / next agent)

1. Unzip the context archive (or open this folder tree in the repo).
2. Read this file top-to-bottom once.
3. For faculty-facing detail on attention: `professor_simple/METHODS_ATTENTION_PROXY.md`.
4. For data: start with `professor_simple/stablecoin_simple_weekly.csv` + `stablecoin_simple_latest.csv`.
5. Do **not** invent Twitter follower history or historical weekly audit scores — those were explicitly unavailable; proxies were shipped instead.

**Repo root (Sharpe-Renaissance):**  
`/home/phyrexian/Downloads/llm_automation/project_portfolio/Molina-Optiplex/Sharpe-Renaissance`

**Product split:** Research Drive / procurement = `drive/`; this dataset lives under Sharpe-Renaissance data + `stablecoin_skynet/` builders. Alpha trading (`alpha/`) is unrelated.

---

## 1. Email thread (what the professor has)

### Chris → De-Rong (2026-07-07)

Delivered a **simplified proxy dataset** because:

- Historical X/Twitter follower growth is **not** consistently available for the Skynet stablecoin universe.
- Historical weekly audit / security-score series is **not** available; Skynet gives a **current** security posture.

Main files pointed to:

- `README.md` / professor README
- `stablecoin_simple_latest.csv` — 71 coins, current profile
- `stablecoin_simple_weekly.csv` — weekly panel, 2021-W24 → 2026-W26, 18,673 rows
- Excel workbook optional

Framing already stated in email:

- `code_security_score` = current Skynet security snapshot (not weekly historical audits)
- Weekly attention uses `attention_proxy_index` (proxy; not recovered Twitter history)

### De-Rong → Chris (2026-07-11)

Asked specifically:

1. How was `attention_proxy_index` constructed (coverage looks more comprehensive)?
2. Is it computed at **monthly** frequency?
3. Or share the data source.

### Correct answers (verified against code + CSV)

| Q | A |
|---|---|
| Construction | Within-entity mean of z-scores of available weekly engagement fields (Trends primary; Reddit; sparse Twitter/holder WoW). |
| Monthly? | **No — weekly** ISO weeks. |
| Source | Primarily **Google Trends** via `community_attention_panel.csv`; see methods note. |
| Why dense? | Trends is **present** on ~98% of entity-weeks — **including 21 coins with constant-zero Trends**, which still produce non-null attention via the zero-stdev → z=`0.0` branch. See `QA_ATTENTION_PROXY_ZEROS.md`. |

**Do not send the old “Trends is comprehensive” draft without the constant-zero caveat.** Revised reply: §8.

---

## 2. What was shipped (professor-simple)

Path: `data/datasets/stablecoin_trust_engagement/20260707/professor_simple/`

| File | Role |
|------|------|
| `README_FOR_PROFESSOR.md` | Plain-language framing & caveats |
| `COLUMN_GUIDE.md` | Column dictionary |
| `COVERAGE_SUMMARY.md` | Fill rates |
| `METHODS_ATTENTION_PROXY.md` | **Methods note for attention_proxy_index** |
| `QA_ATTENTION_PROXY_ZEROS.md` | **Audit: constant-zero Trends inflate coverage** |
| `stablecoin_simple_latest.csv` | 71 rows, cross-section |
| `stablecoin_simple_weekly.csv` | 18,673 rows, weekly panel |
| `stablecoin_simple_workbook.xlsx` | Same data in Excel |

Entry pointers:

- `START_HERE_PROFESSOR.md` (package root)
- Package `README.md` → points at `professor_simple/`

**Universe:** 71 CertiK Skynet stablecoin leaderboard entities (not all global stables).

---

## 3. Package map (full research tree)

```
20260707/   (= latest/)
  START_HERE_PROFESSOR.md
  README.md
  panel_weekly.csv              curated narrow weekly handoff
  panel_latest.csv
  entities.csv
  incidents.csv
  sector_shocks.csv
  security_events.csv
  manifest.json
  lineage.json                  upstream paths
  professor_simple/             ← what Chris sent
  panels/                       full-width daily/weekly/monthly + METHOD.md
  factors/                      per-source blocks
  reference/
  validation/
```

Canonical long-form research docs:

- `docs/STABLECOIN_RESEARCH_DATASET.md` — full dataset documentation
- `docs/STABLECOIN_PROFESSOR_HANDOFF.md` — **this file**
- `panels/METHOD.md` — short methods inside the package

---

## 4. Column rename map (critical)

Professor-simple is a **thin export** of `panel_weekly.csv` / latest tables, with friendlier names:

| Full / internal | Professor-simple |
|-----------------|------------------|
| `community_growth_index` | `attention_proxy_index` |
| `google_trends_index_mean` | `google_trends_index` |
| `peg_deviation_abs_max` | `peg_deviation` |
| `supply_usd_end` | `supply_usd` |
| `supply_growth_wow_pct` | `supply_growth` |
| (latest) last non-null `community_growth_index` | `attention_proxy_latest` |

Builder: `stablecoin_skynet/professor_simple.py`  
(`build_simple_weekly`, `build_simple_latest`)

---

## 5. `attention_proxy_index` — construction (authoritative)

**Frequency:** weekly (ISO week), **not** monthly.

**Code:**

- Rollup: `rollup_engagement_weekly()` in `stablecoin_skynet/research_dataset.py`
- Index: `_attach_growth_index_by_entity(weekly, fields=[...])`
- Z-scores: `_z_scores()` (within-entity population mean/stdev; need ≥2 points)

**Input fields to the composite (weekly):**

1. `google_trends_index_mean`
2. `reddit_submissions_sum`
3. `twitter_followers_wow_pct`
4. `holder_wow_pct`

**Algorithm:**

1. For each entity, z-score each input series over that entity’s weeks.
2. For each week, average the **non-null** z-scores.
3. If none → null.
4. Round to 4 decimals → `community_growth_index` → exported as `attention_proxy_index`.

**Not in the formula:** `wikipedia_pageviews_sum`, `gdelt_entity_mention_rows` (exported beside the index for robustness / description).

**Upstream Trends/Reddit/Twitter/holders panel:**  
`stablecoin_skynet/data/community/community_attention_panel.csv`  
(see `lineage.json` → `community_attention_panel`)

**Coverage (professor weekly file):**

| Variable | ~fill |
|----------|------:|
| attention_proxy_index | 98.3% |
| google_trends_index | 98.2% |
| wikipedia_pageviews_sum | 20.5% |
| gdelt_entity_mention_rows | 13.4% |

**Critical nuance (2026-07-12 audit):** 21 coins have ~262 weeks of Trends all equal to `0.0`. `_z_scores()` maps zero-stdev series to z=`0.0`, so attention stays non-null (often exactly `0.0`). See `professor_simple/QA_ATTENTION_PROXY_ZEROS.md`. Faculty-facing writeup: `METHODS_ATTENTION_PROXY.md`.

```python
# research_dataset.py — the branch that creates dense zeros
if stdev == 0:
    return [0.0 if v is not None else None for v in values]
```

Future rebuild candidate: when `stdev == 0`, return all `None` for that field (not applied to frozen `20260707`).

---

## 6. Other major variables (quick reference)

| Concept | Column(s) | Truth |
|---------|-----------|--------|
| Code security | `code_security_score` | **Cross-section snapshot** from Skynet `governance_strength` flags (worst-chain conservative). Repeated on every weekly row as a **control**, not a time series of audits. |
| Skynet overall score | `skynet_score` | Sparse (~13% in latest); prefer `code_security_score`. |
| Peg stress | `peg_deviation`, `peg_below_99_flag` | DeFiLlama prices vs $1 |
| Adoption / size | `supply_usd`, `supply_growth` | DeFiLlama circulating USD |
| Discrete shocks | `incident_count`, `depeg_dummy`, `sector_shock_flag`, `security_event_flag` | Curated JSON configs + flags |
| News | `gdelt_entity_mention_rows` | GDELT overlay + alias config |
| Wiki attention | `wikipedia_pageviews_sum` | Explicit article map only |

Configs (repo `config/`):

- `stablecoin_defillama_map.json`
- `stablecoin_wikipedia_articles.json`
- `stablecoin_gdelt_aliases.json`
- `stablecoin_curated_incidents.json`
- `stablecoin_sector_shocks.json`
- `stablecoin_security_events.json`

Skynet harvest (canonical raw):  
`stablecoin_skynet/data/harvest_20260622T132438Z/projects/*.json`  
(paths recorded in `lineage.json` / `manifest.json`)

---

## 7. Rebuild commands (ops only)

From Sharpe-Renaissance repo root, with venv:

```bash
# Optional: refresh free external APIs
PYTHONPATH=. .venv/bin/python scripts/harvest_stablecoin_external_sources.py

# Optional: GitHub activity proxy
GITHUB_TOKEN=... PYTHONPATH=. .venv/bin/python scripts/harvest_stablecoin_github_activity.py

# Rebuild research package (+ professor_simple export if wired in build script)
PYTHONPATH=. .venv/bin/python scripts/build_stablecoin_research_dataset.py
```

Key modules:

- `stablecoin_skynet/research_dataset.py` — panels + growth index
- `stablecoin_skynet/professor_simple.py` — faculty export
- `stablecoin_skynet/code_security.py` — security score
- `docs/STABLECOIN_RESEARCH_DATASET.md` — full methods for research package

**Do not silently change formulas** after a faculty delivery without versioning a new build folder and updating README/methods.

---

## 8. Draft email reply (Chris → De-Rong) — revised after QA

**Do not use the earlier “Trends is comprehensive” draft alone.** Use this version (or shorten):

```text
Dear Professor Kong,

Thank you for the careful review — and for noticing the coverage pattern.

Frequency. attention_proxy_index is weekly (ISO week labels such as
2023-W10), not monthly. It lives in stablecoin_simple_weekly.csv
(71 coins × weeks from 2021-W24 to 2026-W26).

Construction. For each stablecoin we (1) aggregate available
attention/community signals to the ISO week, (2) convert each input
to a within-entity z-score over that coin’s history, and (3) average
the non-missing z-scores for that week. Inputs are Google Trends
(weekly mean), Reddit submission counts when present, and sparse
Skynet Twitter / holder week-on-week growth rates. In the full build
this series is named community_growth_index; the simplified package
renames it to attention_proxy_index.

Why coverage looks high. Non-null attention is ~98%, almost entirely
because Google Trends is present that week. For coins whose Trends
series actually varies over time, the attention proxy is very close
to the within-coin Trends z-score.

One important caveat: for 21 of the 71 coins, the Trends series is
filled with constant zeros (every week = 0). Our z-score step treats
a constant series as z = 0 rather than missing, so the attention
proxy stays non-null (and is often exactly 0) even though Trends is
not informative for those coins. So the high fill rate should not be
read as uniformly high-quality attention variation across the whole
universe. I am attaching a short methods note and a QA note that list
those 21 coins. For attention work, I recommend also using the raw
google_trends_index column and treating constant-zero Trends coins
with care (or dropping them).

Wikipedia pageviews and GDELT mentions in the same file are separate
columns; they are not inputs to attention_proxy_index.

Happy to rebuild a stricter version of the proxy (treating constant
series as missing) if that would be more useful for your design.

Best regards,
Chris
```

Attachments to offer: `METHODS_ATTENTION_PROXY.md`, `QA_ATTENTION_PROXY_ZEROS.md`.
---

## 9. What not to claim (integrity)

Do **not** tell the professor or write in papers that:

- `code_security_score` varies historically week-by-week in this package
- `attention_proxy_index` is Twitter follower growth
- Wikipedia/GDELT are components of `attention_proxy_index` (they are not)
- The panel covers all global stablecoins
- Security **causes** attention or peg stability (association / moderation only)

Z-scores are **within-entity**: cross-sectional comparisons of the index level across coins need extra care (or use raw Trends).

---

## 10. Open / follow-ups

| Item | Status |
|------|--------|
| Answer De-Rong on attention construction + weekly freq | **Revised draft ready (§8)** — include constant-zero caveat |
| Methods + QA notes | Written (`METHODS_…`, `QA_ATTENTION_PROXY_ZEROS.md`) |
| Prove `_z_scores` zero-stdev branch + raw panel | **Confirmed** 2026-07-12; source + raw panel in upload zip |
| Rebuild with stdev==0 → missing (stricter proxy) | **Not done** — would be a new dated build if professor wants it |
| Discover UI / yzu-cluster sufficiency work | Separate product track — not this dataset |

---

## 11. Files to upload to ChatGPT (minimum set)

If not using the prebuilt zip, upload at least:

1. This file — `docs/STABLECOIN_PROFESSOR_HANDOFF.md`
2. `professor_simple/METHODS_ATTENTION_PROXY.md`
3. `professor_simple/QA_ATTENTION_PROXY_ZEROS.md`
4. `professor_simple/README_FOR_PROFESSOR.md`
5. `professor_simple/COLUMN_GUIDE.md` + `COVERAGE_SUMMARY.md`
6. `professor_simple/stablecoin_simple_latest.csv` + `stablecoin_simple_weekly.csv`
7. **Proof:** `stablecoin_skynet/research_dataset.py` (at least `_z_scores` / `rollup_engagement_weekly`)
8. **Proof:** `stablecoin_skynet/data/community/community_attention_panel.csv`
9. Optional depth: `docs/STABLECOIN_RESEARCH_DATASET.md`, `panels/METHOD.md`, `lineage.json`, `manifest.json`

Workbook `.xlsx` optional (same data as CSVs).

---

## 12. One-paragraph briefing (paste-ready)

> We delivered a frozen 2026-07-07 professor-simple stablecoin package (71 Skynet leaderboard coins): cross-section CSV + weekly panel 2021-W24–2026-W26 (18,673 rows). Historical Twitter followers and historical weekly audit scores were unavailable, so we shipped proxies. `code_security_score` is a current Skynet-derived security snapshot used as a repeated cross-sectional control. `attention_proxy_index` is weekly (not monthly): within-entity average of z-scored Google Trends (primary), Reddit, and sparse Twitter/holder WoW %. ~98% non-null coverage is mostly Trends *presence*; 21/71 coins have constant-zero Trends, and `_z_scores` maps zero-stdev series to z=0 so attention stays filled (often exactly 0) — Professor Kong’s “coverage looks comprehensive” question is well-founded. Wikipedia/GDELT are separate thinner columns. Reply only with the revised draft that includes this caveat. Proof: `QA_ATTENTION_PROXY_ZEROS.md`, `research_dataset.py`, `community_attention_panel.csv`.

---

*Updated 2026-07-12 after constant-zero Trends QA. Dataset build remains `20260707` (data not rewritten).*
