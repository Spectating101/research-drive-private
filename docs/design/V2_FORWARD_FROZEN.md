# Research Drive v2 — forward plan (FROZEN)

**Status:** FROZEN — 2026-06-28  
**Purpose:** Single “how we go forward” doc — product frozen, implementation order, Preview contract, next step.  
**Do not:** Redesign in chat; amend authority chain below first.

---

## Authority chain

| Order | Doc | Role |
|-------|-----|------|
| 1 | [`RESEARCH_DRIVE_UI_CANON.md`](../RESEARCH_DRIVE_UI_CANON.md) | Product, composition, workflows, build order |
| 2 | [`RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](../RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md) | Right rail entity/context/backend contract |
| 3 | **This file** | Implementation forward plan + Preview contract + phase gates |
| 4 | [`V2_FRONTEND_BACKEND.md`](V2_FRONTEND_BACKEND.md) | How UI (:5178) proxies to API (:8765) |
| 5 | [`WIREFRAME_V2_FROZEN.md`](WIREFRAME_V2_FROZEN.md) | ASCII sketches + polish rules + ship checklist |
| 6 | [`LAYOUT_SPEC.md`](LAYOUT_SPEC.md) | Pixel zones (1440×900) |
| 7 | [`TOKENS.md`](TOKENS.md) | Colors / spacing only |
| 8 | [`OSS_TEMPLATE_EVAL.md`](OSS_TEMPLATE_EVAL.md) | Fork shadcn-admin + OM patterns |
| 9 | [`V2_BUILD_FROZEN.md`](V2_BUILD_FROZEN.md) | **Implementation freeze** — build phases + component contracts |
| 10 | [`UX_SPEC_MICRO.md`](UX_SPEC_MICRO.md) | Pixel + interaction detail |

CLI sketches: `python3 scripts/rd_layout_preview.py list`  
Legacy (cutover complete 2026-08-05; `src/main.jsx` and its UI contract are deleted)

---

## What we are building

A **lab research desk**: seven sidebar tabs, Drive-like list navigation in Library/Home/Browse, **Detail | Ask** in one right rail, **Preview as Quick Look modal** (not a page). The right rail is the selected-object and Composer integration anchor. Four loops must work: **Find · Understand · Use · Grow**. Good enough for a YZU professor desk — not enterprise catalog parity.

---

## Preview — implementation contract (NOT a page)

**Preview is UI state, not navigation.**

| Yes | No |
|-----|-----|
| `PreviewModal` portal on `AppShell` | Sidebar tab, route `/analyze`, `view=analyze` |
| Opens over current tab (Library usual) | Replaces ZONE C with preview content |
| Zones A + B + D stay mounted | Retire `rd-dataset-nav` full-page analyzer |
| Optional URL: `?dataset=id&preview=1` | `preview` as CLI “page” in product mental model |

### Triggers

| Source | Action |
|--------|--------|
| Detail `[Preview rows]` | Open modal, `mode=lab`, tab Preview |
| Library double-click row | Same |
| Home Continue `[Preview]` | Same |
| Browse `[Preview ext]` | Open modal, `mode=external` (metadata snippet only) |

Close: Esc, `[×]`, scrim click. Selection + Detail unchanged.

### Modal tabs (one body visible)

| Tab | Lab (`Query-ready` / `Connected`) | External (`Browse`) |
|-----|-----------------------------------|---------------------|
| **Preview** | `GET /query/{id}?limit=50` table | Publisher / format / size snippet from discover |
| **Schema** | Registry columns + types inferred from first preview row | From discover metadata |
| **Query** | Default SQL + `[Run]` → same query API | Disabled until **In lab** |

Errors: message + `[Ask about this]` — never silent empty.

### Component props (implement against this)

```text
PreviewModal {
  open: boolean
  datasetId: string | null
  mode: 'lab' | 'external'
  initialTab: 'preview' | 'schema' | 'query'
  onClose: () => void
}
```

Backend already used by legacy UI: `GET /query/{dataset_id}?limit=N` on `:8765`.

---

## Polish frozen for v2 (summary)

Full tables: [`WIREFRAME_V2_FROZEN.md` §Polish](WIREFRAME_V2_FROZEN.md).

- **Status pills:** `Query-ready` · `Connected` · `Remote` · `Queued` · `WARN` (same in list + Detail)
- **Browse rows:** `◌ External` · `✓ In lab` · `⟳ Queued` — tertiary actions differ per state
- **Detail rail:** full SOURCE→LIMITATIONS; zone D scrolls
- **Toasts:** Queued / Added / Failed with link to Resources or Library
- **Cluster:** Save compare → Home + Profile
- **Resources:** `[All] [WARN] [FAIL] [Running]` filter chips

---

## Component inventory (build once)

| Component | Zone | Notes |
|-----------|------|-------|
| `AppShell` | A–D grid | Hosts `PreviewModal` at root |
| `DeskHeader` | A | Search ⌘K, New ▾, account |
| `DeskSidebar` | B | 7 tabs — see nav IDs below |
| `CatalogRow` | C3 | Two-line row + status pill |
| `InspectorRail` | D | `RailToggle` + one visible pane |
| `DetailPanel` | D | Fixed field order §canon 4.2 |
| `AskRail` | D | Stream chat; context chip |
| `PreviewModal` | overlay | §above — not a route |
| `ToastHost` | overlay | Bottom-center |
| `EmptyState` | C3 / D | Per tab |

### Sidebar nav IDs (frozen)

`home` · `library` · `cluster` · `browse` · `resources` · `profile` · `settings`  

Labels: **Home · Library · Cluster · Browse · Resources · Profile · Settings**  
**Ask is never a sidebar item.**

Replace legacy `src/app/nav-config.js` (`Drive`, `Source`, `Pipeline`) when wiring v2.

---

## Build phases

### Phase 0 — Gate (done when design agreed)

- [x] Wireframes + canon + this forward doc frozen  
- [x] Preview = modal contract written  
- [x] Ship checklist (four loops + five gates)

### Phase 1 — Vertical slice (cutover done; polish in progress)

**Authority:** [`V2_BUILD_FROZEN.md`](V2_BUILD_FROZEN.md)  
**Run:** `npm run dev` → `/`  
**Code:** `src/v2/`

**Exit:** Ship checklist gates 1–3 pass; `CatalogList` on Library/Home/Discover; desktop grid aligns to `LAYOUT_SPEC` adaptive rail contract.

### Phase 2 — Grow loop

- Browse list + row states + Add to lab → Ask + toast → Resources stub row  
- `PreviewModal` `mode=external` for Preview ext  

**Exit:** Gate 4 pass.

### Phase 3 — Desk completeness

- Home, Resources (ledger + filters), Profile, Settings  
- Cluster canvas + Save compare  
- Schema + Query tabs in PreviewModal  

### Phase 4 — Cutover

- `VITE_UI_V2` default on; retire `main.jsx` analyzer route; update e2e contract  

**v2.1:** usage charts, grid view, mobile rail drawer, Preview expand-wide.

---

## Explicit non-goals (v2)

- Partition domain chips, left folder tree, Ask sidebar tab  
- HF card grid on Browse  
- Full Atlan lineage graph  
- Forced Browse → Ask → Library wizard  
- Reintroducing `magic_procure` / composite planner UI  

---

## Legacy vs v2 code today

| Path | State |
|------|--------|
| `src/main.jsx` | Live monolith; `rd-dataset-layout` = old full-page preview (replace) |
| `src/app/Desk*.jsx` | Partial shell; nav IA **not** aligned — update in Phase 1 |
| `:8765` query engine | Ready for Preview tab |

---

## Change control

1. Product / workflow → `RESEARCH_DRIVE_UI_CANON.md`  
2. Sketches / polish → `WIREFRAME_V2_FROZEN.md`  
3. Phases / Preview contract / next step → **this file**  
4. Tokens only → `TOKENS.md`
