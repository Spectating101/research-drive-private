# Research Drive v2 — adaptive layout spec

**Viewport reference:** 1440×900 desktop (design ruler), but production sizing is adaptive.  
**Canon:** [`RESEARCH_DRIVE_UI_CANON.md`](../RESEARCH_DRIVE_UI_CANON.md)  
**Frozen wireframes:** [`WIREFRAME_V2_FROZEN.md`](WIREFRAME_V2_FROZEN.md)  
**Visual tokens:** [`TOKENS.md`](TOKENS.md)  
**Interactive ruler:** open [`references/layout-ruler.html`](references/layout-ruler.html) at **100% zoom** (browser width ≥ 1440px).

Legacy `src/styles.css` uses 240px sidebar / 332–430px rail / 64px header. V2 now uses a bounded proportion contract instead of a single hardcoded split.

---

## Shell grid (all pages)

The right rail remains the anchor. The sidebar and rail use bounded `clamp()` tokens, while the main work surface receives the remaining width and must not overflow.

| Zone | CSS variable | Size | Position |
|------|--------------|------|----------|
| **A** Header | `--rd-header` | **56px high** | `grid-row: 1; grid-column: 1 / -1` |
| **B** Sidebar | `--rd-sidebar` | `clamp(224px, 18vw, 280px)` desktop | col 1, row 2 |
| **C** Main | flex remainder | no horizontal overflow | col 2, row 2 |
| **D** Rail | `--rd-rail` | `clamp(360px, 30vw, 480px)` desktop | col 3, row 2 |

At the 1440×900 reference viewport, the current CSS resolves to roughly:

```text
1440 total width
├─ 259  sidebar (B)
├─ 749  main (C)
└─ 432  rail (D)

900 total height
├─ 56   header (A)
└─ 844  body row
```

```css
.rd-shell {
  display: grid;
  width: 100%;
  height: 100vh;
  grid-template-columns: var(--rd-sidebar) minmax(0, 1fr) var(--rd-rail);
  grid-template-rows: var(--rd-header) minmax(0, 1fr);
}
```

---

## Zone A — Header (56px)

| Element | x | y | w | h | Notes |
|---------|---|---|---|---|-------|
| Brand block | 18 | 0 | 200 | 56 | logo 34 + title |
| Search bar | 238 | 8 | min(520, 860−40) | 40 | centered in main column align: starts after sidebar |
| Account | 1404 | 10 | 34 | 34 | avatar circle, 18px from right |

Header grid: `sidebar token | adaptive search | meta | avatar`.

Padding: **0 18px** horizontal.

---

## Zone B — Sidebar

| Element | Size | Notes |
|---------|------|-------|
| Nav item | fills sidebar minus side padding × **36** | radius 18px, padding 0 13px |
| Nav gap | **2px** | between items |
| Side padding | **12px** | left/right |
| Section label | 10px caps, margin-top **18px** |

7 items + Settings last. No Ask item.

---

## Zone C — Main (860px wide)

### Shared anatomy

| Block | y offset from body top | h | x pad |
|-------|------------------------|---|-------|
| **PageHeader** | 0 | **72** | 28 |
| **Toolbar** (chips) | 72 | **44** | 28 |
| **Content** | 116 | **728** | 28 |
| Bottom breathing | — | 28px pad bottom | |

PageHeader: title **28px** / 600, subtitle **14px** muted, actions right **32px** buttons.

### Library — column widths (table inside 804px content = 860 − 56 pad)

**Navigation (frozen):** Drive grammar — breadcrumb + folders in list + drill-down. See [`WIREFRAME_V2_FROZEN.md`](WIREFRAME_V2_FROZEN.md). No partition chip row; no Location column duplicating breadcrumb.

Toolbar: `≡ list` · sort `Name ▾` · `Last modified ▾` · `Filter ▾` (readiness: Query-ready, Connected, …).

| Column | width | align |
|--------|-------|-------|
| Name | **minmax(220px, 1.6fr)** | left |
| Ready | **100px** | left |
| Coverage | **140px** | left |
| Source | **100px** | left |
| Updated | **88px** | left |
| Row height | **52px** | icon 32×36 + 2-line name |

Table card: border-radius **18px**, border 1px `#edf1f6`.

### Home — vertical stack

| Section | y | h |
|---------|---|-----|
| PageHeader | 0 | 72 |
| Command band | 72 | content-adaptive |
| Attention rows | after command | compact statement rows |
| Recent section head | after attention | **32** |
| Recent Drive list | after head | 2–5 rows |
| Running strips | after recent | compact status rows |
| Remaining | — | flex whitespace |

### Cluster — no table

| Section | h |
|---------|---|
| PageHeader | 72 |
| Domain filters | 40 |
| Timeline (coverage bars) | **~200** |
| **Venn overlap** (2–3 selected sets) | **~280** |
| Gap chips row | 48 |

**Venn panel** = set intersection (shared dates, countries, keys) + only-A / only-B columns.  
Computed from registry grain + partition manifests — not a decorative force graph.

---

## Zone D — Rail

| Block | h | Notes |
|-------|---|-------|
| **RailToggle** | **44** | Detail \| Ask segments |
| **Pane** | **800** | scroll |
| Detail actions | 40 | bottom sticky optional |

Toggle: full width minus **24px** pad (12 each side).

Detail field labels: 10px uppercase mono, 6px letter-spacing.  
Body text: 13px. Title: 17–18px.

---

## Preview modal (overlay — not a sidebar tab)

Triggered from Detail **Preview rows**. Current tab dims behind a centered panel (~720×560) or right drawer (~480px).

| Tab | Content |
|-----|---------|
| Preview | `GET /query/{id}?limit=10` table |
| Schema | grain + columns from registry + observed types |
| Query | SQL editor + Run (expand modal for wide results) |

Shell unchanged: sidebar, header, rail stay. Esc closes. No `view=analyze` route.

---

## Breakpoints (later)

| Width | Behavior |
|-------|----------|
| ≥1181 | Desktop clamps: sidebar 224–280, rail 360–480 |
| 761–1180 | Narrow desktop clamps: sidebar 204–232, rail 320–360 |
| <761 | Sidebar becomes horizontal sticky; rail stacks below main |

Ruler file is **1440 only** — measure at 100% zoom, but do not freeze production code to those exact widths.

---

## Page summary

| Page | C width usage | Table in C? |
|------|---------------|-------------|
| Library | Drive list with folders + datasets | Yes, primary |
| Home | Command band + attention rows + recent Drive list | Partial |
| Browse | Source/status search results | Yes |
| Cluster | Canvas | No |
| Resources | Section blocks | No |
| Profile | Sections | No |
| Settings | Forms | No |
| Preview modal | Overlay on Library | Preview table in modal |
