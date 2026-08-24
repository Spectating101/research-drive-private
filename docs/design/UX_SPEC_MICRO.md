# Research Drive v2 — micro UX specification

**Status:** updated 2026-07-01  
**Authority:** Subordinate to [`RESEARCH_DRIVE_UI_CANON.md`](../RESEARCH_DRIVE_UI_CANON.md), [`V2_FORWARD_FROZEN.md`](V2_FORWARD_FROZEN.md), [`LAYOUT_SPEC.md`](LAYOUT_SPEC.md).  
**Implementation base:** [`OSS_TEMPLATE_EVAL.md`](OSS_TEMPLATE_EVAL.md) (shadcn-admin fork + OM patterns).

Pixel reference: [`references/desk-v2-1440.html`](references/desk-v2-1440.html) + [`references/desk-v2-1440.css`](references/desk-v2-1440.css).

---

## 1. Global shell (every tab)

### 1.1 Grid

| Zone | Size | Background | Border |
|------|------|------------|--------|
| A Header | 56px × full width | `#ffffff` | bottom `1px #edf1f6` |
| B Sidebar | `clamp(224px, 18vw, 280px)` desktop | `#f8fafd` | right `1px #edf1f6` |
| C Main | flex remainder | canvas `#f7f9fc` | none |
| D Rail | `clamp(360px, 30vw, 480px)` desktop | dark inspector surface | left divider |

Main inner card (`rd-v2-body-scroll`): white surface, `border-radius: 12px 12px 0 0`, `border: 1px solid #e2e8f0`, fills **all** remaining C height (`flex: 1; min-height: 0; overflow: auto`).

### 1.2 Zone A — Header

| Element | Spec |
|---------|------|
| Brand mark | 28×28px, `border-radius: 8px`, fill `#c49a6c`, initials `RD`, font 11px/700 |
| Brand text | "Research Drive", 14px/600, `#0f172a` |
| Search | max-width 520px, height 40px, `border-radius: 20px`, bg `#edf2fa`, placeholder "Search catalog or ask…", trailing `⌘K` 11px muted |
| Meta line | 12px `#64748b`, e.g. `142 datasets · vault synced 2h ago` — **not** a button cluster |
| Avatar | 34×34 circle, bg `#e8f0fe`, border `#c6dafc`, initials from email |

**Reject:** "New ▾" dropdown in v2.0 (mock has it optional; canon CTA lives in page headers).

**Search behavior**

| Input | Result |
|-------|--------|
| Typing | Filter in-place on Library/Browse if on those tabs; else no-op filter |
| Enter | Rail → Ask, prefill input, focus composer |
| ⌘K | Focus search; second ⌘K does not open separate palette (unlike stock shadcn-admin) |

### 1.3 Zone B — Sidebar

| Property | Value |
|----------|-------|
| Item height | 36px |
| Item radius | 18px (pill) |
| Padding | 0 13px |
| Font | 14px |
| Default color | `#334155` |
| Active | bg `#e8f0fe`, text `#174ea6`, weight 600 |
| Gap between items | 2px |
| Section padding | 14px 12px |

**Order (frozen):** Home · Library · Cluster · Browse · Resources · Profile · Settings

**Never:** Ask as nav item. No icons required v2.0 (text-only matches mock).

### 1.4 Zone D — Inspector rail

| Property | Value |
|----------|-------|
| Header height | 48px |
| Toggle | Segmented control "Detail" \| "Ask", height 32px, full width minus 16px padding |
| Body padding | 16px |
| Scroll | Body only; header sticky |

Both panes mounted; inactive pane `hidden` + `aria-hidden="true"` (preserve Ask thread scroll position).

---

## 2. Shared components

### 2.1 StatusPill

| Enum | Background | Text | Dot |
|------|------------|------|-----|
| Query-ready | `#ecfdf5` | `#059669` | 6px circle `#059669` |
| Connected | `#eff6ff` | `#2563eb` | `#2563eb` |
| Review | `#fffbeb` | `#d97706` | `#d97706` |
| Failed | `#fef2f2` | `#dc2626` | `#dc2626` |
| External | `#f1f5f9` | `#64748b` | none |

Pill: `font-size: 11px`, `font-weight: 600`, `padding: 2px 8px`, `border-radius: 999px`, uppercase label optional (prefer Title Case).

Position: directly under dataset title in Detail; inline in table column "Status" width 120px.

### 2.2 CatalogList row

| Column | Width | Content |
|--------|-------|---------|
| Icon | 32px | folder or dataset glyph |
| Name | flex | Primary 13–14px/500; subline `dataset_id` 10.5–12px mono `#64748b` |
| Status | auto | StatusPill or folder count |

| Property | Value |
|----------|-------|
| Row height | 44px (`--rd-row-h`) |
| Hover | `#f8fafc` |
| Selected | `#e8f0fe` left border 3px `#2563eb` |
| Checkbox | None in v2.0 |

