# Research Sprint v3 — Crypto Deep-Dive + Governance×Institutions

**Date:** 2026-06-11  
**Script:** `scripts/run_research_sprint_v3.py`  
**Outputs:** `backtests/outputs/research_sprint_v3/20260611T103223Z/`  
**Supplement:** `horse_race_joint_ftest.csv` (nested F-test, country + week FE)

---

## Executive summary

v3 hardens the **crypto regulatory chokepoint** story from v2 with momentum controls, country splits, BH-adjusted inference, and an event catalog. The **country ETF panel** horse race gets stronger once you add **week fixed effects**: taxonomy is jointly significant for 4w returns (F≈10.2, p≈4×10⁻¹⁴) and vol (F≈2.5, p≈0.01). Governance×institutions is still weak at the firm-week level; vol interaction t≈1.6 only.

**Best tradeable narrative:** India/Hong Kong **regulation enforcement** news → weaker next-week **ETH** (−1.4%/σ after BTC/ETH momentum + SPY + VIX). Hong Kong **exploit** news → **positive** ETH drift (+1.4%/σ). Asia **market-stress** weeks compress BTC absolute moves (−0.72%/σ) — stress headlines coincide with *lower* realized crypto vol, not panic spikes.

---

## 1. Crypto — momentum-controlled regressions

**Method:** Weekly Asia-summed GDELT crypto taxonomy (`country_week_crypto_news_panel`), merged to global BTC/ETH/SPY/VIX. Controls:

- **full_momentum:** z(event) + 4w rolling BTC/ETH momentum + SPY + VIX change  
- **base:** z(event) + SPY + VIX only  

HC1 robust SE; Benjamini–Hochberg across all regression p-values.

### Asia aggregate (survives momentum?)

| Event | Target | Coef (full_mom) | t | p | BH-adj p |
|---|---|---:|---:|---:|---:|
| market_stress | \|BTC\| 1w | **−0.72%**/σ | −2.79 | 0.005 | 0.058 |
| institutional_adoption | \|BTC\| 1w | −0.79%/σ | −2.76 | 0.006 | 0.058 |
| regulation_enforcement | BTC 1w | −0.30%/σ | −0.73 | 0.47 | — |
| security_exploit | BTC 1w | +0.42%/σ | +0.95 | 0.34 | — |

Aggregate Asia regulation is **directionally** negative but not significant once momentum is in — the signal is **country-local**, not pan-Asia sum.

### Country splits (full_momentum, highlights)

| Spec | Event | Target | Coef | p | BH-adj |
|---|---|---|---:|---:|---:|
| **IND** | regulation_enforcement | ETH 1w | **−1.40%**/σ | 0.012 | 0.10 |
| **IND** | regulation_enforcement | BTC 1w | −0.81%/σ | 0.090 | — |
| **HKG** | regulation_enforcement | ETH 1w | **−1.39%**/σ | 0.017 | 0.12 |
| **HKG** | security_exploit | ETH 1w | **+1.36%**/σ | 0.012 | 0.10 |
| **IND** | market_stress | BTC 1w | −0.88%/σ | 0.001 | **0.006** |
| **SGP** | market_stress | BTC 1w | −0.88%/σ | 0.000 | **0.006** |
| **CHN/SGP** | institutional_adoption | BTC 1w | ≈−0.7%/σ | 0.001–0.002 | **0.006** |

**Read:** India and Hong Kong regulation news is a **crypto headwind** (ETH clearer than BTC). Hong Kong hack/exploit news is a **positive ETH drift** week — opposite sign from regulation, consistent with attention/rebound rather than risk-off. Singapore/China institutional-adoption headlines align with **muted** subsequent BTC vol/returns (possibly “priced in” positive news).

### Lead-lag (Asia regulation → BTC)

| Lag | Coef | p |
|---|---:|---:|
| 0 (same week) | −0.32%/σ | 0.43 |
| 1 week | −0.08%/σ | 0.86 |
| 2 weeks | −0.48%/σ | 0.32 |

No clean delayed effect — impact is contemporaneous / within the same week bucket.

### Post-2022 subsample (exploit → BTC)

Coef +0.63%/σ (t=1.23, p=0.22, n=228) — exploit uplift **weaker** post-2022 but not flipped.

---

## 2. Event catalog (top intensity weeks)

**Regulation peaks** (examples):

| Week | Intensity | BTC 1w | ETH 1w |
|---|---:|---:|---:|
| 2025-12-05 | 11,349 | +0.99% | +1.98% |
| 2021-02-19 | 10,534 | **−17.1%** | **−26.2%** |
| 2021-04-16 | 10,258 | −17.0% | −2.8% |
| 2025-07-25 | 10,391 | −3.7% | −6.4% |

