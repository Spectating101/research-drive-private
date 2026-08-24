# ChatGPT visual review workflow

Use this when you want **pixel-level** critique of Research Drive v2 — not just source review.

## Two layers

| Layer | Tool | What it judges |
|-------|------|----------------|
| **Implementation** | GitHub connector on `Spectating101/yzu-cluster` | Structure, copy, component wiring, canon alignment |
| **Experience** | Screenshots in repo (or zip upload) | Hierarchy, spacing, CTA dominance, mobile, “premium vs repo page” |

GitHub alone cannot answer whether the hero hooks or the rail feels cramped.

## Screenshots in this repo (for ChatGPT + connector)

**Desktop review set** (start here):

| Image | Route |
|-------|--------|
| [desktop-home-viewport.png](desktop-home-viewport.png) | Home |
| [desktop-library-viewport.png](desktop-library-viewport.png) | Library root |
| [desktop-library-connections-queue-viewport.png](desktop-library-connections-queue-viewport.png) | Connections queue |
| [desktop-discover-viewport.png](desktop-discover-viewport.png) | Discover empty state |
| [desktop-discover-search-viewport.png](desktop-discover-search-viewport.png) | TWSE search (in-lab) |
| [desktop-discover-acquire-viewport.png](desktop-discover-acquire-viewport.png) | MOPS candidate selected |
| [desktop-discover-probe-viewport.png](desktop-discover-probe-viewport.png) | Probe result in rail |
| [desktop-discover-ask-viewport.png](desktop-discover-ask-viewport.png) | Add to lab → Ask |
| [desktop-resources-viewport.png](desktop-resources-viewport.png) | Resources |

Full set: all `desktop-*`, `tablet-*`, `mobile-*` viewport + full-page PNGs. See [manifest.json](manifest.json) for capture metadata.

**Zip (optional upload):** [research-drive-screenshots.zip](../research-drive-screenshots.zip) at repo root.

Browse on GitHub: `docs/screenshots-review/` folder.

## Generate / refresh screenshots

**Prerequisite:** full desk running — API on `:8765` and UI on `:5178`. See [DESK_COMMANDS.md](../DESK_COMMANDS.md).

**Live capture (recommended — fails on demo/offline):**

```bash
npm run desk:capture:live
# equivalent:
YZU_REQUIRE_LIVE=1 bash scripts/capture_desk_screenshots.sh
```

**Offline shell capture (demo seed allowed):**

```bash
bash scripts/capture_desk_screenshots.sh
```

```bash
git add docs/screenshots-review research-drive-screenshots.zip
git commit -m "chore: refresh Research Drive visual review screenshots"
git push origin main
```

## New ChatGPT chat prompt (paste)

```text
Review Research Drive v2 (YZU procurement desk) — visual + product critique.

Repo: Spectating101/yzu-cluster
Screenshots: docs/screenshots-review/ (desktop-home, library, library-connections-queue, discover, resources)
Product: lab research data desk — Library, Discover, Resources, Detail|Ask rail.
Not SolarPunk, not trading alpha.

Judge (desktop first):
1. Above-the-fold hook on Home and Library
2. Rail decision summary (Status / Use now / Risk / Next)
3. Discover acquisition pipeline clarity
4. Resources ledger density (operations panel, not marketing cards)
5. Header trust cues (demo vs live, dry-run protected)
6. Does it feel like a serious faculty desk vs a student repo?

Reference: docs/RESEARCH_DRIVE_UI_CANON.md
```

## Static GitHub Pages vs full desk

| URL | API | Chat |
|-----|-----|------|
| https://spectating101.github.io/yzu-cluster/ | Demo seed only | No |
| Local `:5178` + `:8765` | Live registry | Yes |

Capture screenshots against **local full desk** when reviewing live data density.
