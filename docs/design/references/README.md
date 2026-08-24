# UI visual references

Sketches and reference screenshots for the v2 visual pass.

**Canon:** [`../RESEARCH_DRIVE_UI_CANON.md`](../RESEARCH_DRIVE_UI_CANON.md) (composition + workflows)  
**Tokens:** [`../TOKENS.md`](../TOKENS.md) (colors/spacing only)

## Frozen wireframes (authority)

**[`../V2_FORWARD_FROZEN.md`](../V2_FORWARD_FROZEN.md)** — FROZEN phases + Preview contract + next step.  
**[`../WIREFRAME_V2_FROZEN.md`](../WIREFRAME_V2_FROZEN.md)** — FROZEN sketches + polish. CLI: `rd_layout_preview.py`.

```bash
python3 scripts/rd_layout_preview.py all --pager
```

## HTML mocks @ 1440×900

Open in browser at **100% zoom** (no devtools device frame).

| File | Scope |
|------|--------|
| **`desk-v2-1440.html`** | **Primary** — all 7 tabs + Detail/Ask rail + Preview overlay (tab switch + sidebar nav) |
| `desk-v2-1440.css` | Shared artboard styles |
| `library-v2-1440.html` | Library-only slice (subset of desk mock) |
| `layout-ruler.html` | Dimension ruler with grid overlay |

## Naming

## Internal repo shots (light rail schema)

Regenerate with `npm run test:v2` or `e2e/ux-audit.spec.js` → `docs/status/generated/`.

| File | Use |
|------|-----|
| `docs/design/references/ui-snapshots/qa-folder-tree-final-desktop.png` | Folder tree rail schema |
| `docs/design/references/ui-snapshots/research-drive-*-rail*.png` | Rail layout references |

## Public products to screenshot (reference board)

Stored under `docs/design/references/product-screenshots/` (`ref-atlan.png`, `ref-datahub*.png`, etc.).

| Tab | Screenshot from | Steal |
|-----|---------------|-------|
| Library | Atlan asset profile sidebar | DetailPanel fields, certification pills |
| Browse | Google Dataset Search | List + detail split (not HF grid) |
| Cluster | ResearchRabbit timeline view | Coverage timeline |
| Cluster | Cite-Agent datamap | Join/overlap graph |
| Resources | Cursor dashboard / Vercel Usage | Integration cards, quota bars |
| Profile | ChatGPT Memory settings | Editable memory list |

## Reject as theme sources

- Magic Procure dark console (do not use as global skin)
- `ui-snapshots/qa-folder-tree-*.png` — rail *schema* only; do not copy dark chrome
- HuggingFace hub orange branding as global skin
