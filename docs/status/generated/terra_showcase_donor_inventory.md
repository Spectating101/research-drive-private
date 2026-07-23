# Terra → Showcase donor inventory

Showcase base: `255c061` on `feat/showcase-terra-port`
Terra tip: `c15d891` (`ui/cdf-rc21-hardening`)

## TAKE (surgical)

### c15d891 — fix(discover): exclude Ask telemetry from lifecycle trail
- drive/src/v2/DiscoverHistoryPanel.jsx

### 7794a9f — test(discover): keep raw search telemetry out of default trail
- e2e/v2-discover-loop.spec.js

### 097bf31 — fix(discover): prioritize durable history trail
- drive/src/v2/DiscoverHistoryPanel.jsx

### 69fa01a — fix(discover): preserve live search identities
- drive/src/v2/App.jsx
- drive/src/v2/BrowsePage.jsx
- drive/src/v2/discoverActions.js
- drive/src/v2/discoverAdapters.js
- drive/src/v2/discoverLiveSearchContract.test.js
- drive/src/v2/procurementJobs.js
- e2e/fixtures/v2MockApi.js
- e2e/v2-discover.spec.js
- package.json

### 62fdf12 — feat(discover): sharpen evidence and history states
- drive/src/v2/BrowsePage.jsx
- drive/src/v2/DiscoverComparePanel.jsx
- drive/src/v2/DiscoverEmptyState.jsx
- drive/src/v2/DiscoverHistoryPanel.jsx
- drive/src/v2/RailPanels.jsx
- drive/src/v2/discoverRailPresentation.js
- drive/src/v2/v2.css
- e2e/v2-discover-loop.spec.js
- e2e/v2-discover.spec.js

### 144f3f1 — feat(discover): carry live source and history truth
- drive/src/v2/App.jsx
- drive/src/v2/BrowsePage.jsx
- drive/src/v2/DiscoverHistoryPanel.jsx
- drive/src/v2/RailPanels.jsx
- drive/src/v2/api.js
- drive/src/v2/discoverAdapters.js
- drive/src/v2/discoverHistoryHandoff.test.js
- drive/src/v2/discoverHistoryTruth.test.js
- drive/src/v2/v2.css
- drive/tests/discoverAdapters.test.mjs
- e2e/v2-discover-loop.spec.js
- e2e/v2-discover.spec.js
- package.json

### 6769b75 — fix(ui): keep Home/Resources worker and receipt truth honest
- drive/src/v2/HomePage.jsx
- drive/src/v2/RailPanels.jsx
- drive/src/v2/ResourcesPage.jsx
- drive/src/v2/datasetMeta.js
- drive/src/v2/datasetMeta.test.js
- drive/src/v2/deskSourcesManifest.js
- drive/src/v2/homeBriefing.js
- drive/src/v2/homeBriefing.test.js
- drive/src/v2/resourcesFromRollup.js
- drive/src/v2/resourcesFromRollup.test.js
- drive/src/v2/resourcesSpending.js
- drive/src/v2/workersToolbarStat.js
- drive/src/v2/workersToolbarStat.test.js
- e2e/v2-resources.spec.js

### 33f7288 — fix(ui): tighten Library decision rail unknowns and restore FE regressions
- drive/src/v2/assetWorkspace.js
- drive/src/v2/assetWorkspace.test.js
- drive/src/v2/v2.css
- e2e/v2-home-library-resources-visual.spec.js
- e2e/v2-resources.spec.js

### e6915e9 — fix(ui): keep Library Detail as a compact decision instrument
- drive/src/v2/DetailPanel.jsx
- drive/src/v2/InspectorRail.jsx
- drive/src/v2/assetWorkspace.js
- drive/src/v2/assetWorkspace.test.js
- drive/src/v2/v2.css
- e2e/v2-home-library-resources-visual.spec.js
- e2e/v2-home.spec.js
- e2e/v2-library.spec.js
- e2e/v2-resources.spec.js

