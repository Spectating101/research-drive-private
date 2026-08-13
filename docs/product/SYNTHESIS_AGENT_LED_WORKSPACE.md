# Synthesis — agent-led construction workspace

**Status:** proposed interaction consolidation / implementation handoff  
**Date:** 2026-08-11  
**Relationship:** additive to [`SYNTHESIS_S04_PRODUCT_SPEC.md`](SYNTHESIS_S04_PRODUCT_SPEC.md); it does not replace S-04's truth, approval, or lifecycle contracts.

## Executive decision

Synthesis should be performed through one durable, agent-led construction thread with a live research canvas beside the conversation.

It should not feel like a wizard, a collection of disconnected pages, or a narrow chatbot attached to an admin console.

The researcher should state the desired research asset once. The agent should then inspect Library evidence, identify gaps, draft a defensible construction, route missing evidence to Discover when necessary, interpret results, and return to the same thread. The researcher intervenes only when a decision changes the meaning of the asset or causes a material side effect.

```text
one research objective
        ↓
durable thread is created automatically
        ↓
agent checks Library and existing context
        ↓
agent maps held evidence, gaps, and joinability
        ↓
agent drafts one recommended construction
        ↓
agent asks only the next consequential question
        ↓
method is reviewed and accepted
        ↓
execution is approved at the write boundary
        ↓
build → verify → register → Library
        ↓
the same thread can revisit Discover, Library, or the method
```

## Why the current surface feels manual

The underlying capability is coherent, but the current composition makes the researcher operate the state machine:

```text
+ New
→ create thread
→ open Ask
→ inspect evidence
→ select a gap
→ route to Discover
→ return to Synthesis
→ accept proposal
→ request execution
→ approve build
```

Most of those are system transitions, not research decisions. They should be automatic and visible as progress, not exposed as navigation work.

The current Synthesis page is therefore best understood as a trustworthy audit console. The target is an agent-led research workspace.

## Target mental model

The page has two continuously synchronized surfaces:

```text
CONVERSATION                         CONSTRUCTION CANVAS
what the researcher and agent say    what has become durable
                                     
clarifications                        research objective
interpretations                       held evidence
methodological choices                missing evidence
diagnostic explanations               proposed construction
                                     assumptions / limitations
                                     execution and registration state
```

The conversation is not disposable chat history. Every consequential turn may update the durable canvas, but only through explicit, revision-bound state changes.

The canvas is not a static diagram. It is the compact explanation of what the agent currently believes, what supports it, and what still needs a decision.

## One-page interaction model

