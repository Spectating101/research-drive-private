# Research Drive Competitive UI — Handoff

**Date:** 2026-07-10  
**Workspace:** `Sharpe-Renaissance/drive`  
**Primary live route:** `http://127.0.0.1:5179/?tab=browse&dataset=gdelt_asia_daily_country_panel`  
**Status:** Historical implementation handoff; superseded for future UI decisions by `docs/UI_PRODUCT_AUTHORITY.md` on 2026-07-11  
**Commits created:** None  

## 1. Objective

Move Research Drive from a functional dataset browser toward a competitive institutional research-data operating system without replacing the working shell, procurement backend, or right-rail interaction model.

The approved product loop is:

```text
Find -> Verify -> Acquire -> Archive -> Register -> Query -> Synthesize -> Reuse
```

The intended competitive combination is:

- Google Dataset Search-level immediate comprehension.
- Atlan-level trust and visual polish.
- DataHub-level entity/rail consistency.
- Dagster/DERIVA-style execution history and provenance.
- Research Drive's unique source-to-vault procurement and reuse loop.

## 2. Product and visual decisions

### Interaction model

Preserve:

- Existing global header and sidebar.
- Home, Library, Discover, Synthesis, Resources, Profile, Settings.
- One persistent right rail with `Detail | Ask`.
- Preview as modal state.
- Existing procurement backend and job approval model.

Discover now has three stable modes:

```text
[ Search ] [ Activity · N ] [ History ]
```

- **Search:** local-first dataset and source discovery.
- **Activity:** present-tense acquisition control.
- **History:** append-only research and procurement memory.

### Visual direction

Selected style: **institutional instrument**.

Principles:

- Editorial authority for research objects.
- Precise data controls rather than marketing presentation.
- Evidence navy, action cobalt, verified emerald, warning amber.
- Serif page/object titles plus IBM Plex controls and monospace identifiers.
- No purple AI theme, decorative charts, oversized marketing hero, or generic operations dashboard.

## 3. Implemented frontend work

### 3.1 Discover Search / Activity / History

Implemented:

- Stable Search, Activity, History mode tabs.
- URL support for `mode=history`.
- Discover search query now persists as `q=` in the URL.
- Search query survives Activity/History round trips.
- Activity summary:
  - Awaiting.
  - Running.
  - Queued.
  - Failed in the last seven days.
- New History panel sourced from existing desk activity events.
- History filters:
  - All.
  - Search.
  - Probe.
  - Query.
  - Procure.
  - Registered.
- History event selection updates the right rail.
- History rail shows:
  - Event evidence.
  - Session/job/dataset identifiers.
  - Outcome.
  - Search -> Verify -> Acquire -> Archive -> Register chain.
- Structured rail context support for `history_event`.

New component:

- `drive/src/v2/DiscoverHistoryPanel.jsx`

Modified:

- `drive/src/v2/App.jsx`
- `drive/src/v2/BrowsePage.jsx`
- `drive/src/v2/DiscoverActivityPanel.jsx`
- `drive/src/v2/InspectorRail.jsx`
- `drive/src/v2/RailPanels.jsx`
- `drive/src/v2/activeObject.js`
- `drive/src/v2/railContext.js`

### 3.2 Research-context surface

The dataset-driven Discover default now exposes:

- Research context.
- Evidence and coverage.
- Find.
- Verify.
- Acquire.
- Synthesize.
- Suggested related searches.

The context rail now includes:

- Why this matters.
- Source confidence.
- Vault state.
- Next gap.

### 3.3 Home

Added a top-level Research Drive brief that communicates:

- Find.
- Verify.
- Acquire.
- Synthesize.

It uses live catalog counts and links directly into the existing pages. Existing Continue, Needs attention, Recent, and Suggested gaps remain below it.

Modified:

- `drive/src/v2/HomePage.jsx`

### 3.4 Library and dataset evidence

Dataset Detail now leads with:

- Why this matters.
- Source confidence.
- Freshness.
- Coverage.
- Provenance.
- Vault path.
- Limitations.
- Next gap.

Modified:

- `drive/src/v2/DetailPanel.jsx`

