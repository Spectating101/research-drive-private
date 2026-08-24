# Enable GitHub Pages for yzu-cluster

The deploy workflow (`.github/workflows/deploy-pages.yml`) runs on every push to `main`, but **Pages must be enabled once** in repo settings or deploys succeed with no public URL (404).

## One-time setup

1. Open https://github.com/Spectating101/yzu-cluster/settings/pages
2. Under **Build and deployment** → **Source**, choose **GitHub Actions**
3. Push to `main` (or run **Actions** → **Deploy GitHub Pages** → **Run workflow**)
4. Wait for the `deploy` job to finish (green)
5. Verify: https://spectating101.github.io/yzu-cluster/

## If you still see 404

| Symptom | Fix |
|---------|-----|
| No workflow runs | Confirm `.github/workflows/deploy-pages.yml` exists on `main` |
| `build` fails | Check Actions log — usually `npm ci` / `vite build` |
| `deploy` skipped | Pages source must be **GitHub Actions**, not “Deploy from branch” |
| Old 404 cached | Hard refresh or wait ~2 min for CDN |

## What Pages serves

- Static v2 UI built with `base: /yzu-cluster/`
- Demo catalog seed (`drive/config/desk_demo_catalog.json`)
- **No** live API — Composer chat and registry need local `:8765`

## Local parity check before push

```bash
GITHUB_ACTIONS=true npm run build
npx vite preview --host 127.0.0.1 --port 4178
# open http://127.0.0.1:4178/yzu-cluster/
```
