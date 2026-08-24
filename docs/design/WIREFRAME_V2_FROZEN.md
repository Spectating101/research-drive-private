# Research Drive v2 — frozen wireframes

**Status:** FROZEN — 2026-06-28 (polish + forward plan in [`V2_FORWARD_FROZEN.md`](V2_FORWARD_FROZEN.md))  
**Authority:** UI sketch + interaction model for v2 implementation and CLI preview.  
**Overrides:** Informal sketches and older partition-chip layouts.  
**Canon:** [`RESEARCH_DRIVE_UI_CANON.md`](../RESEARCH_DRIVE_UI_CANON.md) (product rules)  
**Pixels:** [`LAYOUT_SPEC.md`](LAYOUT_SPEC.md) (1440×900 zones)

**CLI preview:** `python3 scripts/rd_layout_preview.py all --pager`

---

## Ship checklist (v2 quality bar)

Not competitor parity — four loops must work:

| Loop | Ship test |
|------|-----------|
| **Find** | Drill breadcrumb; ⌘K finds by name or `dataset_id` |
| **Understand** | Detail shows SOURCE→LIMITATIONS without Ask |
| **Use** | Preview shows rows or honest “remote / not available” |
| **Grow** | Browse → Add to lab → job in Resources → row in Library |

**Five yes/no gates before cutover:**

1. `Lab › … › folder` navigation is obvious and reversible via breadcrumb  
2. Selected dataset answers readiness, coverage, grain, vault path  
3. Preview works or explains why not  
4. External add completes visibly in-session  
5. WARN on Home/Resources links to the failing row  

**v2.1 defer:** usage charts, grid view, mobile drawer, lineage graph, Preview “open wide” second modal.

---

## Polish — frontend rules (v2)

### Status pills (one vocabulary app-wide)

| Pill | Meaning |
|------|---------|
| `Query-ready` | Local/indexed; preview + query work |
| `Connected` | Remote table wired; query via engine |
| `Remote` | External registry hit; not in vault yet |
| `Queued` | Procure/import job running |
| `WARN` | Usable but degraded (stale index, partial coverage) |

Never shorten to `ready` in lists — same labels in list row and Detail rail.

### Detail rail

- **Always full field block** — SOURCE through LIMITATIONS; zone D scrolls, never truncates in UI.
- CLI sketches abbreviate; implementation does not.

### Toasts (bottom-center, 4s, action link)

| Event | Toast |
|-------|-------|
| Add to lab | `Queued · twse_gov_panel` [Resources] |
| Job completed | `Added to Lab › procured` [Open] |
| Job failed | `Procure failed` [View log] |
| Export sample | `Sample saved` [Reveal] |

### Browse row states

| Row badge | Detail tertiary | List affordance |
|-----------|-----------------|-----------------|
| `◌ External` | Add to lab · Preview ext | Default discover hit |
| `✓ In lab` | Open in Library | Gray Add hidden |
| `⟳ Queued` | View in Resources | Spinner on row |

### Cluster

- **Save compare** → names pair; surfaces on Home Pinned + Profile pins.
- Compare toolbar: `[A ▾] [B ▾] [+ Library] [Save compare]`.

### Resources

- Filter chips under header: `[All] [WARN] [FAIL] [Running]` — filters ledger, does not change layout.

### Preview modal

- **One tab visible at a time** — Preview | Schema | Query swap body; no inline schema under table.
- Remote/BQ: Preview tab shows dry-run sample or honest disabled state + Ask link.

---

## Foundation — Google Drive grammar (Library / Home / Browse)

Drive sophistication = **one navigation model**, not three.

| Do (Drive-like) | Do not |
|-----------------|--------|
| **One list** in main (📁 folders + 📄 datasets) | `CatalogTable` as a UI label |
| **Breadcrumb** = where you are | Location column duplicating breadcrumb |
| **Folder click** → drill down, breadcrumb grows | `▾ research_panels` groups **and** breadcrumb **and** path column |
| Thin toolbar: `≡ list` · sort · **`Filter ▾`** | `[Panels][News][Crypto][Stable]` chip row |
| Select row → **Detail** pane on right | Duplicate chat UI under Detail |
| **Detail \| Ask** segmented control at top of rail | Ask as sidebar tab |
| Preview = modal overlay (Quick Look) | Preview as route or 8th tab |