Double-click dataset row → open Preview modal (lab datasets only). Folder rows drill into the branch.

### 2.3 DetailPanel field block

Field order **fixed** (Atlan-style):

1. Title + StatusPill  
2. Description (2–3 lines, clamp with "Show more")  
3. **SOURCE** — publisher, URI (external link icon 14px)  
4. **ACCESS** — local path / API route / credentials hint  
5. **LIMITATIONS** — bullet list max 4 visible  
6. **PARTITION** — grain, date range if known  
7. **JOIN KEYS** — monospace chips  
8. Actions row  

| Action | Style | Behavior |
|--------|-------|----------|
| Preview rows | Primary button | Opens Preview modal |
| Export CSV | Secondary outline | `GET /query/{id}` download |
| Add to lab | Secondary | Rail → Ask, prefill "Add {id} to lab…" |
| See on Cluster | Ghost link | Navigate Cluster with `?focus=` |

Empty field: show `—` in muted 13px — **only** when API null, not as default before load.

**Loading:** skeleton 3 lines in field area; never flash `—` then populate (use suspense per field group).

### 2.4 EmptyState (rail)

Centered in rail body when no selection:

| Element | Spec |
|---------|------|
| Icon | 40px muted folder-outline |
| Title | 14px/600 "No dataset selected" |
| Body | 13px `#64748b`, max-width 260px, center |
| Hint | "Select a row in the catalog" |

Same component on every tab.

### 2.5 FilterChips (C2)

| Property | Value |
|----------|-------|
| Height | 28px |
| Radius | 14px |
| Gap | 6px |
| Active chip | bg `#e8f0fe`, border `#bfdbfe` |
| Inactive | bg `#fff`, border `#e2e8f0` |

Horizontal scroll with fade mask if overflow; no wrap.

---

## 3. Tab-by-tab

### 3.1 Home

**C1 PageHeader**

| Element | Copy |
|---------|------|
| h1 | "Home" |
| lead | "Continue research and inspect live procurement state." |

**C3 sections (top → bottom)**

1. **Command band** — selected/current dataset plus Library, Discover, Resources actions  
2. **Attention** — Library / Discover / Resources rows  
3. **Recent datasets** — CatalogList, 2–5 rows, "See Library" → Library  
4. **Running jobs** — compact status strips, WARN tint if approval/stall  

**Rail on enter:** preserve last Detail/Ask mode.

### 3.2 Library

**C1:** h1 "Library", lead "Faculty vault, query readiness, and procurement memory."

**C2 chips:** All · Query-ready · Connected · Review · `{folder}`

**C3 layout (two-column optional)**

One scrollable Drive list: folders and datasets share the same row primitive.

**Breadcrumb** above list: `Lab / research_panels / gdelt` 13px, clickable segments.

### 3.3 Cluster

**C3:** React Flow canvas, min-height 400px, dots background `#f1f5f9`.

| Node type | Shape | Label |
|-----------|-------|-------|
| Dataset | rounded rect 160×56 | name + grain subline |
| Overlap | diamond 80×80 | "N shared keys" — **only if computable** |

**Honesty rule:** If join keys unknown, show dashed edge "unknown overlap" — never fake %.

Selecting node → Detail with JOIN KEYS focused.

### 3.4 Browse

Same `CatalogList` row grammar as Home/Library, with the left icon slot replaced by a source ribbon. Row anatomy: **Source ribbon** · **Dataset title/description/subtitle** · **Status**.

Rows: left ribbon 3px `#94a3b8` for external.

Detail actions: **Add to lab** (primary), **Preview ext** (opens modal `mode=external`).

Queued procure: chip on row "Queued" `#fffbeb` from jobs API.

### 3.5 Resources

**No cards.** Single scrollable ledger, `SectionBlock` per domain:

| Section title | Row format |
|---------------|------------|
| Compute | `name · value · status badge` |
| Storage | name + `Progress` bar (used/total) + WARN if &lt;10% free |
| Data plane | `:8765` reachability dot 8px green/red |
| Jobs | table: id truncated, type, started, status |

Refresh: chip in C2 "Refresh" → spinner 1s on icon, refetch `/library/ops`.

### 3.6 Profile

CV tone. Sections:

1. Affiliation block (text only)  
2. Research tracks — numbered list editable  
3. Corpus scope table — columns: Track, Holdings, Gaps  
4. Pinned corpora — editable `dataset_id` table  

No avatar upload. Actions: Edit tracks, Sync Scholar (disabled if no creds), Export scope.

### 3.7 Settings

Form sections: Email (maps `procure_user_email`), Notifications toggle, API keys summary (masked), link "Open procurement credentials doc".

On email save: toast "Profile context updated" 3s bottom-center.