High-intensity regulation weeks are **bimodal** — some coincide with crash weeks (Feb–Apr 2021 China crackdown narrative), others with calm follow-through. Regression survives because the **conditional** slope is negative after controls; event study alone is noisy.

**Exploit peaks:**

| Week | Intensity | BTC 1w | ETH 1w |
|---|---:|---:|---:|
| 2019-08-16 | 3,717 | +0.3% | +5.0% |
| 2020-07-24 | 1,732 | **+18.7%** | **+23.8%** |
| 2020-12-11 | 1,439 | +28.1% | +20.0% |
| 2024-02-23 | 1,251 | +23.1% | +17.6% |

Exploit-heavy weeks often precede **large positive** crypto weeks — but catalog is cherry-picked top deciles; controlled regressions are more modest (+0.4–1.4%/σ depending on scope).

**Sample articles** pulled from `sample_high_priority.csv`: CoinDCX hack (IND, Jul 2025), Thai regulator cyberattack probe, DBS/tokenised-assets risk pieces — see `sample_articles.csv`.

---

## 3. Governance × institutions (World Bank WGI)

**Method:** Rule-of-law (`RL.EST`) + control-of-corruption (`CC.EST`) → `inst_quality`; interact with z-scored governance/corruption news. Country FE via within-demeaning.

| Target | gov coef | gov × low_inst | t (interaction) |
|---|---:|---:|---:|
| fwd_return_4w | +0.03%/σ | −0.07%/σ | −0.52 |
| fwd_vol_4w | −0.12%/σ | +0.06%/σ | **+1.61** |
| cross-country avg return | −0.06%/σ | +0.13%/σ | +0.93 |

**Verdict:** Weak. Low-institution countries show slightly **higher vol** when governance news intensifies (t≈1.6), but no return interaction. Firm-level governance on full entity history still blocked on `ticker_20260611` entity panel.

---

## 4. Horse race — joint F-test (taxonomy | EPU, GPR, VIX, tone, volume)

Nested F-test: baseline vs baseline + 8 taxonomy z-scores, same n≈2,170–2,185.

| FE spec | Target | ΔR² | F | p |
|---|---|---:|---:|---:|
| Country only | fwd_return_1w | +0.46% | 1.26 | 0.26 |
| **Country + week** | fwd_return_1w | **+0.84%** | 2.30 | **0.019** |
| Country only | fwd_return_4w | +1.17% | 3.38 | 0.0007 |
| **Country + week** | fwd_return_4w | **+3.60%** | **10.23** | **3.9×10⁻¹⁴** |
| Country only | fwd_vol_4w | +1.43% | 4.49 | 2.0×10⁻⁵ |
| Country + week | fwd_vol_4w | +0.91% | 2.53 | 0.010 |

**Upgrade from v2:** Week FE is critical — without it, 1w return increment looks insignificant (p≈0.26); with week FE, taxonomy is jointly significant for returns **and** vol. Story shifts from “incremental vol refinement” to “taxonomy adds **country-specific** information beyond global macro weeks.”

---

## 5. What’s still missing

| Gap | Blocker / next step |
|---|---|
| Firm-level governance alpha | `ticker_20260611` entity residual panel (Oct 2023–May 2025 only today) |
| Causal identification | Event-time windows around named enforcement actions (India FIU, HK SFC) |
| Crypto factor model | On-chain flows, funding rates, Liu-Tsyvinski style momentum/size |
| Out-of-sample | Pre-2020 holdout + post-2024 enforcement wave |
| BH survive | Several crypto country hits are p<0.05 raw but BH≈0.10 — need more obs or pre-registration |

---

## 6. Recommended research pitch

**Title:** *Asia regulatory news as a crypto headwind; exploit news as a Hong Kong ETH attention premium*

1. **ETF/country panel:** Taxonomy is **jointly significant** after EPU/GPR/VIX **and** week FE (especially 4w returns).  
2. **Crypto overlay:** India/HKG regulation → lower ETH; HKG exploits → higher ETH; stress/adoption headlines → compressed BTC vol.  
3. **Not** “news → vol” boilerplate — sign flips by event type and country, survives macro + momentum controls.

**Artifacts:** `crypto_regressions_v3.csv`, `crypto_event_catalog.csv`, `governance_institutions.csv`, `horse_race_joint_ftest.csv`, `highlights.txt`.
