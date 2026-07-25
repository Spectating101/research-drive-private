# Sol live-review lane

## Authority

- Live review URL: `https://previous.easycamp.tech`
- Deployed frontend commit reported by operator: `dfd56da9994af9a0351da2af81b2f9135819059f`
- Review base: `2863b0e0b0bba09bfd514d6924da27a2ada691e9`
- Working branch: `sol/live-review`
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
- blocks and fails on every other non-read request;
- captures Home, Discover, Library, Resources, Profile, and Settings at 1440×900;
- checks selected-source Detail and the resting Ask shell without sending a message;
- checks for horizontal overflow and browser page errors;
- attaches a request audit to every scenario.

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

`e2e/professor-demo.spec.js` contains paths that click **Add to lab** and **Approve**. This is valid for an intentionally controlled demo test, but not for the public review URL. The new live-review lane isolates review from those mutations.

### 4. Parked affordances remain visible

The active-research dropdown marker and account avatar are buttons without connected overlays in this branch. This matches the stated decision to park account overlays. They should be treated as deferred affordances, not silently described as working controls.

## Execution limitation for this review session

The current reviewer execution environment has Chromium and Playwright but cannot resolve `previous.easycamp.tech` through DNS. No claim of live visual inspection or passing remote tests is made from this session. The source-equivalent review and safety lane were completed through GitHub; the command must be run from an environment that can resolve the public hostname.

## Files added or changed

- `playwright.live-review.config.js`
- `e2e/live-review.spec.js`
- `package.json`
- `docs/status/generated/SOL_LIVE_REVIEW_LANE.md`

No private backend files or runtime state were changed.
