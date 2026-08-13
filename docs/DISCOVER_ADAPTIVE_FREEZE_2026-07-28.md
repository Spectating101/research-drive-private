# Research Drive — Discover adaptive freeze

**Status:** CURRENT FROZEN DISCOVER UX AUTHORITY  
**Date:** 2026-07-28  
**Authority:** Normative Discover appendix incorporated by [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md)  
**Scope:** `drive/src/v2/*`, Discover API projections, Detail / Ask integration, Discover tests, rendered review  
**Composition authority:** [`DISCOVER_VISUAL_STATES.md`](DISCOVER_VISUAL_STATES.md) — not this file's CLI drawings, not the withdrawn July 15 BEST FIT freeze.

This file freezes Discover **interaction and truth rules** approved on 2026-07-28. It does not restore the July 15 Explore wireframe. History/lifecycle rules that used to live in that freeze are in §9 of this file.

No component, screenshot, test fixture, earlier wireframe, backend table, or agent summary overrides this document.

---

## 1. Product thesis

Discover is the adaptive evidence-sourcing surface:

```text
ordinary keyword or shallow research question
→ immediate held + known-source results
→ progressive semantic / web enrichment when useful
→ contextual right-rail Ask for research questions
→ precise unresolved evidence gap
→ custom dataset strategy only when standard sourcing is insufficient
→ visual strategy review
→ approval-gated durable work
→ History
→ registered Library asset
```

Discover is not:

```text
a Library duplicate
a catalogue-only search page
a chat page
a workflow dashboard
a permanent planning canvas
a panel-construction surface
```

Synthesis constructs and reasons over research panels. Discover explains what evidence exists and how missing evidence can be obtained.

Frozen modes:

```text
Explore | History
```

There is no permanent Plan, Acquisition, Search, Ask, Activity, or Workflow mode.

---

## 2. One automatic composer

Explore has one input:

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Search datasets or describe what you are trying to study…      [→] │
└──────────────────────────────────────────────────────────────────────┘
```

There is no `Search | Ask` toggle.

On deliberate submit:

```text
always
→ run the fast held-evidence and known-source indexes
→ render results immediately

when the input expresses a research need
→ begin held-evidence assessment
→ open and seed right-rail Ask
→ enrich semantically / from web progressively when supported

when the input is an ordinary keyword
→ keep Ask quiet
→ retain explicit Search wider and Discuss results affordances
```

Intent detection must never delay first results. It may be deterministic first and model-assisted later.

Examples:

```text
stablecoin
→ ordinary search

stablecoin exchange volume
→ ordinary results; assessment may remain quiet

What data can I use to study stablecoin de-pegs?
→ same result surface + automatic assessment + seeded right-rail Ask
```

The user is allowed to begin shallow. Discover and Ask earn specificity progressively.

---

## 3. Explore result composition

The primary canvas shows evidence that can advance the need.

```text
query
result count + source scope
compact chrome
available external offerings
optional web / reference context
```

Held evidence does not consume a permanent result section. It is chrome:

```text
[Available · 3] [Library evidence · 12] [Web context · 4]
```

`Library evidence · N` opens an anchored popover containing a bounded preview and:

```text
Compare coverage
Open Library results
```

Normal external rows are compact:

```text
source ribbon    dataset / source title                       [Add]
description: what it contains
type · unit/coverage when declared · access/route state
```

Every result description must explain what the offering is and how it could be used. Raw HTML and Markdown are normalized before rendering.

The primary action is a small `Add to collection` control. It opens acquisition review; it never silently collects.

Selecting a row may support Preview or contextual explanation, but a dedicated selected-candidate centre page is not required and must not interrupt the result landscape.

---

## 4. Right-rail Ask

Ask is the existing right rail. It is not an alternate centre page or a second top-level composer.

For a research question, Ask is seeded automatically with:

```text
exact submitted question
current result snapshot
held-evidence assessment when available
named external offerings
known web/reference context
explicit unknowns
```

Ask:

```text
explains current evidence
asks only for context that changes the sourcing decision
updates the evidence requirement conversationally
distinguishes explicit, drafted, and unspecified details
may suggest a refined query
may open the custom-strategy modal
```

Ask never:

```text
silently changes results
silently selects a route
silently submits procurement
invents access, coverage, cost, readiness, or feasibility
```

Suggested search changes require an explicit action:

```text
[Apply to Discover] [Keep current results]
```

The minimum conversational brief may contain:

```text
research outcome
unit
universe / geography
period
frequency
fields or event type
```

These are not dumped into a permanent form. Ask requests only the unresolved dimensions that materially affect the strategy.

---

## 5. Custom strategy chrome

Custom strategy is compact toolbar chrome, never a permanent band or half-page panel.

States:

```text
[◌ Assessing strategy…]       muted; not ready
[○ Strategy needs context]    focuses Ask on missing context
[● Custom strategy ready]     accented; opens strategy modal
[✓ Strategy recorded]         opens the durable decision
```

The chrome appears only when assessment is relevant. It is absent for an ordinary keyword with adequate standard results.

The ready state requires backend-grounded or explicitly drafted support for:

```text
required output
precise standard-sourcing gap
proposed inputs
required transformations
remaining unknowns
next valid action
```

A joinable set of sources is not itself a coverage verdict. `Covered`, `Partially covered`, `Not covered`, and `Not yet recorded` remain distinct.

---

## 6. Concrete canonical journey

The canonical shallow question is:

```text
What data can I use to study stablecoin de-pegs?
```

Initial results may include:

```text
CoinGecko market history
BigQuery blockchain data
OpenAlex literature
held stablecoin incident evidence
relevant source documentation
```

Ask may clarify:

```text
Are you studying price response, exchange activity, or on-chain movement?
```

The researcher may answer:

```text
Daily volume across the major exchanges is enough.
```

Discover can then state:

```text
standard sources provide de-peg events, aggregate market history,
and on-chain transactions

