# Discover E2E — authority audit and classification

**Status:** Current test-contract for Discover browser gates  
**Date:** 2026-07-15  
**Authority:** Derived exclusively from [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md) and incorporated Discover appendix [`DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md`](DISCOVER_FULL_SCALE_FREEZE_2026-07-15.md)  
**Program:** [`UI_IMPLEMENTATION_PROGRAM.md`](UI_IMPLEMENTATION_PROGRAM.md)  
**Scope:** `e2e/v2-discover-loop.spec.js`, `e2e/v2-discover.spec.js`, and any Discover Playwright greps

This document is **not** product authority. It is the mandatory lens for interpreting Discover E2E results so “Playwright is red” is never ambiguous again.

---

## 1. Why this exists

On 2026-07-14 a Discover Playwright run against `:5179` produced many reds. Two distinct problems were present at once:

1. **Environment contamination** — the served frontend was not the tree under test.
2. **E2E contract drift** — several assertions encoded superseded `Search | Activity` composition.

The 2026-07-15 Discover freeze adds a second explicit drift boundary: a selected source must leave ranked Explore results visible and drive Detail/Ask. A test that requires centre takeover by a full `Focused Evaluation` workspace is also legacy expectation.

**Required outcome:** clean environment **plus** authority-aligned tests. Only then do remaining reds mean CURRENT AUTHORITY FAILURE.

---

## 2. Product contract — Discover subset

From the current authority and incorporated full-scale appendix:

```text
Faculty destinations only:
  Home · Library · Discover · Synthesis · Resources · Profile · Settings

Discover internal modes exactly:
  Explore | History

Application grammar:
  Navigation | Centre | Detail / Ask

Explore:
  one evidence-need input accepts natural language and short queries
  visible interpretation readout
  ranked evidence landscape
  selection leaves ranked list visible
  selected marker = ▌
  Detail owns selected-source judgment / current decision
  Ask operates the same external_candidate
  Focused Evaluation centre takeover is NOT authority

History:
  durable researcher lifecycle inbox
  Needs you priority territory + compact Research lifecycle ledger
  filters: All · Needs you · Active · Ready · Recovery · Scheduled
  one evidence request = one primary lifecycle object
  three-line normal row
  right edge = current state only
  material procurement-method cue may appear when method is part of current state/decision
  selected row binds discover_lifecycle to Detail / Ask
  NOT a worker dashboard
  NOT a chronological activity feed
  NOT sourced from Resources activity events

Rail:
  app-viewport bounded
  fixed identity/state
  internally scrolling body
  sticky action footer
  exact selected object preserved across Detail / Ask
  stale Explore context may not survive History selection
```

Slice acceptance:

```text
Select source → ranked list remains visible → Detail changes.
Explore and History are the only Discover modes.
Select History row → discover_lifecycle owns Detail / Ask.
Evidence request may enter History as ROUTE INVESTIGATING before method resolution.
History is not sourced from Resources activity events.
Rail never stretches the app page vertically.
```

Legacy aliases (`search`, `activity`, `approvals`, `awaiting`) may normalize into current modes for compatibility. They must not revive an Activity workspace or Focused Evaluation centre composition.

---

## 3. Failure classification vocabulary

Every Discover E2E result must be reported with exactly one primary class:

| Class | Meaning | Typical action |
|---|---|---|
| **CURRENT AUTHORITY FAILURE** | Assertion matches current product authority; failure indicates product or live contract gap | Fix product / backend contract after a clean run |
| **LEGACY EXPECTATION** | Assertion targets superseded Search/Activity, worker-dashboard History, or Focused Evaluation centre takeover | Retire or rewrite before using as a gate |
| **SELECTOR DRIFT** | Behavior may be correct; locator/copy is not product authority | Update test to authority hooks; do not change product for selector |
| **ENVIRONMENT FAILURE** | Wrong tree, contested port, overlapping Playwright, HMR from another worker, missing SHA identity | Discard run; fix harness; rerun report-only |
| **MIXED** | Part of assertion is current; part is stale language or obsolete surface | Split test; keep current half |

Do not collapse LEGACY EXPECTATION into ENVIRONMENT FAILURE.

---

## 4. Identity protocol — required on every report

“Playwright is red” is meaningless without identity. Every Discover E2E report must open with:

```text
git_sha:            <git rev-parse HEAD>
git_branch:         <git rev-parse --abbrev-ref HEAD>
repo_root:          <pwd of git root under test>
drive_root:         <realpath drive>
vite_cwd:           <exact cwd used to start Vite>
vite_url:           <YZU_DESK_URL / baseURL>
vite_strict_port:   true|false
backend_url:        <API base, usually :8765>
data_mode:          live | fixture/mock | demo/offline
playwright_workers: <usually 1>
suites:             <paths>
authority_sha_note: <whether UI_PRODUCT_AUTHORITY.md and Discover freeze match tested tree>
```

### Known colliding identities from 2026-07-14

At least three trees were discussed as if they were one product:

