# Discover Composition — visual notes (C1)

## Root cause (mobile 204 px)

`.rd-v2-shell.no-rail` sets `grid-template-columns: var(--rd-sidebar) minmax(0, 1fr)`.

At ≤760 px, `.rd-v2-shell` correctly becomes `minmax(0, 1fr)`, but `.rd-v2-shell.no-rail` is more specific and kept the sidebar-width first column. With `--rd-sidebar-min: 204px` (from the ≤1180 breakpoint), Focused Evaluation collapsed to ~204 px.

**Canonical fix:** inside `@media (max-width: 760px)`, override:

```css
.rd-v2-shell.no-rail {
  grid-template-columns: minmax(0, 1fr);
}
```

## Modes

| Mode | Shell | Main canvas |
|---|---|---|
| Browse (no selection) | `no-rail` — full width | Grouped source index |
| Focused Evaluation | `no-rail` unless Ask open | Evaluation workspace |
| Focused + Ask | rail visible for Ask only | Evaluation remains in main |

## Browse structure

Groups from D1 taxonomy only:

- **In your lab**
- **External candidates**
- **Needs access** (`manual_access` / `access_mode: licensed`)

## Screenshots

### 01 — browse awaiting
Empty Discover; no inspector column.

### 02 — browse grouped
Visibly contains all three group headings.

Needs Access fixture fields:

- `manual_access: true`
- `access_mode: "licensed"`
- `license: "commercial license"`

### 03 — focus before probe
External · Acquisition available in the wide workspace.

### 04 — focus after probe
Verified evidence in Focus (not a narrow rail).

### 05 — focus with Ask
Ask as supporting rail; evaluation remains primary.

### 06 — focus approval required
Collection status · Approval required in wide workspace.

### 07 — focus running
Same-state counterpart to lifecycle screenshot 05 (Running + stage).

### 08 — focus failed
Failed summary readable; not a giant red page.

### 09 — focus registration pending
Can I use this? · Not yet reusable. Not In lab / Query ready.

### 10 — focus registered
Can I use this? · Registered in lab. Open in Library. Not Query ready.

### 11 — focus query ready
Can I use this? · In lab · Query ready. Open in Library.

### 12 — back projected
Back to Browse reveals lifecycle-projected row/counts.

### 13 — tablet running
Wide workspace coherent at 900 px.

### 14 — tablet failed
Failure readable on tablet.

### 15 — mobile browse
Browse uses full viewport width.

### 16 — mobile query ready
Focused workspace width ≥ 380 px; scrollWidth ≤ viewport; decisions do not contradict.

## Scope

- Desktop Composition not redesigned
- Sufficiency / Equivalence not started
- Final Responsive not started
