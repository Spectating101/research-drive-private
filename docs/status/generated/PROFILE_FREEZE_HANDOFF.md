# Profile freeze — handoff (2026-07-10)

## Canonical state
- **IA (do not reorder):** Memory → Works → Lab (Linked / Suggested)
- **Memory is the anchor** — saved research context. Never demote to chips/tabs/gaps.
- **DETAIL rail:** Scholar / Strengths / Desk (evidence-gated)
- **ASK:** quiet context header only

## Files
- `drive/src/v2/ProfilePage.jsx` — main + ProfileDetailPanel
- `drive/src/v2/profileViewModel.js` — buildMemoryCards / Works / Lab / DeskRead
- `drive/src/v2/InspectorRail.jsx` — Profile uses ProfileDetailPanel
- `drive/src/v2/AskRail.jsx` — Profile quiet Ask copy
- `drive/src/v2/v2.css` — Profile freeze styles (section ~20)
- `e2e/v2-profile-freeze.spec.js`

## Screenshots (local, gitignored)
- `docs/status/generated/profile-freeze-showcase.png` (full)
- `docs/status/generated/profile-freeze-viewport.png`
- `docs/status/generated/profile-freeze-detail.png`
- `docs/status/generated/profile-freeze-ask.png`

## What went wrong (do not repeat)
Home token-matching and “less scroll” passes replaced Profile grammar with Home widgets and demoted Memory. Reverted to CLI wireframe freeze. Polish spacing/type in place — do not reinvent IA.

## Verify
```bash
TMPDIR=$PWD/.tmp-pw npx playwright test e2e/v2-profile-freeze.spec.js --retries=0
```
