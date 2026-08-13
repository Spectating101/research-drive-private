# Synthesis implementation handoff

**Status:** ACTIVE WORK ORDER
**Date:** 2026-08-13
**Scope:** finish the Synthesis surface against a frozen design. This is not a design round.

## Read these, in this order, and nothing else

1. [`SYNTHESIS_WORKSPACE_FREEZE_2026-08-13.md`](SYNTHESIS_WORKSPACE_FREEZE_2026-08-13.md) — the
   binding reconciliation. It settles which of the two earlier documents governs what.
2. [`product/SYNTHESIS_S04_PRODUCT_SPEC.md`](product/SYNTHESIS_S04_PRODUCT_SPEC.md) — the CLI
   wireframe. This is the **visual composition**.
3. [`product/SYNTHESIS_AGENT_LED_WORKSPACE.md`](product/SYNTHESIS_AGENT_LED_WORKSPACE.md) — the
   **operating model**: one durable thread, canvas beside conversation, one consequential
   question at a time.

They are adopted together. S-04 is the picture; the August 11 handoff is the behaviour. Do not
treat them as competing designs.

## Do not

- Do not open a new design document. The design is frozen.
- Do not merge `feature/professor-workflow-convergence` or
  `grok/synthesis-agent-led-workflow-20260811` component code. Both are 91 commits stale and the
  August 13 freeze rules their implementation out explicitly. Their **documents** are already here.
- Do not judge the interface from a text dump or a passing test. That failure produced a full day
  of wrong conclusions on 2026-08-12/13.

## Definition of done

Done means **the rendered page matches the wireframe**, not "tests pass".

Every claim of progress must attach captures from the existing harness:

```bash
npx playwright test e2e/program-visual-states.spec.js
# writes docs/screenshots-review/program-visual-states/ at 1280 / 1440 / 1920
```

1920 is included because it is the width this product is actually reviewed at. Do not self-certify
from 1440 alone, and do not self-certify at all — attach the captures and let the reviewer call it.

## Known remaining work

Verified by render on 2026-08-13 against the in-flight implementation:

| # | Gap | Evidence |
|---|---|---|
| 1 | Label and value collide with no separator in every evidence node — `Search intent`**`asset-week`**, `GDELT news`**`event-day`** | visible in all six nodes |
| 2 | Right rail is a ten-row status readout (`STATUS / USE NOW / RISK / NEXT / GRAIN / EVIDENCE / PROPOSAL / EXECUTION / OUTPUT / MANIFEST`). The August 11 wireframe specifies a decision surface: objective, evidence, recommended method, next decision | compare rail against §"One-page interaction model" |
| 3 | No `[Review method]` action and no inline decision buttons in the conversation | wireframe shows `[Use proxy] [Find exact filings]` inline |
| 4 | Roughly half the canvas is empty below the fold at 1920 | `aug13-synth-active` capture |

Already landed, do not redo: the five-stage wizard tracker is removed, the duplicated blueprint
paragraph is gone, `IDEAL DIRECT MEASURE` renders as its own evidence role, and the entry state
carries an explicit `WHAT HAPPENS NEXT` block stating that nothing is collected, built, or
registered from that step.

## In-flight work you must not restart

An implementation against the August 13 freeze already exists, uncommitted, on branch
`release/ui-authority-convergence-20260813` in the `ui-authority-convergence` worktree
(11 files, +265/−173). A snapshot is preserved at `/home/phyrexian/rescue-20260813/`. Pick that up
rather than starting again.

## Truth rules that still bind

Unchanged from [`UI_PRODUCT_AUTHORITY.md`](UI_PRODUCT_AUTHORITY.md) §15 and S-04. In particular:
a completed job is not an archived one, archived is not registered, registered is not query-ready,
and no output may be called registered until registration evidence exists. Never render a
fabricated healthy state when the real one is unknown — say what is not established.