There is no separate “new thread” page and no required “Discuss in Ask” step.

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ Synthesis · Weekly issuer attention panel                    Exploring      │
├──────────────────────────────────────────┬──────────────────────────────────┤
│ CONSTRUCTION CANVAS                      │ CONVERSATION                      │
│                                          │                                    │
│ Objective                                │ You                                 │
│ Weekly issuer attention panel            │ Build a weekly issuer attention    │
│                                          │ panel for Taiwan filings. Use      │
│ Evidence                                 │ existing evidence first.           │
│ ✓ 2 Library inputs                       │                                    │
│ ⚠ issuer filings not held                │ Agent                               │
│                                          │ I found two usable inputs. Exact   │
│ Recommended method                       │ issuer filings are missing. I     │
│ Weekly proxy using held signals          │ drafted a proxy and found one      │
│ Limitation recorded                      │ decision that changes the result. │
│                                          │                                    │
│ Next decision                            │ Decision                             │
│ Proxy acceptable, or exact filings?      │ [Use proxy] [Find exact filings]   │
│                                          │                                    │
│ [Review method]                          │ [Ask / change constraint…]         │
└──────────────────────────────────────────┴──────────────────────────────────┘
```

On a narrow viewport, the canvas remains above the conversation. The conversation does not disappear; it becomes the next section of the same thread.

## Primary workflow

### 1. Start with the research object

The first input accepts plain language, a registered blueprint, or a Library selection. The system creates the durable thread before the first agent turn completes.

The user does not need to click `+ New`, create an empty record, then separately open Ask.

The first response should immediately show:

- interpreted objective;
- known or inferred grain;
- initial context;
- whether the request is a construction, a direct Library lookup, or an evidence gap;
- the agent's current next step.

### 2. Run the evidence pass automatically

The agent may, without approval:

- search and inspect Library assets;
- read descriptions, capabilities, coverage, grain, and join keys;
- compare held inputs;
- detect missing or incompatible evidence;
- inspect prior thread decisions;
- draft a construction and its limitations;
- prepare a Discover handoff.

The visible progress should be compact:

```text
Understanding objective ✓
Checking Library evidence ✓
Mapping gaps ✓
Drafting construction ●
```

Raw tool traces remain available as an expandable technical detail, not as the primary interface.

### 3. Ask only consequential questions

The agent should not ask for every missing field. It should resolve reversible details itself and ask when an answer changes:

- the research meaning;
- the unit or universe;
- the acceptable proxy;
- the method choice;
- the source or collection scope;
- the destination or material side effect.

Questions should be singular and actionable. Do not present a form asking the researcher to manually complete the entire brief.

### 4. Keep Discover and Library inside the thread's loop

Synthesis remains the conductor for a construction, but it does not own source procurement.

When evidence is missing, the agent prepares an exact Discover handoff containing:

```text
thread identity
research objective
required grain
evidence role
held evidence
missing evidence
acceptable limitations
```

Discover may search, compare, probe, or propose a collection route. Its result returns to the same Synthesis thread. The researcher may inspect the full Discover surface, but does not manually reconstruct context after returning.

When a new asset lands in Library, Synthesis re-evaluates the construction and presents a revision proposal. It does not silently mutate an accepted method.

### 5. Review one recommended method

The agent should recommend one construction by default. Alternatives remain available behind `Compare alternatives`.

The method card states:

- inputs;
- transformations;
- output grain;
- expected coverage;
- assumptions;
- limitations;
- unresolved unknowns;
- how the method answers the research objective.

The primary action is `Review method`. Accepting it creates a revision-bound durable state. It does not build data.

### 6. Use one material approval gate

After acceptance, the system prepares execution automatically. The researcher sees one clear action:

```text
Approve and run
```

The confirmation states destination, estimated resource use, identity, and what is not yet verified. There should not be separate user-facing actions for “request execution” and “approve build” when the first merely creates an internal pending state.

The backend may retain those lifecycle states. The interface should expose the single meaningful boundary.

### 7. Continue automatically through verification and reuse

After approval:

```text
queued → running → archive checked → registered → query-readiness checked
```

The thread reports each state honestly. On registration, it offers `Open in Library` and returns the asset as a reusable input. Synthesis is not an end state; it can feed another construction or trigger a Discover re-check.

## Autonomy and approval contract

### Agent may do automatically

- read and compare evidence;
- update an unaccepted draft;
- resolve reversible formatting or naming choices;
- prepare Discover and Library handoffs;
- explain coverage and limitations;
- re-evaluate a draft when new evidence arrives;
- show progress and diagnostics.

### Researcher must decide

- ambiguous research meaning;
- material proxy or universe choice;
- acceptance of a method;
- external collection or licensed access;
- execution that writes, materializes, registers, or spends resources.

### Agent must never do silently

- claim a source was collected;
- call completed equivalent to verified, registered, or query-ready;
- change an accepted construction without a new revision;
- overwrite Library evidence;
- hide a failed route or unresolved gap;
- convert a proposed strategy into a live collection job without approval.

## State presentation

The centre should use one adaptive construction card, not a different page for every lifecycle state.

```text
draft objective       → objective + evidence summary
evidence mapping      → evidence map + gap
method proposed       → recommended method + decision
method accepted       → execution preview + approval
build running         → progress + truth boundary
registered            → verification + Library handoff
failed                → cause + valid recovery
```

The right conversation surface stays attached to the same thread. It should never show a generic “context received” response or a provider-linking failure as the main user-facing result. If the agent cannot answer, show a plain recovery state and preserve the objective.

## Acceptance criteria for this consolidation

The implementation is directionally correct when a researcher can:

1. Enter one objective and immediately receive a durable thread and first interpretation.
2. See Library evidence, missing evidence, and the proposed construction without navigating between pages.
3. Clarify the method conversationally without losing the evidence canvas.
4. Trigger Discover from a named gap and return with context intact.
5. Accept one revision-bound method without accidentally executing it.
6. Approve one material build action with clear destination and truth boundaries.
7. Watch the asset progress to registration and open it in Library.
8. Continue the same thread to revise, backtrack, or construct a related asset.
9. Never be asked to operate an internal lifecycle transition that does not change their decision.

## Implementation handoff

This document is a product/interaction handoff, not permission to weaken backend governance.

Recommended implementation order:

1. Make the Synthesis first turn create the durable thread and open the conversation automatically.
2. Replace the post-create empty blueprint state with the thread-created decision card.
3. Keep the evidence canvas and conversation visible together.
4. Collapse `request execution` plus `approve build` into one user-facing approval boundary while preserving backend lifecycle states.
5. Make Discover handoffs return to the exact Synthesis thread automatically.
6. Replace provider plumbing responses with grounded answer content or a plain recoverable state.
7. Add browser journeys for objective → clarification → method → approval → registration → Library reuse, including a backtrack through Discover.

The existing S-04 truth rules, proposal hashes, execution gates, registration distinctions, and Discover ownership remain unchanged. This addendum only consolidates how the researcher reaches and operates them.
