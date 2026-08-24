# Research Drive v2 — OSS template evaluation (fork, don’t reinvent)

**Status:** 2026-06-28  
**Authority:** Implements shell from frozen canon — does not change IA.  
**Companion:** [`UX_SPEC_MICRO.md`](UX_SPEC_MICRO.md) (pixel + interaction detail)

---

## Decision summary

| Layer | Recommendation | Why |
|-------|----------------|-----|
| **App chrome** | Fork **[satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin)** (Vite + React 19 + shadcn sidebar) | Already matches our stack (`vite`, `radix`, `tailwind` in `package.json`). Sidebar, ⌘K command palette, layout primitives, dark/light — production-grade without writing grid CSS. |
| **Design tokens** | Keep [`TOKENS.md`](TOKENS.md) + map into shadcn `globals.css` CSS variables | Canon colors (`--rd-*`) override shadcn defaults once; no second token system. |
| **Catalog table + rail** | **Patterns** from **[OpenMetadata UI](https://github.com/open-metadata/OpenMetadata/tree/main/openmetadata-ui)** (`EntityProfile`, search, tags) — **not** full OM fork | Best open-source Atlan-class asset profile + discovery UX. Apache-2.0. Too heavy to run whole product; **copy component shapes** into our `DetailPanel` / `CatalogTable`. |
| **Library folder tree** | shadcn **[CRUD File Manager block](https://www.shadcn.io/blocks/crud-file-manager)** + `react-arborist` or Radix **Tree** | Drive-like vault navigation without custom tree CSS. |
| **Data tables** | **TanStack Table v8** (shadcn `DataTable` recipe) | Sort, filter, row selection, virtual scroll for 500+ datasets. |
| **Cluster canvas** | **React Flow** (`@xyflow/react`) | Honest node/edge overlap map; not fake Venn percentages. |
| **Preview modal** | shadcn **Dialog** + **Tabs** + TanStack Table (50-row cap) | Quick Look overlay per [`V2_FORWARD_FROZEN.md`](V2_FORWARD_FROZEN.md). |
| **Ask rail** | shadcn **ScrollArea** + message list pattern from **Vercel AI SDK Chat** UI blocks (layout only — keep `/library/chat/stream` backend) | Do not fork a chat product; steal scroll + composer chrome. |
| **Resources ledger** | shadcn-admin **tables** + status badges; row semantics from **Grafana** / **Vercel Usage** screenshots | Dense ops board, not four hero cards. |

**Explicit reject**

| Candidate | Reject reason |
|-----------|---------------|
| Full OpenMetadata product | Java server, Elasticsearch, 130+ connectors — wrong backend; 6+ month integration |
| Refine.dev / React-Admin | CRUD admin generator; fights 7-tab desk + modal Preview + dual rail |
| Apache Superset UI | BI/chart-first; catalog rail is secondary |
| HuggingFace Hub skin | Wrong metaphor (model cards); Browse is list+detail like Google Dataset Search |
| Legacy `procure-ui-live` dark ops theme | Canon rejects as global skin |
| Continue hand-rolled `v2.css` grid | Already diverged from mock; shadcn `SidebarProvider` + inset layout is maintained |

---

## Competitor → OSS steal map

Reference board: [`references/README.md`](references/README.md)

| Competitor pattern | Tab | OSS source to fork/adapt |
|--------------------|-----|--------------------------|
| Atlan asset profile (tags, owner, tier, lineage link) | Library Detail | OM `EntitySummaryPanel` field order |
| Atlan certification pills | Library rows | OM `Tag` / `Tier` badge components |
| Google Dataset Search result list | Browse | shadcn `DataTable` + external source ribbon column |
| ResearchRabbit timeline | Cluster | Custom React Flow timeline lane (no OM) |
| Cite-Agent / set overlap | Cluster | React Flow `nodeTypes` for dataset sets |
| Cursor / Vercel usage dashboard | Resources | shadcn-admin table + `Progress` for quota bars |
| ChatGPT Memory settings | Profile | shadcn `Form` + editable table rows |
| macOS Quick Look | Preview modal | shadcn `Dialog` max-w-4xl, scrim `bg-black/40` |

---

## Fork procedure (minimal risk)

### Phase 0 — Branch layout (1 day)

```text
git checkout -b feat/desk-shadcn-shell
# Vendor shell only — do not copy shadcn-admin pages
cp -r vendor/shadcn-admin/src/components/ui → src/components/ui
cp vendor/shadcn-admin/src/components/layout → src/components/layout  # adapt names
```

Keep existing `src/v2/api.js`, `deskSession.js`, hooks — **swap presentation layer only**.

### Phase 1 — Shell parity (2–3 days)

1. Replace `App.jsx` grid with shadcn `SidebarProvider` + `SidebarInset`.
2. Map 7 nav items to `sidebarNav` config (same order as canon).
3. Zone D: adaptive rail token from `LAYOUT_SPEC.md` — right rail remains the anchor, but width is not fixed.
4. Header: brand | centered search (max 520px) | `N datasets` meta | avatar — match mock [`desk-v2-1440.css`](references/desk-v2-1440.css) lines 16–49.

### Phase 2 — Catalog components (3–5 days)

1. Port OM **read-only** profile field list into `DetailPanel` (SOURCE, ACCESS, LIMITATIONS, PARTITION, JOIN KEYS).
2. Keep `CatalogList` for Home/Library Drive rows; use TanStack only if Discover/source result sorting needs it.
3. Do not reintroduce a separate Library folder tree unless the Drive-list model fails a concrete workflow.

### Phase 3 — Modal + Ask (2 days)

1. `PreviewModal` on shadcn Dialog.
2. `AskRail` composer: textarea min-height 80px, send on ⌘↵.

### Phase 4 — Visual regression (1 day)

- Playwright screenshot diff: `desk-v2-1440.html` vs `index-v2.html` @ 1440×900.
- Threshold: layout zones ±2px; colors from tokens.

---

## License compatibility

| Project | License | Use |
|---------|---------|-----|
| shadcn-admin | MIT | Full fork of layout/components |
| shadcn/ui blocks | MIT (per block) | Copy into repo |
| OpenMetadata UI | Apache-2.0 | Adapt component **structure**; attribute in `NOTICE` if copying >50 lines |
| TanStack Table | MIT | Dependency |
| React Flow | MIT | Dependency |

---

## What stays ours (do not replace)

| Asset | Reason |
|-------|--------|
| `research_data_library_server.py` `:8765` | Backend contract frozen |
| `config/research_query_registry.json` | Dataset truth |
| `src/v2/api.js` endpoints | Already wired |
| IA: 7 tabs, Detail\|Ask rail, Preview modal | Product frozen |
| E2E `e2e/v2-parity.spec.js` | Layout contract tests |

---

## Demo data policy (post-fork)

| Environment | Data |
|-------------|------|
| Production UI | Live registry only — **no** `deskSeed.js` vendors |
| Playwright / offline | `config/desk_demo_catalog.json` loaded with banner `DEMO` |
| HTML mock | Static HTML — design reference only |

Never hardcode CoinGecko (or any vendor) in React source.

---

## Success metrics

1. Sidebar + header keep the 1440px mock rhythm without freezing production to one pixel split.
2. `CatalogList` for Library/Home/Discover and one `DetailPanel` across tabs.
3. Detail fields populated from `research_describe_dataset` — no `—` when API returns data.
4. `npm run test:v2-parity` green + new visual diff job &lt; 5% pixel delta on shell chrome.
