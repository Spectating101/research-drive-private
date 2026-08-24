# Status — Bridge (local) + LSEG MarketPsych probe

**Updated:** 2026-07-13 (after password fix)

---

## Platform auth

**OK.** `refinitiv_access_probe.py --mode platform` returns data (e.g. BBCA.JK).

---

## MarketPsych entitlement — verdict

### **Not available on this YZU EDP app-key scope via standard TR.* / news APIs.**

| Test | Result |
|------|--------|
| `TR.MPSentiment`, `TR.MPBuzz`, `TR.MPAdoption`, crypto theme fields, etc. | **Unable to resolve all requested fields** (AAPL, BTC=, USDT=) |
| `TR.SocialSentiment` / `TR.NewsSentiment` / TRNA-like | **Unable to resolve** |
| `get_history` of MP fields | **Unable to resolve** |
| News headlines API | **Insufficient scope** — needs `trapi.data.news.read` (not in available scopes) |
| Search `"MarketPsych"` | Finds product docs + chain RIC `0#MARKETPSYCH` (contributor metadata), **not** pullable analytics scores |
| Known entitled controls (ESG, identity, equity get_data) | **Work** |

Artifacts:
- `lseg_marketpsych_entitlement_probe.json`
- `lseg_search_followup.json`
- `lseg_marketpsych_chain_probe.json`

### Implication

ChatGPT’s MarketPsych plan is **product-correct** but **not entitled** on the current YZU Data Platform credentials. Options:

1. Ask YZU/LSEG to add MarketPsych Analytics (and ideally `trapi.data.news.read`) to the campus entitlement.  
2. Separate MarketPsych API/SFTP subscription (search results mention “MarketPsych API” / “Data via SFTP”).  
3. Continue **v2.1 without MarketPsych**: local Twitter bridge + existing Trends/holders/supply/events (already built under `bridge_v21/`).

Crypto on this account appears mainly as **FX spot RICs** (`USDT=`, `BTC=` as FX Spot Rate), not a full crypto analytics package.

---

## Local bridge (unchanged conclusion)

See `data/datasets/stablecoin_trust_engagement/bridge_v21/` — Trends shows modest within-community co-movement with real Twitter growth; old `community_growth_index` correlation is target leakage.