### 3.5 Synthesis

Added an explicit four-stage synthesis model:

```text
Inputs -> Join / transform -> Coverage check -> Registered output
```

The component derives:

- Input sources.
- Join keys.
- Entity coverage.
- Gap count.
- Built/output status.

Modified:

- `drive/src/v2/SynthesisPage.jsx`

### 3.6 Institutional visual system

Applied:

- `Source Serif 4` for page/object titles.
- IBM Plex Sans and IBM Plex Mono for controls and identifiers.
- Paper canvas: `#F7F6F2`.
- Primary ink: `#172033`.
- Evidence navy: `#102A43`.
- Action cobalt: `#1B67D2`.
- Updated semantic ready/review/failure colours.
- Larger page title and lead typography.
- New Home brief, Research Context, Activity, History and Synthesis styles.
- Responsive layouts for the new surfaces.

Modified:

- `drive/src/v2/v2-base.css`
- `drive/src/v2/v2.css`

## 4. Discover crop bug: diagnosis and fix

### Symptom

At the supplied route, the middle Research Context component visually cropped:

- `GDELT Asia Daily Country News Shock Panel`
- Context explanation.
- Suggested query chips.

Evidence values were also invisible.

### Root cause

The dark background used a fixed gradient boundary at `54%`, but the actual first grid column occupied:

- Approximately 57% at 1366px.
- Approximately 60% at 1440px.
- Approximately 61% at 1920px.

White text extended beyond the dark gradient onto a white background and appeared cropped.

The inherited child grid also allocated `88px + 12px gap` inside evidence cells roughly 100px wide, leaving every `<dd>` with `0px` usable width.

### Fix

- Removed the fixed background gradient.
- Assigned navy directly to the left grid child.
- Assigned white directly to the evidence child.
- Removed inherited 30px grid gap and outer vertical padding.
- Added explicit padding to each child.
- Added safe heading wrapping.
- Changed evidence cells to stacked label/value layout.
- Allowed evidence values to wrap normally.

### Playwright proof

Validated at:

- 1366 x 900.
- 1440 x 900.
- 1920 x 900.

Assertions cover:

- Zero grid gap.
- Zero outer padding.
- No gradient background.
- Correct navy child background.
- Heading remains inside its grid column.
- No heading overflow.
- Evidence values have usable width and no horizontal clipping.

Final screenshot:

```text
/tmp/rd-discover-context-fixed2.png
```

## 5. Live Playwright interaction evidence

Tested the supplied context route, then clicked:

```text
GDELT Asia News Shock
```

Observed:

- URL updated to:

```text
?tab=browse&dataset=gdelt_asia_daily_country_panel&q=GDELT+Asia+News+Shock
```

- 15 result rows rendered.
- One row auto-selected.
- Right rail updated to selected dataset comparison.
- No page errors.
- No horizontal overflow.

Interaction screenshot:

```text
/tmp/rd-discover-search-interaction.png
```

## 6. Tests added or changed

Modified:

- `e2e/v2-discover-loop.spec.js`
- `e2e/v2-home.spec.js`
- `e2e/v2-library.spec.js`
- `e2e/v2-parity.spec.js`
- `e2e/v2-synthesis.spec.js`

New behavior covered:

- Stable Discover modes.
- History rendering and rail selection.
- Search URL persistence.
- Activity state summary.
- Research operating loop visibility.
- Multi-resolution Research Context clipping.
- Evidence value visibility.
- Home capability brief.
- Library evidence/trust rail.
- Synthesis input-to-output chain.
- Institutional visual tokens and title hierarchy.

## 7. Verification completed

### Baseline before implementation

```text
npm run test:v2-mock -- --retries=0 --reporter=line
46 passed
```

### Focused post-change verification

```text
Discover mode/history tests:             4 passed
Dataset research-context test:           1 passed
Home + Library evidence tests:           2 passed
Synthesis flow test:                     1 passed
Institutional hierarchy test:            1 passed
Multi-resolution clipping regression:    1 passed
```

### Live render inspection

Rendered:

- Home.
- Discover context.
- Activity.
- History.
- Synthesis.