still missing:
harmonized exchange-level daily volume
historical exchange/token identity
```

Only then may `Custom strategy ready` activate.

---

## 7. Visual custom-strategy modal

The strategy is a modal over preserved Explore results. It is not a Discover page.

The modal is diagram-first:

```text
intended dataset
→ how it answers the question
→ held inputs + proposed external inputs
→ normalize / transform
→ verify / register
→ source feasibility matrix
→ unknowns
→ next valid action
```

Canonical output:

```text
Stablecoin De-peg Exchange Activity Dataset

unit        exchange × stablecoin × day
period      2020–present
measures    price · volume · abnormal volume · event day
integrity   listing status and missing-period evidence
```

Canonical modal:

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Custom strategy · Stablecoin De-peg Exchange Activity Dataset            × │
├──────────────────────────────────────────────────────────────────────────────┤
│ WHAT YOU WILL GET                                                           │
│ exchange × stablecoin × day · planned fields and required coverage          │
│                                                                              │
│ HOW IT ANSWERS THE QUESTION                                                  │
│ de-peg occurs → exchange volume responds → response spreads or fades         │
│                                                                              │
│ HOW WE BUILD IT                                                              │
│                                                                              │
│ [held de-peg events] + [exchange history] + [identity/listing map]           │
│                                  ↓                                           │
│                       [collect + normalize]                                  │
│                                  ↓                                           │
│                     [research-ready dataset]                                 │
│                                  ↓                                           │
│                       [verify + register]                                    │
│                                                                              │
│ SOURCE CHECK                                                                 │
│ source       access       coverage         next check                        │
│ …            observed / proposed / unknown                                   │
│                                                                              │
│ STILL UNKNOWN                                                                │
│ [historical depth] [rate limits] [delisted pairs] [implementation effort]    │
│                                                                              │
│ NEXT VALID ACTION                                                            │
│ exact supported action; never a fabricated executable promise                │
│                                                                              │
│ [Refine in Ask] [Save strategy] [Next valid action]                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

`Refine in Ask` closes the modal and returns to the same investigation.

When source probes have run, the same modal updates its feasibility matrix. It may conclude that the plan is partially feasible or blocked. It must not preserve an attractive but disproven plan.

---

## 8. Acquisition review

`Add to collection` opens a compact review modal over results.

It states:

```text
what will be added
supported route
what the route requires
destination
refresh behavior
unknowns
next valid action
```

If multiple supported routes exist, comparison appears inside the modal. A route comparison is temporary decision support, not a mode or page.

Submitting creates a pending-approval durable object. It does not approve or start collection.

After submission:

```text
row state updates
History owns approval and lifecycle
completed ≠ archived ≠ registered ≠ query-ready
Library owns the resulting asset
```

---

## 9. History

History is the durable decision and lifecycle surface.

It preserves:

```text
exact question
evidence requirement
gap
Ask-derived context
strategy or selected route
approval
run and failures
archive proof
registry promotion
Library asset
```

Failed routes remain institutional evidence and inform later recommendations.

---

## 10. Non-negotiable truth rules

```text
registry membership ≠ Library possession
Library possession ≠ query-ready
declared route ≠ verified access
successful probe ≠ legal clearance
completed ≠ archive verified
archive verified ≠ registered
registered ≠ query-ready
proposed strategy ≠ executable strategy
```

Never fabricate:

```text
confidence scores
fit percentages
coverage percentages
costs
readiness
source reliability
probe results
implementation feasibility
```

---

## 11. Responsive behavior

Desktop:

```text
left navigation | Explore results | Detail / Ask rail
```

Mobile:

```text
single-column Explore
Ask opens as the existing bottom sheet
Library evidence opens as a popover/sheet
strategy and acquisition remain viewport-bounded modals/sheets
```

The first four external rows and their descriptions must remain readable without requiring horizontal scrolling.

---

## 12. Release acceptance

An implementation is conformant only when:

```text
Explore | History are the only Discover modes
one automatic composer; no Search | Ask toggle
keyword submission paints fast results without opening Ask
research-question submission paints the same results and seeds right-rail Ask
automatic assessment never blocks first results
Library evidence is compact chrome, not a permanent result section
external offerings remain the centre priority
every visible offering has a normalized description
Add to collection is a small row action and opens review
custom strategy is compact stateful chrome
strategy review is a visual modal over preserved results
no selected-candidate centre takeover is required
no mutation occurs without explicit review / approval
History preserves the complete decision chain
```

Required before production release:

```text
idle Explore
keyword → external results
question → same results + seeded Ask
Ask clarification → custom strategy ready
strategy modal → refine in Ask
row Add → acquisition review modal
submission → History
History → exact Library handoff
desktop and mobile
```

---

## 13. Do not reintroduce

```text
Search | Ask toggle in the centre
permanent held-evidence section
large custom-strategy band
selected-candidate centre page
full-page acquisition workspace
permanent route-comparison panel
Plan tab
workflow dashboard
AI canvas
silent search rewriting from Ask
silent procurement submission
generic “External · Available to inspect” for every source
```

---

## 14. Freeze statement

The frozen model is:

```text
ONE EXPLORE PAGE

