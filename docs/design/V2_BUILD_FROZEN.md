# Research Drive v2 — BUILD FROZEN (implementation authority)

**Status:** SUPERSEDED BUILD RECORD — product/composition authority moved to [`../UI_PRODUCT_AUTHORITY.md`](../UI_PRODUCT_AUTHORITY.md) on 2026-07-11  
**Supersedes:** ad-hoc CSS drift, duplicate row components, fixed-width shell experiments  
**Subordinate to:** [`RESEARCH_DRIVE_UI_CANON.md`](../RESEARCH_DRIVE_UI_CANON.md), [`../RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](../RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md), [`V2_FORWARD_FROZEN.md`](V2_FORWARD_FROZEN.md)  
**Companion:** [`LAYOUT_SPEC.md`](LAYOUT_SPEC.md), [`TOKENS.md`](TOKENS.md), [`UX_SPEC_MICRO.md`](UX_SPEC_MICRO.md)

---

## What we know

| Layer | Verdict |
|-------|---------|
| **Information architecture** | Correct — 7 tabs, Detail\|Ask rail, Preview modal, four loops |
| **Backend contract** | Correct — `src/v2/api.js` → `:8765` |
| **Visual execution** | Not institutional — hand-rolled CSS, 4 row patterns, raw errors, grid drift |
| **Path to parity** | Drive-list grammar + canon tokens + mock screenshot regression — **not** another IA pass |

Entry point: `index.html` → `src/v2/main.jsx`. Legacy: `index-legacy.html` only.

---

## Frozen decisions (do not re-litigate)

| Topic | Decision |
|-------|----------|
| Grid @ 1440 | Adaptive shell: sidebar/rail clamp tokens, main takes remainder, **56px** header |
| Typography | **IBM Plex Sans** + **IBM Plex Mono** — no Inter |
| Nav label | Tab id `browse`, label **Discover** (product rename; canon id unchanged) |
| Catalog rows | **`CatalogList` for Library/Home/Discover**; external Discover rows use source ribbons + procurement state pills |
| Detail rail | Uppercase mono field labels; CTAs at top; collapsible sections |
| Preview modal | Never show raw HTTP paths; offline → seed sample rows + banner |
| Demo data | `config/desk_demo_catalog.json` only — never vendor strings in React source |
| CSS strategy | Extend `v2.css` with tokens from mock until shadcn fork (Phase 4 optional) |
| Tests | `e2e/v2-parity.spec.js` + per-tab screenshot baselines |

---

## Build phases (execute in order)

### Phase 1 — Foundation (CURRENT)

**Exit:** Library + Home + Discover use Drive list grammar; grid matches `LAYOUT_SPEC` adaptive rail contract; Preview human errors; e2e green.

1. Canon tokens in `v2.css` (`--rd-sidebar` / `--rd-rail` clamp tokens)
2. `CatalogList` + `CatalogRow` for Drive rows, lab rows, and external source rows
3. Wire Library (breadcrumb + list), Home (recent list)
4. `PreviewModal` offline sample rows; rename "Run on :8765" → "Open query engine"
5. `DetailPanel` label typography per UX_SPEC_MICRO §1.4
6. Header offline chip (status pill, not bare link)

### Phase 2 — Discover + density (IN PROGRESS)

**Exit:** Discover results use shared list rows with source ribbons; empty states with copy; e2e `v2-discover.spec.js` green.

1. BrowsePage → `CatalogList` external rows
2. Sort chips functional on Library (name, readiness)
3. Row hover + keyboard focus rings

### Phase 3 — Main canvas depth

**Exit:** Cluster timeline + overlap in Zone C; Resources ledger table density.

1. Cluster: coverage bars + overlap summary in main (rail = detail only)
2. Resources: Grafana-style dense ledger (de-emphasize hero cards)
3. Profile: finished empty states

### Phase 4 — Component system (optional acceleration)

Per [`OSS_TEMPLATE_EVAL.md`](OSS_TEMPLATE_EVAL.md): shadcn-admin shell + TanStack Table — **only after** Phase 1–3 screenshot diff &lt; 10% on Library.

---

## Component contract

### `CatalogList`

```text
CatalogList {
  rows: FolderItem | DatasetItem[]
  selectedId?: string
  onSelectDataset(ds)
  onOpenFolder(folder)
  onDoubleClick?(ds)
}
```

**Library/Home row anatomy:** icon · title/subtitle · status pill.  
**Folder rows:** icon · folder name/subcount · count pill.
**Discover row anatomy:** source ribbon · title/description/subtitle · External/In lab/Queued pill.

### `PreviewModal`

```text
On query error:
  - If usingSeed: show preview_rows from catalog JSON + "Demo sample — connect :8765 for live data"
  - Else: "Preview unavailable" + [Retry] + [Ask about this]
Never display: "500 /query/..."
```

---

## Screenshot regression

| Baseline | Compare |
|----------|---------|
| `docs/design/references/desk-v2-1440.html` | `http://127.0.0.1:5178/?tab=library` @ 1440×900 |

Store captures in `e2e/screenshots/` (gitignored). Playwright visual test in Phase 2.

---

## Change control

1. Product / IA → canon + `V2_FORWARD_FROZEN.md`
2. **Build order / component contracts** → **this file**
3. Pixels only → `TOKENS.md`, `UX_SPEC_MICRO.md`

Amend this file before starting a new visual direction.
