# Synthesis S-04 frontend slice

Status: implemented on `feat/synthesis-ai-workspace-ui`

Authority: `docs/product/SYNTHESIS_S04_PRODUCT_SPEC.md`

Date: 2026-07-29

## What this slice establishes

- A new Synthesis project begins with one ordinary-language research objective.
- Creating the project persists a durable thread before handing the exact objective to Ask.
- Ask is investigation-scoped: selecting a durable thread restores that thread's linked conversation.
- A fresh project cannot inherit the previously selected thread or transcript.
- The centre shows durable research state rather than a second chat transcript.
- Evidence flows from Library inputs through an optional method into the constructed research object.
- Ask may interpret and propose; it cannot silently accept a method, execute work, register an output, or claim query readiness.
- Detail and Ask are exclusive lenses on desktop and deliberate overlay sheets on mobile.
- Registered and query-ready remain separate lifecycle claims.

## Rendered acceptance states

The Playwright journey captures:

1. evidence mapping with source-backed Detail;
2. approval-gated execution;
3. registered output with manifest evidence;
4. investigation-scoped Ask with restored thread history;
5. empty new-project entry;
6. first AI interpretation and draft workspace;
7. mobile evidence workspace;
8. mobile Detail sheet;
9. mobile Ask sheet.

The mobile contract keeps the five primary product destinations legible and removes the
Profile/Settings icon collision from the bottom tray. Profile and Settings remain available
through the account surface.

## Truth boundary

The visual captures use deterministic API fixtures to prove composition and state handling.
They do not prove that a public review deployment can produce a live model response. Live
provider acceptance remains a separate release condition.

The interface must continue to reject:

- execution claims without a durable execution record;
- registration claims without registry evidence;
- query-ready claims inferred from registration;
- AI replies that present a provisional proxy as an observed measure;
- conversation history from a different Synthesis thread.

## Verification

```text
npm exec playwright test e2e/v2-synthesis.spec.js
npm run build
```

The browser contract also asserts that inactive Detail/Ask panes do not paint and that an
expanded mobile rail has a usable sheet height rather than a decorative strip.
