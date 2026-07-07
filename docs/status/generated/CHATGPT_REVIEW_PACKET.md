# ChatGPT review packet — Research Drive v2 (Drive + HF + Ask rail)

**Generated:** 2026-07-07T17:25Z · Live desk `:5179` + API `:8765` · **159** registered datasets

## Upload to ChatGPT

**Upload this file only** (screenshots + markdown evidence):

```text
research-drive-chatgpt-packet.zip
```

**Verify before upload** (must PASS):

```bash
node scripts/verify_chatgpt_packet.mjs
```

Expected (2026-07-07 capture): **~8.95 MB**, SHA256 `fd7534dfe04473bd87738f564454df4bd99e8cd283b678d7f2d842450172d525`, `manifest.git_head` = `7eb4271` (Spectating101/yzu-cluster), `manifest.captured_at` = `2026-07-07T17:24:10.379Z`, `manifest.acquire_query` includes MOPS director pledge ladder (desktop discover-acquire/probe/ask).

## Product model (current)

```text
Library ≈ Google Drive vault (folder-first, preview, register)
Discover ≈ Hugging Face / DOI / open-web procurement ladder
Ask ≈ right-rail Composer agent (structured rail_context, not chat-only UI)
Home ≈ command surface + profile-aware suggested asks (not 150-card catalog dump)
```

Home hero copy:

```text
Google Drive vault for the lab. Discover Hugging Face, DOI catalogs, and the open web.
Ask the assistant to search, query, collect, and register.
```

## What to ask ChatGPT

```text
Review Research Drive v2 — YZU faculty procurement desk.

Product model:
  Home = command surface + profile-aware asks
  Library = lab vault (159 datasets; folder tree, preview, lane chips)
  Discover = acquisition ladder (registry → unified → web → probe → collect → Library)
  Resources = operational safety ledger
  Right rail = Detail | Ask (rail_context for selected objects)

Attached:
  - research-drive-chatgpt-packet.zip (84 PNGs + markdown)
  - professor_demo_report.md (9/9 live e2e scenarios PASS, 2026-07-07)
  - DISCOVER_ACQUISITION.md semantics

Judge:
1. Library feels like Drive vault, not a raw catalog homepage?
2. Discover credible for HF/DOI/web procurement (probe, fit, destination)?
3. Ask rail receives object context — not generic chat beside pages?
4. Home suggests faculty-aware asks without dumping all holdings?
5. Visual hierarchy vs “student repo” feel

Reference canon: docs/RESEARCH_DRIVE_UI_CANON.md (yzu-cluster repo)
```

## Key screenshots (desktop)

| File | Shows |
|------|--------|
| `desktop-home-viewport.png` | Drive+HF+Ask hero + lane strip + suggested asks |
| `desktop-library-stablecoin-preview-viewport.png` | Vault drill-in + row preview |
| `desktop-discover-acquire-viewport.png` | External open-web candidate (not In lab) |
| `desktop-discover-probe-viewport.png` | Probe result + connector summary in rail |
| `desktop-discover-ask-viewport.png` | Add to lab → Ask with structured prompt |
| `desktop-discover-search-viewport.png` | TWSE — mostly in-lab hits |
| `desktop-profile-viewport.png` | Faculty profile (drkong@saturn.yzu.edu.tw) |
| `desktop-resources-viewport.png` | Safety ledger |

## Live evidence summary

- Professor demo e2e: **9/9 PASS** (`YZU_DESK_URL=http://127.0.0.1:5179 npm run test:professor-demo`)
- Build: `npm run build` PASS
- Packet verify: `node scripts/verify_chatgpt_packet.mjs` PASS
- API routes live: `/library/discover/web`, `/probe`, `/collect`, `/library/faculty/profile`

## Refresh commands

```bash
bash drive/scripts/run_research_query_engine.sh   # API :8765
npm run dev -- --port 5179                         # UI (not :5178 — wrong app)
npm run desk:capture:live
npm run test:professor-demo
bash scripts/sync_yzu_cluster_github.sh            # push to Spectating101/yzu-cluster
```