**List row shape (all catalog lists):**

```text
📄 Asia daily news-risk panel          Query-ready · local · 2d
   gdelt_asia_daily · country-day · 2018–2026
```

**Registry columns** in list: readiness pill · source kind · relative time — not a separate Location column.

**Rail (Detail mode):** canonical field block + `[Preview]` · contextual tertiary · `Ask about this →` flips toggle (not a second chat pane).

**Browse:** same list grammar; row states per **Polish** §Browse; single **Discover** field in Browse toolbar (not duplicate with ⌘K).

---

## Shell (every page)

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RD · [ Search lab + discover ⌘K ] · 128 ds · [New ▾] · YZ ▾                │
├──────────┬───────────────────────────────────────────────────┬───────────────┤
│ ZONE B   │ ZONE C — main                                     │ ZONE D 360    │
│ 7 tabs   │ PageHeader · toolbar · content                    │ [Detail|Ask]  │
│ no Ask   │ selection → ?dataset= in URL                      │ one pane      │
└──────────┴───────────────────────────────────────────────────┴───────────────┘
```

Tabs: **Home · Library · Cluster · Browse · Resources · Profile · Settings**

| Header control | Behavior |
|----------------|----------|
| **Search ⌘K** | Filter in-tab list; **Enter** → rail Ask + query prefilled |
| **[New ▾]** | See **NEW MENU** below |
| Item count | Registry datasets in scope (tab-specific subtitle in PageHeader) |

---

## NEW MENU

Global `[New ▾]` — same on every tab.

```text
┌ New ─────────────────────┐
│ Ask to procure…          │  → rail Ask, empty thread
│ Import from URL…         │  → modal; queues job
│ Connect remote table…    │  → Settings creds if missing; then Ask
│ Open upload folder       │  → GDrive vault path (external)
└──────────────────────────┘
```

No wizard. Each action lands in **Ask** or a **single modal**, then **Resources** shows the job.

---

## DETAIL PANEL

Shared **Detail** mode — identical on Home, Library, Browse, Cluster selection.

```text
┌─ Detail | Ask ──────────────────────────────────────────────────────────────┐
│ Asia daily news-risk panel                                                    │
│ gdelt_asia_daily                                                              │
│ [Query-ready] [local vault]                                                   │
│ ─────────────────────────────────────────────────────────────────────────── │
│ SOURCE      GDELT GKG · scored country-day panel                              │
│ ACCESS      Query engine :8765 · parquet on NVMe                              │
│ COVERAGE    2018-01 – 2026-04 · 42 countries · daily                          │
│ GRAIN       country × day · ISO3 + date                                       │
│ VAULT       gdrive:…/collection/research_panels/gdelt/asia_daily              │
│ USE         News shock overlay · Asia equity event studies                    │
│ LIMITATIONS  TWSE names not joined · lag T+1                                  │
│ ─────────────────────────────────────────────────────────────────────────── │
│ [Preview rows]  [Ask about this →]  [See on Cluster]                          │
└───────────────────────────────────────────────────────────────────────────────┘
```

| Context | Tertiary (rightmost) |
|---------|----------------------|
| Library / Home | See on Cluster |
| Browse · External | Add to lab · Preview ext |
| Browse · In lab | Open in Library |
| Browse · Queued | View in Resources |
| Cluster | Expand overlap · Save compare |
| Resources row | View related dataset |

Idle: `EmptyState` — “Select a dataset or job row” — Ask toggle still available.

---

## ASK RAIL

Shared **Ask** mode — full rail height; thread persists across tabs.

```text
┌─ Detail | Ask ──────────────────────────────────────────────────────────────┐
│ Context: gdelt_asia_daily · Library · ⌘K query cleared              [New]   │
│ ─────────────────────────────────────────────────────────────────────────── │
│ You: overlap with ticker_week before 2020?                                    │
│                                                                               │
│ Agent: 82% date overlap · TW missing pre-2019. Suggest TWSE OpenAPI panel.   │
│        [Add TWSE to lab] [Open Cluster] [Preview overlap sample]              │
│ ─────────────────────────────────────────────────────────────────────────── │
│ [ Message…  Ask uses catalog + MCP tools ]                          [Send]   │
└───────────────────────────────────────────────────────────────────────────────┘
```

Replies are **not** canonical metadata — user toggles Detail for API fields.

---

## HOME

Drive analog: **Continue** + **Running** + **Pinned** + **Recent** — not full tree.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RD · [ Search lab + discover ⌘K ] · 78 ds · [New ▾] · YZ ▾                  │
├──────────┬───────────────────────────────────────────────────┬───────────────┤
│●Home     │ Home                                              │ Detail | Ask  │
│ Library  │ Continue where you left off                       │───────────────│
│ Cluster  │ ┌───────────────────────────────────────────────┐ │ Select a      │
│ Browse   │ │ Asia daily news-risk panel                    │ │ dataset       │
│ Resources│ │ gdelt_asia_daily · Preview closed 2h ago      │ │               │
│ Profile  │ │                    [Open in Library] [Preview]│ │  or toggle    │
│ Settings │ └───────────────────────────────────────────────┘ │  to Ask       │
│          │ Running                              [All jobs →] │               │
│          │ ● GDELT backfill ············ 18/99 mo · OK        │               │
│          │ ● DataCite queue · 4 workers · WARN  [Resources →]│               │
│          │ Pinned compares (saved)                           │               │
│          │ GDELT Asia × Ticker week              [Cluster →]│               │
│          │ Recent                               [See Library]│               │
│          │ Asia daily news-risk panel    Query-ready · 2d    │               │
│          │   gdelt_asia_daily                                │               │
│          │ CoinGecko market archive      Query-ready · 1d    │               │
│          │   coingecko_daily_archive                         │               │
│          │ Suggested gaps                                    │               │
│          │ [Browse TWSE daily] [Browse MOPS] [Ask to procure]│               │
└──────────┴───────────────────────────────────────────────────┴───────────────┘
```