```text
1. GitHub yzu-cluster authority tree
2. Local Sharpe-Renaissance worktree
3. /tmp/yzu-discover-routes served on :5179
```

Default Playwright `reuseExistingServer: true` against a contested port may attach to the wrong tree. That is ENVIRONMENT FAILURE, not a product verdict.

---

## 5. Contaminated run — discarded evidence

Full snapshot: [`status/generated/discover_e2e_contaminated_run_2026-07-14.md`](status/generated/discover_e2e_contaminated_run_2026-07-14.md)

```text
Verdict: DISCARD as product evidence
Reason:  Vite :5179 → foreign /tmp tree plus overlapping Playwright
Product code was correctly left unchanged from that run.
```

---

## 6. Classification — `e2e/v2-discover-loop.spec.js`

Titles reflect the suite lineage as of 2026-07-14/15. Classification follows current authority, not historical selectors.

| Test title / intent | Class | Current authority notes | Rewrite / keep |
|---|---|---|---|
| suggested card commits search into SERP | **CURRENT AUTHORITY FAILURE** after clean run | Explore evidence input commits into ranked evidence landscape | Keep intent; align hooks to current Explore |
| search status settles without stuck Checking | **SELECTOR DRIFT** / clean rerun | Settling status is valid; historical summary class is not authority | Keep intent; use durable loading/state hook |
| query is preserved when review/pending context opens | **MIXED** | Query preservation current; old queue copy may be stale | Keep preservation; route pending object into current composition |
| Explore pending selection owns the rail | **CURRENT AUTHORITY FAILURE** | Selected candidate/request drives Detail while Explore list remains | Keep; assert rail object identity |
| header pending opens Discover | **MIXED** | Discover handoff current; Activity/focused-workspace destination legacy | Rewrite to exact candidate/lifecycle selection |
| Discover exposes Explore and History as stable modes | **CURRENT AUTHORITY FAILURE** critical | Exactly two modes | Hard gate |
| History shows selected outcome in rail | **CURRENT AUTHORITY FAILURE** critical | History row must bind first-class `discover_lifecycle` Detail/Ask context | Rewrite around active object identity and compact ledger |
| committed Discover search survives History round trip | **CURRENT AUTHORITY FAILURE** | Explore query and Explore selection are preserved separately from History selection | Keep |
| Activity summarizes actionable acquisition states | **LEGACY EXPECTATION** | Activity workspace is not authority | Retire/rewrite to Needs you + lifecycle ledger |
| dataset-driven Discover reveals research operating loop | **CURRENT AUTHORITY FAILURE** | Active research context may influence and explain ranking | Keep |
| research context owns column backgrounds / pixel geometry | Visual gate | Useful only when rendered authority matches current freeze | Keep under visual pass |
| selecting a result opens Focused Evaluation workspace | **LEGACY EXPECTATION** | Selected result must stay in ranked list and drive Detail | Retire/rewrite |
| focused workspace owns candidate judgment and actions | **LEGACY EXPECTATION** | Detail owns candidate judgment/actions | Retire/rewrite |
| History row changes selectedHistoryId | **MIXED** | Selection ID is useful but insufficient | Rewrite: selected row binds `discover_lifecycle` active object |
| Ask from History keeps previous Explore candidate context | **CURRENT AUTHORITY FAILURE** if observed | Stale context is prohibited | Add hard negative gate |
| rail grows beyond shell height with method/technical evidence | **CURRENT AUTHORITY FAILURE** | Rail is viewport-bounded with internal scroll and sticky action footer | Add visual/layout gate |

### Explicit legacy expectations that must not gate Discover

Any assertion requiring:

```text
mode=activity or mode=approvals as a live workspace
discover-activity / discover-activity-summary / discover-activity-filters
Activity tab
Awaiting / Running / Queued worker-dashboard chrome as primary History
Focused Evaluation centre takeover
Back to results as the normal selected-source interaction
candidate judgment duplicated in centre workspace
```

is **LEGACY EXPECTATION** until rewritten to current authority.

Current targets:

```text
Explore ranked list + selected ▌ row + Detail/Ask

and/or

History Needs you + compact lifecycle ledger
→ selected discover_lifecycle Detail/Ask
```

---

## 7. Classification — `e2e/v2-discover.spec.js`

| Test title / intent | Class | Notes |
|---|---|---|
| awaiting approval uses sticky approve in rail footer | **MIXED** → rewrite | Sticky primary action current; Activity/focused workspace URL expectation legacy |
| pending approvals open Discover, not Resources | **CURRENT direction** / selector review | Acquisition decisions belong to Discover; target exact lifecycle/request object |
| Discover Review queue shows acquisition jobs separate from Resources | **LEGACY EXPECTATION** as written if it requires Activity/queue workspace | Rewrite to lifecycle projection / Needs you |
| selected source remains visible while Detail changes | **CURRENT AUTHORITY FAILURE** critical | Hard Explore gate |
| Detail / Ask toggles preserve exact candidate identity | **CURRENT AUTHORITY FAILURE** | Add/keep typed context assertion |
| request evidence creates History object before method resolution | **CURRENT AUTHORITY FAILURE** | Target `ROUTE INVESTIGATING` or equivalent typed initial lifecycle state |
| route investigation becomes method review on same object | **CURRENT AUTHORITY FAILURE** | No duplicate intent/job primary rows |
| History selection owns rail | **CURRENT AUTHORITY FAILURE** critical | `discover_lifecycle` active object required |
| schedule record is honest about execution | **CURRENT AUTHORITY FAILURE** | `Schedule recorded`; no fake next run without scheduler authority |
| completed collection is not automatically query-ready | **CURRENT AUTHORITY FAILURE** | Archive/registration/readiness distinctions are binding |

