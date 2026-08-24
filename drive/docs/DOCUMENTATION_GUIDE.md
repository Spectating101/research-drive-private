# Documentation Guide

Use [CURRENT_STATE.md](CURRENT_STATE.md) as the starting point for any new agent or review.

## Authority Classes

| Class | Meaning | Handling |
| --- | --- | --- |
| Current authority | Rules that govern active work | Keep short and link from `CURRENT_STATE.md` |
| Procedure | Reusable operational runbook | Keep dated assumptions out of the procedure |
| Historical snapshot | Accurate only for a stated date | Preserve with a visible historical label |
| Generated report | Derived from scripts and mutable state | Regenerate; do not hand-edit |

## Rules

- Do not use old dataset counts, active PR numbers, or host inventory as current facts.
- Do not delete historical architecture or acceptance records merely to reduce context. Label them and link to current authority instead.
- Do not copy runtime/deployment guidance into frontend documentation or vice versa.
- When a document is superseded, add a one-line notice at the top pointing to `CURRENT_STATE.md`.

## Review Checklist

Before creating a new design, handoff, or operational document:

1. Confirm it is not duplicating `CURRENT_STATE.md` or `REPO_AUTHORITY.md`.
2. State whether it is current authority, a procedure, or a dated snapshot.
3. Link to evidence rather than embedding volatile counts.
4. Keep secrets, host addresses, credentials, and mutable runtime data outside documentation committed to Git.
