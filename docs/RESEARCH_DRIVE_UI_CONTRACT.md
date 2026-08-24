
> **Legacy-only notice (2026-07-14):** This document applies only to the legacy `src/main.jsx` surface and its legacy regression tests. It does not prescribe current v2 product composition, navigation, rail behavior, Preview behavior, or responsive rules. Current decisions live in [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md).

# Research Drive UI Contract

> **Superseded for new work** by [`RESEARCH_DRIVE_UI_CANON.md`](RESEARCH_DRIVE_UI_CANON.md) (2026-06-28).  
> This file remains in force **only** for legacy `src/main.jsx` + `e2e/ui-contract.spec.js` until `VITE_UI_V2` cutover.

**Status:** Frozen v1.1 — 2026-06-25 (legacy)  
**Authority:** Was canonical through v1; do not extend for new surfaces.  
**Product promises:** [`DESK_STATUS.md`](DESK_STATUS.md) — organized GDrive + procurement chat; flywheel is catalog write-back.  
**Enforcement:** `e2e/ui-contract.spec.js` (run in CI / before merge on desk UI)

---

## 1. Product shape (one paragraph)

Research Drive is a **Google Drive–style shell** for lab datasets, with **Hugging Face–style procure surfaces** (Discover → Browse), a scoped right-rail Assistant for selected data, and **Chat as a peer full-page tool** for deeper sourcing sessions.

**Internal lane** = what the lab holds (Home, Recent, Starred, Drive, Cluster).  
**Procure lane** = what the lab can acquire (Discover, Browse).  
**Tools lane** = Chat, Activity.

---

## 2. Shell layout (non-negotiable)

```text
┌──────────┬─────────────────────────────┬──────────────┐
│ Sidebar  │ Main canvas                 │ Inspector    │
│ 240px    │ flex                        │ 380px        │
│ nav only │ primary work                │ Details rail │
└──────────┴─────────────────────────────┴──────────────┘
         Global header: brand · library search · New · account
```

| Rule | Detail |
|------|--------|
| Grid | `240px · 1fr · 380px` when inspector is shown |
| Inspector **on** | Home, Recent, Starred, Drive, Dataset detail |
| Inspector **off** | Chat, Discover, Browse, Cluster, Activity, admin views |
| Chat in main | Full-page Chat nav is for deeper sessions; internal data views may also expose a scoped Assistant tab in the inspector |
| Folder tree | **No** folder rail on Drive (catalog table + scope chips only) |

---

## 3. Navigation

### Sections (sidebar labels)

| Section | Items |
|---------|--------|
| **Internal** | Home, Recent, Starred, Drive, Cluster |
| **Procure** | Discover |
| **Tools** | Chat, Activity |
| **Admin** | Lab admin (collapsed): jobs, credentials, workers |

### Badge policy

| Item | Badge |
|------|-------|
| Activity | Pending/running job count **only** |
| Chat, Drive, Home, Recent, Starred, Discover, Cluster | **No** count badges |

---

## 4. Surface contracts

### Home (`view=home`)

**Role:** GDrive Home — recent work first, same table language as Drive.

| Must have | Must not have |
|-----------|----------------|
| `PageBar` title **Home** | Editorial hero (“What the lab holds”, serif kickers) |
| Section **Recent** (`h2`) + optional **Suggested for you** | Smart procure bar, procure footnotes in main |
| `CatalogTable` with `showScopeColumn` (same columns as Drive) | Featured-only 3-column table, nested `rd-l1-panel` card |
| **Details** inspector rail always visible and default (idle until selection); Assistant tab opt-in | Hiding inspector until selection |
| “See all” → Recent nav | Duplicate tiles / quick-action grid on Home |

### Recent / Starred

Same as Drive table + inspector. PageBar title matches nav label.

### Drive

| Must have | Must not have |
|-----------|----------------|
| PageBar **Drive** | Separate Lab/My top-level nav items (merged into Drive) |
| Scope chips: **All · Lab · My uploads** | Folder tree rail |
| `CatalogTable` with scope column on All | — |
| Inspector Details default; Assistant tab may answer against selected dataset context | Assistant as default on Drive |

### Dataset workspace (`view=dataset`)

Full-page tabs: Overview, Preview, Schema, Query, Updates. Inspector may show same dataset Details.

### Discover (`view=recommended`)

| Must have | Must not have |
|-----------|----------------|
| Procure L1: **PageBar** title **Discover**, search + filter chips | Inspector rail |
| Result **card grid**; **library hits instant** from registry while catalog search loads | Legacy `.rd-result-row` list-only layout |
| Cards → **Browse** (`view=browse`) | Chat thread in main |

### Browse (`view=browse`)

HF-style drill-in: hero, facets, tabs Overview / Details / Collect. **No** inspector. Back → Discover.

### Chat (`view=chat`)

| Must have | Must not have |
|-----------|----------------|
| Full-page main (`yzu-procure.main`) | Inspector |
| Title **Source & compare** (not duplicate “Chat” PageBar in thread) | Procure panel in sidebar |

### Cluster (`view=cluster`)

Coverage map (domains, gaps, pipeline). **No** inspector. Procure CTAs via nav only, not home footnotes.

### Activity (`view=dashboard`)

Job list. **No** inspector. Title **Activity** (not “Procurement dashboard”).

---

## 5. Inspector (Details rail)

| State | Content |
|-------|---------|
| Idle | Details tab: heading **Details** + “Select a dataset…”; Assistant tab is available but not default |
| Selected | Dataset metadata, Open / Star / Preview with assistant chips |
| Tabs | **Details** default + **Assistant** opt-in on Home, Recent, Starred, Drive, Dataset detail |

Selection in main list updates inspector; it does **not** auto-navigate to full-page Chat. Contextual Preview / Find related actions open the rail Assistant.

---

## 6. Header search

| Action | Behavior |
|--------|----------|
| Type + Enter | Filter library rows on current internal view |
| **Chat** button in search | Navigate to full-page Chat with query |

---

## 7. Anti-patterns (do not reintroduce)

1. Magazine Home with serif hero and “vault” copy  
2. Toggling inspector on/off on Home between iterations without contract amendment  
3. Chat badge on nav + Activity badge duplicating the same count  
4. Procure footnotes on Home / inspector idle  
5. `Lab Drive` / `My Drive` as separate sidebar peers (use Drive + scope chips)  
6. Assistant as the default inspector state on Home/Drive  
7. Passing Playwright only — shipping UI that fails visual/OSS parity without contract update  

---

## 8. Change process

1. Propose amendment to this file (PR or issue) with **surface**, **rule**, **why**.  
2. Update `e2e/ui-contract.spec.js` in the same change.  
3. Run `TMPDIR=.tmp-pw npx playwright test e2e/ui-contract.spec.js`.  
4. Do **not** merge UI-only refactors that contradict the contract.

---

## 9. Related docs

| Doc | Role |
|-----|------|
| [`RESEARCH_DRIVE_UI_CANON.md`](RESEARCH_DRIVE_UI_CANON.md) | **New UI** — implement here, not this contract |
| `docs/PROCUREMENT_PIPELINE.md` | Backend / registry truth |
| `e2e/desk.spec.js`, `e2e/source-first.spec.js` | Behavioral regression suites |
| `e2e/ui-contract.spec.js` | **Legacy layout assertions** (this contract only) |