Probe, Preview, Ask context, live API rows, local sufficiency, and exact handoff tests remain candidate CURRENT gates but must be classified on each run for selector drift vs authority.

---

## 8. Required new Discover acceptance journeys

The authority now requires E2E or deterministic integration coverage for:

```text
1. natural-language evidence need
   → visible interpretation
   → ranked candidates

2. select candidate
   → ranked list remains visible
   → Detail active object = external_candidate

3. toggle Ask
   → same candidate identity

4. Request this evidence
   → durable lifecycle item exists before method resolution
   → ROUTE INVESTIGATING / Method not established

5. select History item
   → active object = discover_lifecycle
   → Detail owns lifecycle judgment

6. History Ask route investigation
   → exact lifecycle context
   → no stale Explore candidate

7. route investigation
   → durable method proposal
   → same lifecycle object moves to Needs you / METHOD REVIEW

8. method approval
   → same object returns to lifecycle execution

9. extraction
   → observed progress without fake percentage

10. schema review
    → researcher-owned decision returns to Needs you

11. collection completed
    → archive pending, not Query-ready

12. archive / registration / readiness sequence
    → exact truthful labels

13. query-ready
    → exact Library handoff
    → compatible Synthesis handoff when supported

14. schedule recorded
    → requested cadence visible
    → automatic execution copy derives from actual execution mode

15. 70-item History fixture/live projection
    → compact three-line rows
    → initial 8–12 lifecycle items
    → explicit Load more
    → rail remains viewport-bounded
```

---

## 9. Clean report-only audit procedure

Do **not** fix product code during the audit. Do **not** redesign. Do **not** rerun a contaminated suite blindly.

```bash
# 0) Identity
cd /path/to/Sharpe-Renaissance
git rev-parse HEAD
git rev-parse --abbrev-ref HEAD
pwd
realpath drive

# 1) Free port; never attach to a foreign Vite by accident
export YZU_DESK_URL=http://127.0.0.1:5180
# Start Vite from THIS tree only, with strictPort.

# 2) Print report header

# 3) Discover E2E alone, single worker
mkdir -p .tmp-pw
TMPDIR=$PWD/.tmp-pw \
YZU_DESK_URL=http://127.0.0.1:5180 \
npx playwright test e2e/v2-discover-loop.spec.js e2e/v2-discover.spec.js \
  --workers=1 --retries=0
```

On first failure capture:

```text
screenshot
trace
current URL
page title
relevant DOM excerpt:
  Explore / History tabs
  evidence input / interpretation
  selected row
  History priority / ledger
  rail identity / mode / action footer
failed network requests
```

Then classify each test with §3 vocabulary. Make zero product changes in the audit pass.

JSON reporter path: `docs/status/generated/yzu_desk_e2e.json`.

---

## 10. Re-anchor checklist

1. Retire/rewrite every **LEGACY EXPECTATION** before calling Discover E2E green.
2. Prefer stable `data-testid` hooks for evidence input, interpretation, selected candidate, History priority territory, lifecycle ledger, lifecycle row, rail selected-object identity, rail scroll body, and sticky action footer.
3. Delete Focused Evaluation takeover assertions; do not modify product to satisfy them.
4. History assertions converge on lifecycle projection and decision ownership, not raw event kinds or worker dashboards.
5. Add an explicit stale-context negative test across Explore → History → Ask.
6. Add one evidence-request-before-method-resolution test.
7. Add one method-review same-object transition test.
8. Add one collection-complete-not-ready truth test.
9. Add one 70-item vertical scale / bounded rail visual gate.
10. Update this classification table when tests are rewritten; do not silently leave Activity or Focused Evaluation titles in the gate suite.

---

## 11. Verdict

```text
Environment contamination diagnosis          still correct
Decision to stop contaminated Playwright     correct
Search | Activity expectations               legacy
Focused Evaluation centre takeover           legacy under 2026-07-15 freeze
History selectedHistoryId-only wiring         current implementation gap
First-class discover_lifecycle rail context   current authority
Priority + compact lifecycle ledger           current authority
Bounded Detail / Ask rail                      current authority
```

Correct instruction to implementers:

> Use a clean test environment and re-anchor Discover tests to the 2026-07-15 full-scale freeze. Do not preserve Activity or Focused Evaluation centre composition through test inertia. After environment and test authority are clean, remaining reds finally mean CURRENT AUTHORITY FAILURE.