| Strip | Click |
|-------|-------|
| WARN/FAIL running row | Resources → select row → Detail |
| Pinned pair | Cluster with both datasets loaded |
| Suggested chip | Browse filtered or Ask prefilled |

---

## LIBRARY

Drive analog: **My Drive** — breadcrumb drill-down; reference implementation for list tabs.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RD · [ Search lab + discover ⌘K ] · 12 in folder · [New ▾] · YZ ▾            │
├──────────┬───────────────────────────────────────────────────┬───────────────┤
│ Home     │ Lab › research_panels › gdelt                     │ Detail | Ask  │
│●Library  │ ≡ list   Name ▾   Last modified ▾   Filter ▾      │───────────────│
│ Cluster  │ Filter ▾: All · Query-ready · Connected · WARN    │ Asia daily…   │
│ Browse   │ ────────────────────────────────────────────────  │ gdelt_asia…   │
│ Resources│ 📁 archive                                      2  │ [Query-ready] │
│ Profile  │ 📄 Asia daily news-risk panel   Query-ready · 2d   │ SOURCE GDELT… │
│ Settings │    gdelt_asia_daily · country-day               │ ACCESS :8765  │
│          │ 📄 GDELT scored country panel     Query-ready · 3d │ COVERAGE …    │
│          │    gdelt_scored_country                           │ (full block   │
│          │ 📄 Cross-asset fused panel        Query-ready · 3d │  scrolls)     │
│          │    cross_asset_fused                                │               │
│          │ 📄 CoinGecko market archive       Query-ready · 1d │ [Preview]     │
│          │    coingecko_daily_archive                          │ [See Cluster] │
│          │ 📁 Empty folder example:                          │ [Ask about →] │
│          │    “No datasets · [Ask to procure]”               │               │
└──────────┴───────────────────────────────────────────────────┴───────────────┘
```

**Root view** (breadcrumb `Lab` only): folders `news_shock`, `crypto`, `stablecoin`, `research_panels`, `connections`, `procured`, `markets` — same row/toolbar grammar.

---

## CLUSTER

Coverage canvas — **not** a file list. Entry: Profile pins, Library shift-select (2), or Detail “See on Cluster”.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RD · [ Search lab + discover ⌘K ] · [New ▾] · YZ ▾                           │
├──────────┬───────────────────────────────────────────────────┬───────────────┤
│ Home     │ Cluster                                           │ Detail | Ask  │
│ Library  │ Compare: [GDELT Asia ▾] [Ticker week ▾] [+ Library] [Save compare]│
│●Cluster  │ 47 mapped · 3 gaps · overlap 82% on selected pair │ Overlap       │
│ Browse   │ Filter ▾ All · Asia · Crypto · Taiwan · NFT       │ GDELT × Ticker│
│ Resources│        2018      2020      2022      2024    now  │ [82% overlap] │
│ Profile  │ GDELT  ████████████████████████████████████████  │ COVERAGE both │
│ Settings │ Ticker ░░░░░░░░░░░█████████████████████████████  │ 2018–2026 ·   │
│          │ CoinG  ░░░░░░░░░░░█████████████████████████████  │ country·day   │
│          │ ── Venn ────────────────────────────────────────  │ GRAIN match   │
│          │   (GDELT Asia) ∩ (Ticker week) = 41,204 rows     │ JOIN date ·   │
│          │   only A: 9,102 · only B: 2,881 · neither: gaps  │ country_iso3  │
│          │ Missing coverage: TWSE · MOPS · Election events   │ Missing grain │
│          │ Join keys: date · country_iso3                    │ TWSE · MOPS   │
│          │ [Find in Browse] [Export join keys] [Open Library]│ [Expand overlap]│
│          │ click timeline gap → highlights missing span      │ [Ask about →] │
└──────────┴───────────────────────────────────────────────────┴───────────────┘
```