automatic composer
→ immediate results
→ compact evidence chrome
→ automatic right-rail Ask for research questions
→ contextual clarification
→ compact custom-strategy state
→ visual modal
→ approval-gated History
→ Library handoff
```

Any change to this model must amend this file and [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md) before implementation.

---

## 15. Frozen rendered evidence and implementation boundary

The exact implementation reviewed in this slice is captured here:

- [question results + automatic Ask](status/generated/discover-freeze-2026-07-28/results.png)
- [visual custom-strategy modal](status/generated/discover-freeze-2026-07-28/strategy.png)
- [read-only live API question + progressive external results](status/generated/discover-freeze-2026-07-28/live-question.png)
- [acquisition review over preserved results](status/generated/discover-freeze-2026-07-28/acquisition-review.png)
- [mobile automatic Ask sheet](status/generated/discover-freeze-2026-07-28/mobile-question.png)
- [mobile question results after collapsing Ask](status/generated/discover-freeze-2026-07-28/mobile-results.png)

Implemented in this slice:

```text
one automatic composer
deterministic keyword vs research-question routing
fast results for both paths
automatic assessment + seeded right-rail Ask for questions
progressive semantic/web enrichment without clearing first results
external result priority and normalized descriptions
small Add to collection row action
Library evidence chrome instead of a permanent held-results block
compact strategy status chrome
diagram-first custom-strategy modal
acquisition review as a modal over preserved results
```

The live review artifact proves progressive external discovery, retained Library evidence, and automatic Ask selection. It does **not** prove a live assessment verdict or live `Custom strategy ready`: the public review endpoint rejects the required desk mutation. Those states are exercised only against the committed assessment contract and fixtures in this slice.

Still dependent on a mutation-capable backend or later lifecycle work:

```text
live assessment verdict and custom-strategy gating
Ask-authored requirement updates reflected in the strategy without reload
durable Save strategy action
complete source feasibility matrix after probes
History-to-Library proof chain for every route
production deployment
```

The remaining production-release journeys not demonstrated by these six captures are:

```text
Ask clarification → custom strategy ready against a mutation-capable backend
submission → History
History → exact Library handoff
```

These unfinished items do not authorize substitute pages, permanent panels, fabricated values, or a return to the Search | Ask toggle.

---

## 16. UX polish closure

The post-freeze interface audit is resolved as a bounded polish pass. It does not amend the composition in §14.

User-visible language now uses one possession boundary:

```text
in your Library
Beyond your Library
Library evidence
Library comparison
```

`lab`, `held`, and `local` remain valid internal data-model terms, but they are not competing user-facing names for the Library boundary on the adaptive Explore surface.

The result header now states one set and its useful partition:

```text
N results · X offerings available to add · Y results in your Library
```

Additional route-verification or reference counts appear only when those categories exist. The duplicate candidate total at the bottom of the list is removed.

Acquisition review follows these display rules:

```text
human offering and route titles in the primary reading path
technical identifiers behind a collapsed Technical details disclosure
no disabled Select route action before proposal review
Continue to route selection records the proposal but does not start collection
Collection / Boundary / Next replace the misleading Use now label
```

The custom strategy renderer is topic-agnostic. It binds its output title, unit, universe, period, and fields from the assessment requirement. Stablecoin values live in the committed visual fixture, not in production presentation logic.

Mobile acceptance is geometric, not screenshot-only:

```text
Research brief stacks above Filters at 390px
result rows remain inside the viewport with no horizontal document overflow
Resources, Profile, and Settings controls and icons do not overlap
the preserved Detail / Ask sheet remains independently collapsible
```

The deterministic capture journey is
[`e2e/discover-adaptive-freeze-screenshots.spec.js`](../e2e/discover-adaptive-freeze-screenshots.spec.js).
It regenerates the five fixture-backed artifacts listed in §15 with a question-specific grounded Ask answer. The live read-only artifact remains separately identified and is not represented as proof of mutation-backed assessment.
