# Research Drive — Synthesis workspace freeze

**Status:** CURRENT VISUAL / INTERACTION IMPLEMENTATION AUTHORITY  
**Date:** 2026-08-13  
**Scope:** Synthesis entry, construction canvas, right-rail conversation,
cross-page return, and lifecycle presentation.  
**Preserves:** The truth, approval, revision, execution, archive,
registration, and readiness rules in
[`product/SYNTHESIS_S04_PRODUCT_SPEC.md`](product/SYNTHESIS_S04_PRODUCT_SPEC.md)
and [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md).

This document resolves an implementation-authority gap. It does **not** start a
new Synthesis design round.

## 1. What is binding

Two earlier documents describe complementary parts of the same finished
product design:

1. **S-04** defines the semantic construction canvas: research brief,
   recommended construction, evidence roles, limitation, expected output,
   resolved/deferred decisions, alternatives, and truthful execution outcome.
2. The **2026-08-11 agent-led workspace handoff** defines the interaction:
   one durable thread, conversation synchronized with the construction canvas,
   automatic evidence work, one consequential decision at a time, and an exact
   Discover/Library return loop.

They are adopted together. S-04 is not a second, competing page; its detailed
CLI wireframe is the visual composition of the agent-led construction canvas.
The August handoff is the operating model for that canvas.

Historical provenance: the August handoff was introduced as
`20bdda05e4acac6d22ac3df2ee839ddaec71d671` on the old convergence branch.
Its branch location does not reduce the design's authority here. Its old
component implementation is **not** a merge target.

## 2. Product experience

The researcher experiences one durable construction thread:

```text
research objective
→ agent grounds held Library evidence and named gaps
→ one recommended construction
→ one consequential researcher decision, when needed
→ revision-bound method acceptance
→ one material execution approval
→ verified registration and Library reuse
→ optional return through Discover or Library without losing the thread
```

The researcher never has to operate an internal transition merely to make the
system continue. Creating a thread, opening its attached conversation,
checking Library evidence, preparing a Discover handoff, refreshing a running
record, and returning to the source thread are system transitions. They are
visible, but not separate manual chores.

## 3. One canvas, one conversation, one lifecycle

The global shell remains:

```text
Navigation | Synthesis centre | Detail / Ask rail
```

The centre is one adaptive construction canvas. Ask is attached to the same
durable thread, not a disconnected chat. Detail reports selected-object truth.

There is exactly one researcher-facing lifecycle vocabulary after a
construction is accepted:

```text
Explore → Design → Test → Build → Registered → Reuse
```

Before acceptance, do **not** show a numbered wizard. Use `EXPLORATION READY`
or a precise active statement such as `Mapping Library evidence`. The phrases
`Interpret`, `Ground`, and `Challenge` may describe current agent activity in
plain language, but must not form a competing numbered process strip.

## 4. Canvas composition

### Entry and initial interpretation

The entry accepts one plain-language research objective, a registered method,
or a Library handoff. Submitting it creates the durable thread and opens Ask
with that exact objective attached.

The entry must communicate one promise and one primary action. It must not
present a passive four-step pseudo-wizard, an empty blueprint catalogue as the
dominant surface, or a required `+ New → another action` sequence.

Until structured interpretation arrives, the centre says only what is true:
the objective, that a durable thread exists, the current evidence pass, and
that nothing has been built or modified. It does not fabricate a research
brief, grain, coverage, or recommendation.

### Exploration and recommendation

Once the backend provides the relevant state, the canvas follows the S-04
composition in this order:

```text
EXPLORATION READY
RESEARCH BRIEF
RECOMMENDED CONSTRUCTION
  evidence roles and their convergence
  validation role, when declared
  ideal direct measure / gap, when declared
  expected output, when declared
AI HAS ALREADY RESOLVED
METHOD DESIGN WILL RESOLVE
WHAT HAPPENS NEXT
```

The evidence roles remain visible when a proposal exists. A proposal review
adds the exact change set and its revision-bound decision; it does not replace
the evidence architecture with a bare `input → transform → output` plumbing
diagram.

One recommendation is open by default. Alternatives are available only behind
`Compare alternatives` and only when the backend supplied real alternatives.

### Method, build, and reuse

An accepted method shows the actual execution specification and the single
researcher-facing material boundary, `Review & approve execution`. That action
may create or reuse the durable request, then opens the existing governed
approval review. The backend may retain internal request and pending-approval
states; they must not become two required researcher clicks.

The canvas distinguishes queued, running, archive checked, registered, and
query-ready states. `Open in Library` appears only after a registered output
exists. A registered output can later become input to another construction;
Synthesis is not a terminal workflow.

## 5. Cross-page continuity

- A named missing evidence item may open Discover only from an explicit,
  backend-declared handoff.
- Discover receives the thread's objective, required grain, evidence role,
  held inputs, and limitation boundary.
- Returning selects the exact originating Synthesis thread and preserves its
  canvas.
- A newly registered Library asset may trigger a **revision proposal**, never a
  silent mutation of an accepted method.

## 6. Truth rules

The canvas reads durable typed state. It must not infer a capability from a
title, use regexes to classify a gap, or fill an S-04 block with plausible UI
copy.

If a S-04 field has no durable source, either omit the optional block or label
it `Not recorded`; do not make an implied claim. In particular:

```text
proposed ≠ accepted
completed ≠ archive verified
archive verified ≠ registered
registered ≠ query-ready
```

## 7. Implementation and acceptance boundary

Implement this authority fresh on the release convergence line. Do not merge
the historical checkpoint (`722832a`) or transplant its broad source tree.

Required proof is a rendered desktop and mobile journey for:

1. objective entry → durable thread / attached Ask;
2. evidence mapping with a declared gap → Discover → exact-thread return;
3. recommendation with evidence architecture still visible;
4. revision-bound method review → one approval boundary;
5. queued/running/registered/query-ready truth distinctions;
6. Library reuse of a registered output.

The implementation is complete only when the rendered candidate conforms to
this document and the behavioural tests prove the same durable transitions.
