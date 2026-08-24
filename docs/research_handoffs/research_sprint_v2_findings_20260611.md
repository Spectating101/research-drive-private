# Research Sprint v2 — Horse Race + Crypto

**Date:** 2026-06-11  
**Script:** `scripts/run_research_sprint_v2.py`  
**Outputs:** `backtests/outputs/research_sprint_v2/20260611T102347Z/`

---

## 1. Horse race: taxonomy vs EPU / GPR / VIX

**Question:** After Baker-Bloom-Davis **country EPU**, Caldara-Iacoviello **country GPR**, global GPR, **VIX**, tone, and news volume — does our 8-category taxonomy still add anything?

**Method:** Country within-transformed OLS (country FE). Baseline sample n≈2,185 (months where EPU/GPR merge).

### Incremental R² (taxonomy on top of baseline)

| Target | Baseline R² | Taxonomy-only R² | Combined R² | **ΔR²** |
|---|---:|---:|---:|---:|
| fwd_return_1w | 1.3% | 0.7% | 1.8% | **+0.46%** |
| fwd_return_4w | 5.6% | 2.6% | 6.8% | **+1.17%** |
| fwd_vol_4w | 12.9% | 6.0% | 14.3% | **+1.43%** |

**Verdict:** Taxonomy adds **something**, but **scalars (EPU/GPR/VIX) explain more of vol** than taxonomy alone. This is not a knockout “we replace EPU/GPR” result — it's an **incremental refinement** story.

### What survives baseline controls (4w return)

| Category | Coef (conditional) | Read |
|---|---:|---|
| health | **−0.53%/week** | Health-shock weeks → lower 4w returns after EPU/GPR/VIX |
| natural_environment | +0.49%/week | |
| political_instability | +0.31%/week | Smaller than v1 pooled result |
| governance_corruption | −0.09%/week | Weak |

### What survives baseline controls (4w vol)

All taxonomy coeffs **< 0.12%/week** after baseline — marginal.

---

## 2. Crypto — Asia GDELT crypto overlay → BTC/ETH

**Question:** Does **Asia crypto-classified news** (regulation, exploits, market stress) predict **global** BTC/ETH next-week returns/vol, controlling SPY + VIX?

**Data:** Sum of `country_week_crypto_news_panel` across 13 countries, weekly 2018–2026, merged to global BTC/ETH from fused panel.

### Event studies (top decile Asia news weeks vs rest)

| Event type | BTC fwd 1w (hi − lo) | |return| hi vs lo |
|---|---:|---|
| **security_exploit** | **+1.15%** | 7.0% vs 6.2% |
| exchange_market_structure | +1.32% | ~flat |
| institutional_adoption | +0.60% | 4.5% vs 6.5% (lower vol) |
| **regulation_enforcement** | **−0.73%** | ~flat |
| **market_stress** | −1.05% | 4.6% vs 6.5% (lower vol after stress-news weeks) |

### Regressions (z-scored Asia event intensity, control SPY + VIX)

| Event | BTC fwd 1w coef | ETH fwd 1w coef |
|---|---:|---:|
| **security_exploit** | **+0.51%** | **+0.52%** |
| regulation_enforcement | −0.30% | −0.57% |
| market_stress (ETH) | — | −0.63% |
| market_stress (|BTC| vol) | −0.72% (4w realized vol) | −1.00% |

### Country-specific regulation ↔ BTC (corr, exploratory)

| Country | corr(reg news, BTC 1w fwd) |
|---|---:|
| **IND** | **−0.092** |
| **HKG** | **−0.053** |
| CHN | −0.025 |
| KOR / SGP | ~0 |

**Crypto verdict (more interesting than country ETF panel):**

- **Exploit/hack news** in Asia is associated with **higher** subsequent global crypto returns and larger moves — plausibly attention/liquidation/rebound dynamics.
- **Regulation enforcement** news (especially India/Hong Kong slices) aligns with **weaker** next-week BTC/ETH — a coherent “Asia regulatory chokepoint” narrative.
- **Not** a full factor model — no crypto momentum/size controls yet (Liu-Tsyvinski next step).

---

## 3. Governance × fragility interaction

**Failed spec:** within-country fragility proxy (median vol) has no variation after country demeaning → interaction degenerate.

**Proper test (not run yet):** cross-country interaction: governance shock × WGI/rule-of-law level, or governance shock × country median vol **between** countries.

---

## 4. What's actually interesting vs still boring

| Result | Interesting? |
|---|---|
| Taxonomy ΔR² +1–1.4% over EPU/GPR/VIX | Mild — incremental, not revolutionary |
| Health shocks → lower 4w returns after full controls | **Maybe** — worth one table in a paper |
| Asia exploit news → +1% BTC next week | **Yes** — clearest crypto lead |
| Asia regulation news → −0.7% BTC next week | **Yes** — policy channel |
| India reg news ↔ BTC ρ≈−0.09 | **Suggestive** — needs regression not corr |
| Governance dysfunction at firm level | Still untested properly |

---

## 5. Recommended v3 (if continuing)

1. **Crypto paper/track:** Exploit + regulation event studies with crypto momentum control; Granger Asia→US with timezone alignment.
2. **Academic horse race:** Formal F-test + Benjamini-Hochberg; week FE; compare category-specific GPR/EPU subindices if available.
3. **Governance:** Cross-country `governance_shock × institution_quality` using World Bank WGI from macro baseline.
4. **Firm-level:** Entity-residual panel when `ticker_20260611` lands.
