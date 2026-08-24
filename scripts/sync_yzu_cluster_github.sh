#!/usr/bin/env bash
# Publish Research Drive UI + docs to the public yzu-cluster GitHub repo.
# Source: Sharpe-Renaissance monorepo. Target: ../yzu-cluster (or YZU_CLUSTER_OUT).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SR_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT="${YZU_CLUSTER_OUT:-$(cd "$SR_ROOT/../../yzu-cluster" 2>/dev/null && pwd || echo "$SR_ROOT/../../yzu-cluster")}"

mkdir -p "$OUT/drive/src" "$OUT/config" "$OUT/docs/design" "$OUT/e2e" "$OUT/.github/workflows" "$OUT/scripts" "$OUT/src"

rsync -a --delete \
  --exclude node_modules \
  --exclude dist \
  --exclude .tmp-pw \
  --exclude test-results \
  "$SR_ROOT/package.json" \
  "$SR_ROOT/package-lock.json" \
  "$SR_ROOT/index.html" \
  "$SR_ROOT/components.json" \
  "$SR_ROOT/jsconfig.json" \
  "$OUT/"

rsync -a --delete \
  "$SR_ROOT/drive/src/" \
  "$OUT/drive/src/"

# Monorepo shim → standalone canonical file
rsync -a "$SR_ROOT/src/driveTree.js" "$OUT/drive/src/driveTree.js"

mkdir -p "$OUT/drive/config"
rsync -a \
  "$SR_ROOT/drive/config/desk_demo_catalog.json" \
  "$SR_ROOT/drive/config/desk_sources.json" \
  "$OUT/drive/config/"

mkdir -p "$OUT/docs/design"
for doc in \
  RESEARCH_DRIVE_UI_CANON.md \
  DESK_STATUS.md \
  RESEARCH_DRIVE_RIGHT_RAIL_CONTRACT.md \
  DATABANK_STATE.md \
  DESK_ACTIVATION.md \
  yzu_cluster.md; do
  if [[ -f "$SR_ROOT/docs/$doc" ]]; then
    rsync -a "$SR_ROOT/docs/$doc" "$OUT/docs/"
  fi
done
for doc in V2_BUILD_FROZEN.md V2_FORWARD_FROZEN.md LAYOUT_SPEC.md; do
  if [[ -f "$SR_ROOT/docs/design/$doc" ]]; then
    rsync -a "$SR_ROOT/docs/design/$doc" "$OUT/docs/design/"
  fi
done

rsync -a "$SR_ROOT/drive/README.md" "$OUT/drive/README.md"

mkdir -p "$OUT/e2e"
rsync -a "$SR_ROOT/e2e/fixtures/" "$OUT/e2e/fixtures/"
rsync -a \
  "$SR_ROOT/e2e/v2-"*.spec.js \
  "$SR_ROOT/e2e/professor-demo.spec.js" \
  "$SR_ROOT/e2e/beta-workflow.spec.js" \
  "$OUT/e2e/"

# Live screenshots (captured against :5179 + :8765)
if [[ -d "$SR_ROOT/docs/screenshots-review" ]]; then
  rsync -a "$SR_ROOT/docs/screenshots-review/" "$OUT/docs/screenshots-review/"
fi
if [[ -f "$SR_ROOT/docs/status/generated/professor_demo_report.md" ]]; then
  mkdir -p "$OUT/docs/status/generated"
  cp "$SR_ROOT/docs/status/generated/professor_demo_report.md" "$OUT/docs/status/generated/"
  cp "$SR_ROOT/docs/status/generated/professor_demo_report.json" "$OUT/docs/status/generated/" 2>/dev/null || true
  cp "$SR_ROOT/docs/status/generated/CHATGPT_REVIEW_PACKET.md" "$OUT/docs/status/generated/" 2>/dev/null || true
  cp "$SR_ROOT/docs/status/generated/golden_procure_path.md" "$OUT/docs/status/generated/" 2>/dev/null || true
  cp "$SR_ROOT/docs/status/generated/golden_procure_path.json" "$OUT/docs/status/generated/" 2>/dev/null || true
fi
if [[ -f "$SR_ROOT/research-drive-screenshots.zip" ]]; then
  cp "$SR_ROOT/research-drive-screenshots.zip" "$OUT/research-drive-screenshots.zip"