### 5b4c56d — feat(ui): refocus Home, Library, and Resources on observed research state
- .gitignore
- drive/src/v2/App.jsx
- drive/src/v2/AssetWorkspace.jsx
- drive/src/v2/DetailPanel.jsx
- drive/src/v2/HomePage.jsx
- drive/src/v2/InspectorRail.jsx
- drive/src/v2/LibraryPage.jsx
- drive/src/v2/ProcurementDecisionCard.jsx
- drive/src/v2/RailPanels.jsx
- drive/src/v2/ResourcesPage.jsx
- drive/src/v2/StatusPill.jsx
- drive/src/v2/assetWorkspace.js
- drive/src/v2/assetWorkspace.test.js
- drive/src/v2/datasetMeta.js
- drive/src/v2/datasetMeta.test.js
- drive/src/v2/discoverAdapters.js
- drive/src/v2/discoverHistoryHandoff.test.js
- drive/src/v2/discoverHistoryTruth.test.js
- drive/src/v2/discoverRailPresentation.test.js
- drive/src/v2/homeBriefing.js
- drive/src/v2/homeBriefing.test.js
- drive/src/v2/libraryIntakeCapability.js
- drive/src/v2/railContext.js
- drive/src/v2/railEmptyCopy.js
- drive/src/v2/v2.css
- e2e/fixtures/v2MockApi.js
- e2e/v2-home-library-resources-visual.spec.js
- e2e/v2-home.spec.js
- e2e/v2-library.spec.js
- e2e/v2-resources.spec.js

### e2f5451 — fix(ui): keep Home selection honest and trim follow-up e2e churn
- drive/src/v2/App.jsx
- drive/src/v2/v2.css
- e2e/v2-home.spec.js
- e2e/v2-resources.spec.js

### 7838e7c — fix(ui): send desk Bearer token and assert live faculty bind
- drive/src/v2/api.js
- drive/src/v2/deskSession.js
- e2e/v2-account-live-bind.spec.js

### f5eab7b — fix(cluster,ui): gate synthesis_execute live and lock pre-probe Add to lab label
- drive/config/yzu_cluster.json
- drive/src/v2/App.jsx
- drive/src/v2/RailPanels.jsx
- drive/src/v2/discoverAddToLabAction.js
- drive/src/v2/discoverAddToLabAction.test.js
- e2e/v2-discover.spec.js
- tests/test_synthesis_thread_state.py

## SKIP (parked)

ba1f4c9 feat(ui): hide Synthesis from Discover/Library release nav
cdf0531 fix(dev): allow custom comparison hostnames
5fece3e feat(ui): unify account overlays and resource activity rail
58df088 test(ui): expect compact workspace prefs from account menu
290d428 fix(ui): finish account overlays for research context and prefs
e80a182 docs(ui): point Settings comment at Research Context overlay
a08bc13 merge(private): reconcile unbound Profile honesty with account overlays
7a439cb fix(ui): move Profile and Settings into account overlays
1dd8939 fix(ui): recompose Profile and Settings interaction surfaces

## High-conflict files (do not wholesale take)
- drive/src/v2/App.jsx
- drive/src/v2/BrowsePage.jsx
- drive/src/v2/LibraryPage.jsx
- drive/src/v2/nav-config.jsx (hide Synthesis)

## Applied on feat/showcase-terra-port (this consolidation)

| Donor | Applied how |
|---|---|
| Ask/search telemetry out of default History | `historyNoiseFence.js` + `DiscoverHistoryPanel.jsx` Search chip |
| Desk Bearer + X-Desk-Token | `deskSession.js` (7838e7c) |
| Library rail unknowns tightening | `LibraryDatasetRailPanel.jsx` (33f7288 spirit) |
| Receipt-only readiness honesty | `datasetMeta.isReceiptOnlyAsset` |
| Home briefing / pending judgment | `homeBriefing.js` wired into `homeIteration10.buildPickUp` |
| Collectors toolbar honesty | `workersToolbarStat.js` wired into `ResourcesPage` |
| Hide-Synthesis switch parked | `releaseVisibility.js` with `SYNTHESIS_NAV_DEFERRED=false`; nav-config wired |
| Discover Detail rail always visible | `App.jsx` `hideRail=false` (Terra c15d891 shell contract) |
| History identity + holding truth | `discoverAdapters.js` + `enrichHistoryEventsFromJobs` in App; History Detail uses `historyHoldingTruth` |
| Receipt-only never Query ready | `historyLifecycleLabel.js` consults holding truth |
| Web hit candidate keys | `discoverActions.webHitsToRows` |

## Still parked

- Account overlays / Research Context overlay series
- Wholesale Terra `BrowsePage` / `App.jsx` / Library tree rewrite
- Discover live-search identity rewrite that requires BrowsePage surgery