---

## BROWSE

Same list grammar as Library; external discovery + trust line per row.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RD · [ Search lab + discover ⌘K ] · 24 external · [New ▾] · YZ ▾             │
├──────────┬───────────────────────────────────────────────────┬───────────────┤
│ Home     │ Browse                                            │ Detail | Ask  │
│ Library  │ Discover datasets outside the lab vault           │───────────────│
│ Cluster  │ [ Discover datasets…  taiwan governance ]         │ TWSE OpenAPI  │
│●Browse   │ [ Discover datasets… ]  Source ▾  Filter ▾        │ twse_gov_panel│
│ Resources│ ≡ list   Name ▾   Relevance ▾                     │ [◌ External]  │
│ Profile  │ Profile boosts Taiwan · Asia rows (★)             │ SOURCE TWSE   │
│ Settings │ ────────────────────────────────────────────────  │ ACCESS API key│
│          │ 📄 TWSE OpenAPI governance panel    TWSE   —  ★  │ COVERAGE 2010+│
│          │    Taiwan listed cos · daily · TWSE terms           │ GRAIN sym·day │
│          │ 📄 SEC crypto enforcement filings    SEC    —     │ LICENSE TWSE  │
│          │    enforcement actions · JSON · US                  │ USE Taiwan EQ │
│          │ 📄 DataCite finance corpus           DC     2d    │ LIMITATIONS   │
│          │    DOI corpus · finance · global                    │ rate limits   │
│          │ 📄 Stablecoin BigQuery remote table   BQ     —     │               │
│          │    public dataset · transfers · on-chain            │ [Add to lab]  │
│          │ 📄 HuggingFace taiwan-equity         HF     1w    │ [Preview ext] │
│          │    community mirror · parquet · 2.1 GB              │ [Ask about →] │
│          │ ★ = boosted by Profile · After Add: toast + job   │               │
└──────────┴───────────────────────────────────────────────────┴───────────────┘
```

---

## RESOURCES

Ops ledger — full status board (not summary cards). Home strip = top WARN + running only.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RD · [ Search lab + discover ⌘K ] · [New ▾] · YZ ▾                           │
├──────────┬───────────────────────────────────────────────────┬───────────────┤
│ Home     │ Resources                                         │ Detail | Ask  │
│ Library  │ OK 11 · WARN 2 · FAIL 0 · updated 12s [Refresh]   │───────────────│
│ Cluster  │ ── Compute ─────────────────────────────────────  │ DataCite queue│
│ Browse   │ yzu-controller      UI · optiplex        OK       │ WARN · 4 wrk  │
│●Resources│ windows_lab pool    3/12 busy · scrape   OK       │ last err: …   │
│ Profile  │ job queue depth     2 running · 0 fail   OK       │ [View log]    │
│ Settings │ ── Storage ─────────────────────────────────────  │ [Retry]       │
│          │ GDrive vault        2.1/5 TB           OK       │ Related ds: — │
│          │ NVMe hot            68% used           WARN     │               │
│          │ USB bulk cache      mounted              OK       │               │
│          │ ── Data plane ──────────────────────────────────  │               │
│          │ Query :8765         128 ds · index 2h    OK       │               │
│          │ ── Remote query ────────────────────────────────  │               │
│          │ BigQuery SA         dry-run gate         OK       │               │
│          │ bytes scanned (30d) 12.4 GB                OK       │               │
│          │ ── Procurement ─────────────────────────────────  │               │
│          │ MCP tools           14 registered        OK       │               │
│          │ active sessions     1 composer           OK       │               │
│          │ ── Pipelines ───────────────────────────────────  │               │
│          │ GDELT backfill      18/99 mo             OK       │               │
│          │ DataCite harvest    4 workers          WARN       │               │
│          │ alpha-live timer    last 6h ago          OK       │               │
│          │ ── LLM desk ─────────────────────────────────────  │               │
│          │ llm_configured      deepseek reachable   OK       │               │
└──────────┴───────────────────────────────────────────────────┴───────────────┘
```