---

## 4. Ask rail (micro)

| Element | Spec |
|---------|------|
| Thread area | flex 1, overflow-y auto, padding-bottom 8px |
| User bubble | bg `#e8f0fe`, align right, max-width 85%, radius 12px 12px 4px 12px |
| Assistant bubble | bg `#f1f5f9`, align left, radius 12px 12px 12px 4px |
| Streaming cursor | 2px blink in assistant bubble |
| Composer | textarea, min-height 80px, max 160px auto-grow, border `#e2e8f0`, radius 8px |
| Send | icon button 36px, disabled when empty or streaming |

**Job approve card** (inline in thread): title, job id mono, `[Approve]` `[Dismiss]` — calls existing approve API.

**Errors:** red banner inside thread, not toast-only: "Chat unavailable — check :8765" + `[Retry]`.

Keyboard: ⌘↵ send, Esc blurs composer (does not close rail).

---

## 5. Preview modal (Quick Look)

| Property | Value |
|----------|-------|
| Overlay | `rgba(15,23,42,0.4)` |
| Panel | max-width 960px, max-height 85vh, centered, radius 12px |
| Header | dataset name + StatusPill + `[×]` |
| Tabs | Preview \| Schema \| Query — height 40px underline active |

**Preview tab:** table max 50 rows, sticky header, mono 12px cells, horizontal scroll.

**Schema tab:** two-column field/type table from registry.

**Query tab:** SQL textarea prefilled; `[Run]` disabled for `mode=external`.

Close: Esc, ×, scrim click. URL optional `?preview=1&dataset=`.

---

## 6. States matrix

| State | Shell | C3 | Rail |
|-------|-------|-----|------|
| Initial load | skeleton header meta | table skeleton 8 rows | EmptyState |
| API down | banner below header amber "API unreachable" | empty with retry | Ask shows connection error |
| No datasets | meta `0 datasets` | EmptyState "Vault empty" + Browse CTA | EmptyState |
| Row selected | unchanged | row highlighted | Detail populated |
| Preview open | dim main optional 0.02 | unchanged | unchanged behind modal |
| Streaming Ask | unchanged | unchanged | composer disabled |

---

## 7. Motion

| Interaction | Duration | Easing |
|-------------|----------|--------|
| Rail toggle | 150ms | ease-out |
| Modal open | 200ms scale 0.98→1 + fade | ease-out |
| Row select | 0ms (instant bg) | — |
| Toast | slide up 200ms, dwell 3000ms | ease |

No parallax. Respect `prefers-reduced-motion`: disable scale on modal.

---

## 8. Typography

| Role | Font | Size / Weight |
|------|------|---------------|
| Page h1 | IBM Plex Sans | 22px / 600, letter-spacing -0.02em |
| Lead | IBM Plex Sans | 13px / 400 muted |
| Body | IBM Plex Sans | 14px / 400 |
| Mono ids | IBM Plex Mono | 12px |
| Table header | IBM Plex Sans | 12px / 600 uppercase optional |

Load from Google Fonts or self-host; fall back system-ui.

---

## 9. Accessibility

| Requirement | Implementation |
|-------------|----------------|
| Focus ring | 2px `#2563eb` offset 2px on all interactive |
| Rail toggle | `role="tablist"`, `aria-selected` |
| Modal | focus trap, restore focus on close |
| Table | `aria-selected` on row |
| Status | not color-only — pill includes text label |

Target: WCAG 2.1 AA contrast on text/background pairs in tokens.

---

## 10. User scenarios (acceptance)

### S1 — Professor finds GDELT panel

1. Lands Home → clicks Library  
2. Tree shows `research_panels/gdelt` expanded  
3. Clicks row → rail flips Detail, fields populated  
4. Preview rows → modal 50 lines  
5. Esc → back to list, selection kept  

### S2 — Procure external dataset

1. Browse → search "ocean temperature"  
2. Select hit → Detail shows SOURCE  
3. Add to lab → Ask prefilled  
4. Send → stream response + job card  
5. Approve → Resources shows running job  

### S3 — Check vault headroom

1. Home strip shows WARN storage  
2. Resources → Storage section bar yellow  
3. No navigation to fake "upgrade" CTA  

### S4 — Cluster honesty

1. Select two datasets with known `join_keys`  
2. Edge label shows key names  
3. Third dataset without keys → dashed edge, no %  

---

## 11. Anti-patterns (lint in review)

- [ ] Ask in sidebar  
- [ ] Preview as route/tab  
- [ ] Vendor names in React source seed data  
- [ ] Fake overlap percentages  
- [ ] Different Detail field order per tab  
- [ ] Card-grid Browse layout  
- [ ] Legacy `styles.css` / `drive-visual.css` on v2 entry  
- [ ] Hero metrics on Resources without API backing  