Observed:

- No JavaScript page errors.
- No document-level horizontal overflow at 1440px.

## 8. Current assessment

### Strongest areas

- Home now communicates the product loop immediately.
- Library and dataset rails expose substantially better trust and provenance.
- Search / Activity / History is a coherent and differentiated information architecture.
- The Discover clipping defect is fixed and guarded across resolutions.
- Live context-to-search behavior is working and shareable.

### Not complete

The following remain before calling the UI finished:

1. **Activity auto-selection**
   - Opening Activity directly can show an actionable job in the list while the rail remains empty.
   - Auto-select the highest-priority actionable job.

2. **History auto-selection**
   - Opening History directly leaves the rail empty.
   - Auto-select the newest event.

3. **History date grouping**
   - UTC date keys can produce two sections both labelled `Today` in UTC+8.
   - Group by one consistent local date key.

4. **Synthesis visual conflict**
   - The synthesis flow exists in the DOM and its focused test passes.
   - In the current live screenshot the flow container appears visually collapsed due to an unresolved CSS interaction.
   - Diagnose with computed layout before editing.

5. **Remaining legacy typography**
   - Some older rows and rail metadata remain very small.
   - Apply institutional hierarchy selectively; do not enlarge dense operational metadata indiscriminately.

6. **Full post-change regression**
   - The full 46-test v2 mock suite has not been rerun after all UI changes.

7. **Build and responsive verification**
   - `npm run build` has not been run after the complete change set.
   - Tablet and 390px mobile screenshots still require final review.

## 9. Recommended next sequence

Execute in this order:

1. Diagnose and fix the Synthesis flow visibility conflict.
2. Add Activity default job selection.
3. Add History default event selection.
4. Fix History local-day grouping.
5. Run focused Discover, Home, Library and Synthesis suites.
6. Run:

```bash
npm run build
npm run test:v2-mock -- --retries=0 --reporter=line
npm run test:discover-loop
```

7. Render these viewports:

```text
1440 x 900
1920 x 1080
1024 x 768
390 x 844
```

8. Review console errors, clipping, focus order and rail behavior.
9. Run a real non-mocked procurement golden path if safe.

## 10. Operational debt work completed in parallel

A separate Cursor Grok 4.5 pass addressed operations/backend status debt.

Completed:

- Distinguished lifetime job totals from actionable recent failures.
- Added SQL-backed status counts and semantics.
- Added recent failure/cancellation fields.
- Improved desk health/resource warnings.
- Fixed repo-root bootstrap for stale-job recovery and pending triage CLIs.
- Reclaimed disposable cache/log space:
  - NVMe approximately 32GB -> 40-41GB free.
- Reniced GDELT/gzip I/O work rather than killing it.
- Recovered stale running jobs: 0.
- Left pending approvals untouched.
- Deleted no research datasets.

Verification:

```text
tests/test_job_status_counts.py
tests/test_desk_resources.py
tests/test_desk_scale.py
tests/test_materialization_sync.py

13 passed
```

Report:

```text
docs/status/generated/ops_debt_remediation.json
```

Remaining operations work:

- Restart `:8765` when safe so the long-running process serves the new job-stat shape.
- Manually review approximately 10 pending approvals.
- Diagnose approximately 10 recent collection-queue failures.
- Review failed user units separately.

## 11. Guardrails

- Do not replace the global shell.
- Do not reintroduce a Python heuristic planner.
- Do not expose MCP/internal tool names to faculty.
- Do not auto-approve pending procurement jobs.
- Do not delete research data to reclaim local space.
- Do not turn Resources or Discover into generic metric dashboards.
- Keep Detail authoritative; Ask provides contextual reasoning.
- Continue test-first for behavior and regression fixes.
- Do not commit or push without explicit user instruction.

## 12. Important repository-state note

The repository already contained extensive uncommitted, deleted, symlinked and untracked work before this implementation. Many `drive/` and test paths appear untracked due to the ongoing repository split. Do not use destructive Git cleanup, reset, checkout, or broad staging commands.

Review exact paths deliberately and preserve unrelated user work.