Row select → Detail with status, last error, log link, related `dataset_id` if any.

---

## PROFILE

Academic context — machine-readable scope for Browse ranking and Ask.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RD · [ Search lab + discover ⌘K ] · [New ▾] · YZ ▾                           │
├──────────┬───────────────────────────────────────────────────┬───────────────┤
│ Home     │ Profile                                           │ Detail | Ask  │
│ Library  │ Research context · ranking · procurement scope    │───────────────│
│ Cluster  │ Affiliation · Prof Kong · YZU · ORCID · Scholar   │ Track detail  │
│ Browse   │ ── Research tracks ───────────────────────────────  │ on row select │
│ Resources│ 1 Asia news-risk  2 Crypto/stablecoin  3 Taiwan EQ │               │
│●Profile  │ ── Corpus scope (holdings vs gaps) ───────────────  │               │
│ Settings │ Track          Holdings              Gaps           │               │
│          │ Asia news      gdelt_asia, news…    TWSE, MOPS      │               │
│          │ Taiwan equity  ticker_week          TWSE gov        │               │
│          │ Crypto         coingecko, usdt…      on-chain DEX    │               │
│          │ ── Pinned for Cluster ──────────────────────────────  │               │
│          │ gdelt_asia_daily      GDELT Asia panel      [Edit]  │               │
│          │ ticker_week_panel     Ticker week panel     [Edit]  │               │
│          │ [Edit tracks] [Sync Scholar] [Export scope JSON]    │               │
└──────────┴───────────────────────────────────────────────────┴───────────────┘
```

---

## SETTINGS

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RD · [ Search lab + discover ⌘K ] · [New ▾] · YZ ▾                           │
├──────────┬───────────────────────────────────────────────────┬───────────────┤
│ Home     │ Settings                                          │ Detail | Ask  │
│ Library  │ ── Account ── YZ · email · sign out               │───────────────│
│ Cluster  │ ── Credentials ─────────────────────────────────  │ Credential    │
│ Browse   │ BigQuery SA    ● configured  [Test]  OK 2s ago    │ test result   │
│ Resources│ GDrive OAuth   ● configured  [Test]  OK           │ on select     │
│ Profile  │ DataCite token ○ missing     [Add]                │               │
│●Settings │ ── Display ── Default tab: Library · On select: Detail│           │
│          │ ── Integration ─────────────────────────────────  │               │
│          │ Query engine :8765  [Test] [Open]                   │               │
│          │ Vite desk :5178     [Open]                          │               │
│          │ Admin · Workers · Jobs · Credential vault →         │               │
└──────────┴───────────────────────────────────────────────────┴───────────────┘
```

