# YZU Cluster — Research Drive

Public GitHub home for the **YZU Research Drive** procurement desk: faculty UI, design canon, and visual-review artifacts.

This repo is the **pitch-facing frontend slice**. The full control plane (Python API `:8765`, MCP, workers, `data_lake/`) lives in the private monorepo **Sharpe-Renaissance** (`drive/` tree).

## What this is

| Promise | What professors get |
|---------|---------------------|
| **Organized lab data** | Library catalog mapped to vault partitions |
| **Procurement assistant** | Composer + MCP — search, query, collect, register |

**Not** alpha trading, not SolarPunk — those are separate products.

## Live surfaces

| Surface | URL |
|---------|-----|
| **GitHub Pages** (static UI + demo seed) | https://spectating101.github.io/yzu-cluster/ — enable via [`docs/GITHUB_PAGES_SETUP.md`](docs/GITHUB_PAGES_SETUP.md) |
| **Full desk** (API + chat + workers) | Run locally — see below |

Static Pages shows the v2 shell and offline demo catalog. Composer chat and live registry need the API running.

## Run locally (full desk)

From **Sharpe-Renaissance** monorepo:

```bash
bash drive/scripts/run_yzu_cluster.sh
# UI → http://127.0.0.1:5178
# API → http://127.0.0.1:8765
```

Frontend-only (this repo):

```bash
npm install
npm run dev
# proxy → :8765 (start API separately for live data)
```

## ChatGPT visual review

GitHub connector gives **structure and copy**. For **pixels** (spacing, hierarchy, mobile), generate screenshots:

```bash
# With desk running on :5178 (monorepo or this repo + API)
bash scripts/capture_desk_screenshots.sh
```

Produces `research-drive-screenshots.zip` — upload to a new ChatGPT chat.

See [`docs/CHATGPT_VISUAL_REVIEW.md`](docs/CHATGPT_VISUAL_REVIEW.md).

## Canon docs (implement UI from these)

- [`docs/RESEARCH_DRIVE_UI_CANON.md`](docs/RESEARCH_DRIVE_UI_CANON.md) — product authority
- [`docs/RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md`](docs/RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md) — Detail \| Ask rail
- [`docs/design/V2_BUILD_FROZEN.md`](docs/design/V2_BUILD_FROZEN.md) — build phases + e2e gates

## Sync from monorepo

Maintainers refresh this public repo from Sharpe-Renaissance:

```bash
bash scripts/sync_yzu_cluster_github.sh   # in Sharpe-Renaissance
cd ../yzu-cluster && git add -A && git commit && git push
```

## Share line

> Research Drive is a lab data desk for YZU: organized vault catalog, live query registry, and a Composer-backed procurement loop — search what we have, collect what we don't, register it for next time.