fi
if [[ -f "$SR_ROOT/research-drive-chatgpt-packet.zip" ]]; then
  cp "$SR_ROOT/research-drive-chatgpt-packet.zip" "$OUT/research-drive-chatgpt-packet.zip"
fi

# index.html imports /drive/src/v2/main.jsx (Vite dev + GH Pages build)
mkdir -p "$OUT/src"
ln -sfn ../drive/src/v2 "$OUT/src/v2"

# Repo-local vite + playwright (GH Pages base path)
cp "$SCRIPT_DIR/yzu_cluster_github/vite.config.js" "$OUT/vite.config.js"
cp "$SCRIPT_DIR/yzu_cluster_github/playwright.config.js" "$OUT/playwright.config.js"
cp "$SCRIPT_DIR/yzu_cluster_github/.gitignore" "$OUT/.gitignore"
mkdir -p "$OUT/.github/workflows"
cp "$SCRIPT_DIR/yzu_cluster_github/deploy-pages.yml" "$OUT/.github/workflows/deploy-pages.yml"
cp "$SCRIPT_DIR/yzu_cluster_github/ci.yml" "$OUT/.github/workflows/ci.yml"
mkdir -p "$OUT/scripts"
cp "$SCRIPT_DIR/yzu_cluster_github/capture_desk_screenshots.mjs" "$OUT/scripts/capture_desk_screenshots.mjs"
cp "$SCRIPT_DIR/yzu_cluster_github/capture_desk_screenshots.sh" "$OUT/scripts/capture_desk_screenshots.sh"
cp "$SCRIPT_DIR/yzu_cluster_github/desk_verify_live.mjs" "$OUT/scripts/desk_verify_live.mjs"
chmod +x "$OUT/scripts/capture_desk_screenshots.sh"
cp "$SCRIPT_DIR/yzu_cluster_github/README.md" "$OUT/README.md"
cp "$SCRIPT_DIR/yzu_cluster_github/docs/CHATGPT_VISUAL_REVIEW.md" "$OUT/docs/CHATGPT_VISUAL_REVIEW.md"
cp "$SCRIPT_DIR/yzu_cluster_github/docs/GITHUB_PAGES_SETUP.md" "$OUT/docs/GITHUB_PAGES_SETUP.md"
cp "$SCRIPT_DIR/yzu_cluster_github/docs/DESK_COMMANDS.md" "$OUT/docs/DESK_COMMANDS.md"
cp "$SR_ROOT/docs/PROFESSOR_DEMO_SCRIPT.md" "$OUT/docs/PROFESSOR_DEMO_SCRIPT.md"
cp "$SR_ROOT/docs/DISCOVER_ACQUISITION.md" "$OUT/docs/DISCOVER_ACQUISITION.md"
mkdir -p "$OUT/docs/screenshots-review"
cp "$SR_ROOT/docs/screenshots-review/README.md" "$OUT/docs/screenshots-review/README.md" 2>/dev/null || \
cp "$SCRIPT_DIR/yzu_cluster_github/docs/screenshots-review/README.md" "$OUT/docs/screenshots-review/README.md"

# Public package.json: UI-repo scripts (no monorepo Python paths)
"${SR_PYTHON:-python3}" - <<'PY' "$OUT/package.json"
import json, sys
path = sys.argv[1]
pkg = json.loads(open(path).read())
scripts = pkg.setdefault("scripts", {})
scripts.update({
    "desk:capture": "bash scripts/capture_desk_screenshots.sh",
    "desk:capture:live": "YZU_REQUIRE_LIVE=1 bash scripts/capture_desk_screenshots.sh",
    "desk:integration": "node scripts/desk_verify_live.mjs",
    "test:beta-workflow": "mkdir -p .tmp-pw && TMPDIR=$PWD/.tmp-pw playwright test e2e/beta-workflow.spec.js",
    "test:professor-demo": "mkdir -p .tmp-pw docs/status/generated && TMPDIR=$PWD/.tmp-pw playwright test e2e/professor-demo.spec.js",
})
for key in ("desk:start", "sync:yzu-cluster", "build:faculty", "preview:desk", "dev:legacy"):
    scripts.pop(key, None)
open(path, "w").write(json.dumps(pkg, indent=2) + "\n")
PY

echo "synced → $OUT"
echo "next: cd $OUT && npm install && npm run build"