---

## PREVIEW (modal overlay — not a page)

CLI sketch below shows **Library with Quick Look open**. Preview is **not** sidebar tab 8 or a route — see [`V2_FORWARD_FROZEN.md`](V2_FORWARD_FROZEN.md) §Preview.

Modal overlay on Library (or Home/Browse with selection). Zones A + B + D stay mounted.

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ RD · [ Search lab + discover ⌘K ] · 12 in folder · [New ▾] · YZ ▾            │
├──────────┬───────────────────────────────────────────────────┬───────────────┤
│ Home     │ Lab › research_panels › gdelt          ░░░░░░░░░░░│ Detail | Ask  │
│●Library  │ ≡ list   Name ▾   Last modified ▾   ░ dimmed ░░│───────────────│
│ Cluster  │ 📄 Asia daily news-risk panel  ◀ selected ░░░░░░░│ Asia daily…   │
│ Browse   │ 📄 GDELT scored country panel      ░░░░░░░░░░░░░│ gdelt_asia…   │
│ Resources│ 📄 Cross-asset fused panel         ░░░░░░░░░░░░░│ [Query-ready] │
│ Profile  │ 📄 CoinGecko market archive      ░░░░░░░░░░░░░│ SOURCE GDELT  │
│ Settings │     ┌ Preview — Asia daily news-risk ───── [×] ┐ │ ACCESS :8765  │
│          │     │ [Preview] [Schema] [Query]   50 rows ▾   │ │ COVERAGE 2018 │
│          │     │ date       country  score  headline      │ │ GRAIN cty·day │
│          │     │ 2026-04-30 TW      0.82   export controls │ │               │
│          │     │ 2026-04-30 ID      0.71   central bank   │ │ [Preview]     │
│          │     │ 2026-04-29 SG      0.65   trade policy   │ │ [See Cluster] │
│          │     │ 2026-04-28 MY      0.59   palm exports   │ │ [Ask about →] │
│          │     │ Schema: date·country·score·headline·url    │ │               │
│          │     │ Query: SELECT * FROM gdelt_asia … LIMIT 50 │ │               │
│          │     │ [Open wide] [Export CSV] [Run on :8765]    │ │               │
│          │     └────────────────────────────────────────────┘ │               │
│          │ Esc closes modal · list selection kept              │               │
└──────────┴───────────────────────────────────────────────────┴───────────────┘
```

**Remote / BQ row:** Preview tab shows “Sample via dry-run” or disabled with link to Ask; Schema from registry either way.

---

## FLOWS

Closed loops (no wizard):

```text
FIND     Library breadcrumb / ⌘K / Browse discover box
UNDERSTAND  select row → Detail (auto) → read SOURCE…LIMITATIONS
USE      Detail [Preview rows] → modal → Schema / Query
GROW     Browse [Add to lab] → Ask prefilled → Resources job → Library folder

Library shift-select 2 datasets → Cluster Compare slots
Home WARN strip → Resources row → Detail log
Profile pin edit → Home Pinned + Cluster defaults
```

---

## Change control

Do **not** redraw wireframes in chat for routine work — update **this file** first, then `scripts/rd_layout_preview.py` if new sections need CLI listing.

Rejected patterns (do not reintroduce without explicit unfrozen decision):

- Partition domain chips (`Panels`, `News`, `Crypto`, `Stable`)
- `CatalogTable` visible label
- Location column + breadcrumb for same path
- Ask as sidebar tab or full-page route
- Left folder-tree rail (Explorer split pane)
- 8th sidebar tab for Preview
- HF-style card grid on Browse
- Forced Browse → Ask → Library stepper
