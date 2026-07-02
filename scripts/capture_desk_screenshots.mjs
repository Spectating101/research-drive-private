#!/usr/bin/env node
/**
 * Capture Research Drive v2 screenshots for ChatGPT / advisor visual review.
 *
 * Usage:
 *   node scripts/capture_desk_screenshots.mjs
 *   YZU_DESK_URL=http://127.0.0.1:5178 node scripts/capture_desk_screenshots.mjs
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const OUT_DIR = path.join(ROOT, "docs", "screenshots-review");
const ZIP_PATH = path.join(ROOT, "research-drive-screenshots.zip");

const BASE_URL = (process.env.YZU_DESK_URL || "http://127.0.0.1:5178").replace(/\/$/, "");

const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 900, height: 1200 },
  mobile: { width: 390, height: 1200 },
};

const ROUTES = [
  { slug: "home", path: "/?tab=home", label: "Home" },
  {
    slug: "library-connections-queue",
    path: "/?tab=library&folder=connections&dataset=collection_queue_status",
    label: "Library · Apps & connections · collection queue",
  },
  { slug: "library", path: "/?tab=library", label: "Library root" },
  { slug: "discover", path: "/?tab=browse", label: "Discover" },
  { slug: "resources", path: "/?tab=resources", label: "Resources" },
];

function gitHead() {
  const r = spawnSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT, encoding: "utf8" });
  return r.status === 0 ? r.stdout.trim() : "unknown";
}

async function waitForShell(page) {
  await page.waitForSelector(".rd-v2-shell, .yzu-shell", { timeout: 45_000 });
  await page.waitForTimeout(600);
}

async function captureRoute(browser, vpName, viewport, route) {
  const page = await browser.newPage({ viewport });
  const url = `${BASE_URL}${route.path}`;
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await waitForShell(page);

  const prefix = `${vpName}-${route.slug}`;
  await page.screenshot({
    path: path.join(OUT_DIR, `${prefix}-viewport.png`),
    fullPage: false,
  });
  await page.screenshot({
    path: path.join(OUT_DIR, `${prefix}-full.png`),
    fullPage: true,
  });
  await page.close();
  return { viewport: vpName, route: route.slug, url, label: route.label };
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const manifest = {
    product: "Research Drive (YZU Cluster procurement desk)",
    captured_at: new Date().toISOString(),
    base_url: BASE_URL,
    github_repo: "Spectating101/yzu-cluster",
    github_screenshots_path: "docs/screenshots-review/",
    git_head: gitHead(),
    viewports: VIEWPORTS,
    routes: ROUTES.map((r) => ({ slug: r.slug, path: r.path, label: r.label })),
    files: [],
    notes: [
      "Screenshots committed under docs/screenshots-review/ for ChatGPT + GitHub connector review.",
      "Zip at repo root: research-drive-screenshots.zip",
      "Live API enriches data; offline seed still renders shell when API is down.",
    ],
  };

  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
  });

  try {
    for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
      for (const route of ROUTES) {
        const shot = await captureRoute(browser, vpName, viewport, route);
        manifest.files.push(`${vpName}-${route.slug}-viewport.png`);
        manifest.files.push(`${vpName}-${route.slug}-full.png`);
        console.log(`ok ${vpName} ${route.slug} → ${shot.url}`);
      }
    }
  } finally {
    await browser.close();
  }

  fs.writeFileSync(path.join(OUT_DIR, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);

  if (fs.existsSync(ZIP_PATH)) fs.unlinkSync(ZIP_PATH);
  const zip = spawnSync("zip", ["-r", ZIP_PATH, "docs/screenshots-review"], {
    cwd: ROOT,
    encoding: "utf8",
  });
  if (zip.status !== 0) {
    console.error(zip.stderr || zip.stdout);
    process.exit(1);
  }

  console.log(`\nWrote ${ZIP_PATH}`);
  console.log("Upload this zip to ChatGPT for visual review.");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
