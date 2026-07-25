# Sol live-review lane

## Authority

- Live review URL: `https://previous.easycamp.tech`
- Deployed frontend commit reported by operator: `dfd56da9994af9a0351da2af81b2f9135819059f`
- Review base: `2863b0e0b0bba09bfd514d6924da27a2ada691e9`
- Working branch: `sol/live-review`
- Draft evidence PR: `#58`
- Runtime is real and must be treated as read-only during review.

Git comparison shows the review base is four commits ahead of the deployed frontend and that the difference is confined to `e2e/professor-demo.spec.js`. The application source is therefore identical across the deployed and review commits.

## Review safety

The legacy `e2e/professor-demo.spec.js` is not safe for remote review because it can click **Add to lab** and **Approve**. It must not be run against the live review URL.

The dedicated lane uses:

```bash
npm run test:live-review
```

This command runs `e2e/live-review.spec.js` with `playwright.live-review.config.js` directly against the remote URL. The suite:

- permits `GET`, `HEAD`, and `OPTIONS` requests;
- permits only the required bootstrap POSTs to `/library/desk/session` and `/library/desk/warm`;
- suppresses Cloudflare Browser Insights `/cdn-cgi/rum` without treating it as Research Drive state;
- blocks and fails on every other non-read request;
- captures Home, Discover, Library, Resources, Profile, and Settings at 1440×900;
- checks selected-source Detail and the resting Ask shell without sending a message;
- checks for horizontal overflow and browser page errors;
- attaches a request audit to every scenario.

## Live execution result

GitHub Actions run `30166004352` completed successfully from commit `3320d9370615c7b0b8e468c5a5724af76976a009`.

Proven by the run:

- the public hostname resolved and returned successfully;
- Chromium loaded the real live frontend;
- all six scoped route scenarios passed;
- no Research Drive runtime mutation was attempted;
- no page-level JavaScript error was detected;
- no horizontal document overflow was detected at 1440×900;
- screenshots and the HTML report were uploaded as artifact `sol-live-review-30166004352`.

Synthesis was intentionally outside this review suite because the requested review scope covered Home, Discover, Library, Resources, Profile, and Settings.

## Live visual findings

### 1. Home is showcase-ready

The hierarchy is strong and immediately legible: Pick up dominates appropriately, Resource headroom is compact, Recommended evidence is understandable, and Recent trail creates a credible durable-work story. No urgent visual defect was observed in the captured frame.

### 2. Discover is the strongest demo surface, with two visible data-presentation defects

The stablecoin query returned real external catalogue candidates and preserved selected-source context into Detail / Ask. The overall ranking composition is effective.

Visible defects:

- external descriptions expose raw HTML fragments such as `<p>` and `</em>` instead of clean prose;
- duplicate or near-duplicate OpenAlex candidates can appear in the same result set.

Secondary polish issue: long Ask suggestion labels truncate heavily in the narrow rail.

### 3. Library deep-link state is contradictory

On the audited deep link, the main Library pane reports `0 datasets` and `No holdings in this branch`, while the Detail rail simultaneously presents `gdelt_asia_daily_country_panel` as selected and query-ready.

This is a material route/tree consistency defect or stale-selection defect. The selected object and the visible folder contents must agree before this deep link is used in a live demonstration.

### 4. Profile is visually strong

The Research memory, current research direction, works list, and Detail rail form a coherent faculty-facing page. It is one of the strongest finished surfaces in the captured build.

### 5. Resources is coherent but not showcase-friendly

The layout is readable, but the live frame foregrounds several negative states: `NOT OBSERVED`, `Not configured`, `Fleet pending`, and `Not reported`. These may be truthful, but Resources should not be a primary demo destination unless the presentation goal is operational honesty rather than polished capability.

### 6. Settings contradicts the global live state

The global header reports `Live registry`, while Settings reports `Desk API: demo`, `Health payload missing or degraded`, and `Research assistant: Needs setup`.

That contradiction is visible and should be resolved in health-state mapping or kept out of the showcase path.

## Source review findings

### 1. Profile search handoff is broken

In `drive/src/v2/App.jsx`, the `ProfilePage` `onSuggestSearch` callback calls `setSearchQuery(q)`, but the active Discover state setter is `setDiscoverSearchQuery`. A Profile **Search →** or linked-lab action can therefore raise a `ReferenceError` instead of opening Discover with the requested query.

Recommended bounded fix:

```diff
- setSearchQuery(q);
- setTab("browse");
- syncUrl({ tab: "browse", q });
+ setDiscoverSearchQuery(q);
+ goTab("browse");
+ syncUrl({ tab: "browse", q });
```

### 2. Home History links do not force History mode

`drive/src/v2/HomePage.jsx` labels Recent Trail destinations as **History →**, but its `View all` control and history rows call only `onGoTab("browse")`. The current Discover mode can remain Explore, so the destination label and resulting state can disagree.

Recommended bounded fix: route history-labelled controls through the existing Home attention/history handoff or add an explicit `onOpenHistory` callback that selects Discover History before navigation.

### 3. Existing live-demo test can mutate production state

`e2e/professor-demo.spec.js` contains paths that click **Add to lab** and **Approve**. This is valid for an intentionally controlled demo test, but not for the public review URL. The live-review lane isolates review from those mutations.

### 4. Parked affordances remain visible

The active-research dropdown marker and account avatar are buttons without connected overlays in this branch. This matches the stated decision to park account overlays. They should be treated as deferred affordances, not silently described as working controls.

## Recommended demo boundary

Use:

1. Home;
2. Discover stablecoin or another reliable external-source query;
3. selected-source Detail;
4. resting Ask context without sending a mutating request;
5. Library only through a verified shelf path whose visible contents match the selected dataset.

Avoid leading with Resources or Settings. Do not use the currently audited empty Library deep link until the folder/selection contradiction is corrected.

## Files added or changed

- `.github/workflows/sol-live-review.yml`
- `playwright.live-review.config.js`
- `e2e/live-review.spec.js`
- `package.json`
- `docs/status/generated/SOL_LIVE_REVIEW_LANE.md`

No private backend files, deployment pins, or live runtime state were changed.
