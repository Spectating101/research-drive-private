# Desk commands — monorepo vs public repo

Research Drive runs as a **full stack** (API `:8765` + worker + UI `:5178`). Screenshots and beta e2e tests require the live API — UI-only `npm run dev` falls back to demo seed.

## Sharpe-Renaissance (monorepo — canonical)

Start everything (loads `CURSOR_API_KEY` from `.env.local`):

```bash
bash scripts/run_yzu_cluster.sh
# or
npm run desk:start
```

Verify + capture + test:

```bash
npm run desk:integration          # Python: env, API, registry, profile, UI proxy
npm run desk:capture:live         # screenshots; fails unless Live registry
npm run test:beta-workflow        # 7 live Playwright scenarios
```

## yzu-cluster (public UI repo)

This repo ships the faculty UI and e2e specs. It does **not** include the Python query engine or `run_yzu_cluster.sh`.

**Before capture or beta tests**, start the API from Sharpe-Renaissance in another terminal:

```bash
cd ../Molina-Optiplex/Sharpe-Renaissance
bash scripts/run_yzu_cluster.sh
```

Then in `yzu-cluster`:

```bash
npm run dev                       # UI on :5178 (proxies /api → :8765)
npm run desk:integration          # Node: API + UI proxy health
npm run desk:capture:live         # YZU_REQUIRE_LIVE=1 screenshots
npm run test:beta-workflow        # requires API on :8765
```

| Script | Public repo | Monorepo only |
|--------|-------------|---------------|
| `desk:start` | — | `bash scripts/run_yzu_cluster.sh` |
| `desk:integration` | `node scripts/desk_verify_live.mjs` | `python3 scripts/ops/desk_integration_check.py` |
| `desk:capture` / `desk:capture:live` | `bash scripts/capture_desk_screenshots.sh` | `bash scripts/yzu_cluster_github/capture_desk_screenshots.sh` |
| `test:beta-workflow` | yes (live API required) | yes |
| `sync:yzu-cluster` | — | publish UI → public repo |

### Live capture gate

```bash
YZU_REQUIRE_LIVE=1 bash scripts/capture_desk_screenshots.sh
```

Checks API health on `:8765`, waits for **Live registry** in the header, then captures 36 PNGs.
