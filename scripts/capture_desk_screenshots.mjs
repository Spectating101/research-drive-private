#!/usr/bin/env node
/**
 * Capture Research Drive v2 screenshots for ChatGPT / advisor visual review.
 *
 * Usage:
 *   node scripts/capture_desk_screenshots.mjs
 *   YZU_DESK_URL=http://127.0.0.1:5178 node scripts/capture_desk_screenshots.mjs
 *   YZU_REQUIRE_LIVE=1 node scripts/capture_desk_screenshots.mjs
 */
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = fs.existsSync(path.join(__dirname, "..", "drive", "src", "v2", "main.jsx"))
  ? path.resolve(__dirname, "..")
  : fs.existsSync(path.join(__dirname, "..", "..", "drive", "src", "v2", "main.jsx"))
    ? path.resolve(__dirname, "../..")
    : path.resolve(__dirname, "..");
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
  { slug: "discover-search", path: "/?tab=browse&q=TWSE", label: "Discover · search results" },
  { slug: "resources", path: "/?tab=resources", label: "Resources" },
];

function gitHead() {
  const r = spawnSync("git", ["rev-parse", "--short", "HEAD"], { cwd: ROOT, encoding: "utf8" });
  return r.status === 0 ? r.stdout.trim() : "unknown";
}

async function waitForTrustBadge(page, liveOnly = false) {
  await page.waitForFunction(
    (requireLive) => {
      const text = document.body?.innerText || "";
      const badges = Array.from(document.querySelectorAll(".rd-v2-trust-badge"))
        .map((el) => el.textContent || "")
        .join(" ");
      const hay = `${text} ${badges}`;
      if (requireLive) return hay.includes("Live registry");
      return (
        hay.includes("Live registry") ||
        hay.includes("Demo catalog") ||
        hay.includes("Desk API offline")
      );
    },
    liveOnly,
    { timeout: 45_000 },
  );
}

async function waitForShell(page) {
  await page.waitForSelector(".rd-v2-shell, .yzu-shell", { timeout: 45_000 });
  await waitForTrustBadge(page, false);

  if (process.env.YZU_REQUIRE_LIVE === "1") {
    try {
      await waitForTrustBadge(page, true);
    } catch {
      await page.reload({ waitUntil: "load" });
      await page.waitForSelector(".rd-v2-shell, .yzu-shell", { timeout: 45_000 });
      await waitForTrustBadge(page, false);
      await waitForTrustBadge(page, true);
    }
  }

  await page.waitForTimeout(600);
}

async function waitForRouteReady(page, route) {
  const requireLive = process.env.YZU_REQUIRE_LIVE === "1";

  const run = async () => {
    if (route.slug === "discover-search") {
      await page.waitForFunction(() => {
        const text = document.body?.innerText || "";
        return !text.includes("Showing offline matches while live catalogs refresh");
      }, { timeout: 60_000 });

      await page.waitForFunction(
        (live) => {
          const text = document.body?.innerText || "";
          const offlineChip = Array.from(document.querySelectorAll(".rd-v2-chip")).some((el) =>
            (el.textContent || "").includes("Offline sample"),
          );
          if (offlineChip) return false;
          const hasLiveSource = text.includes("Discover API") || text.includes("Unified search");
          const hasResults =
            /\d+ results?/i.test(text) ||
            text.includes("Taiwan TWSE") ||
            text.includes("TWSE OpenAPI");
          if (live) {
            return hasLiveSource && hasResults;
          }
          return hasResults;
        },
        requireLive,
        { timeout: 60_000 },
      );
    }

    if (route.slug === "discover" && !route.path.includes("q=")) {
      await page.waitForFunction(() => {
        const text = document.body?.innerText || "";
        return text.includes("Find external datasets") || text.includes("TWSE governance");
      }, { timeout: 20_000 });
    }

    if (route.slug === "resources") {
      await page.waitForFunction(() => {
        const text = document.body?.innerText || "";
        return (
          text.includes("ASK USAGE") ||
          text.includes("Ask usage") ||
          text.includes("COLLECTION WORKERS") ||
          text.includes("Collection workers") ||
          text.includes("DESK CONNECTION") ||
          text.includes("Desk connection")
        );
      }, { timeout: 60_000 });
    }

    if (route.slug === "library-connections-queue") {
      await page.waitForFunction(() => {
        const text = document.body?.innerText || "";
        return (
          (text.includes("Data Collection Queue Status") ||
            text.includes("collection_queue_status")) &&
          text.includes("Query-ready")
        );
      }, { timeout: 45_000 });
    }

    await page.waitForTimeout(600);
  };

  try {
    await run();
  } catch (err) {
    if (route.slug === "discover-search" || route.slug === "resources") {
      await page.reload({ waitUntil: "load" });
      await waitForShell(page);
      await run();
      return;
    }
    throw err;
  }
}

async function captureRoute(browser, vpName, viewport, route) {
  const page = await browser.newPage({ viewport });
  const url = `${BASE_URL}${route.path}`;
  await page.goto(url, { waitUntil: "load" });
  await waitForShell(page);
  await waitForRouteReady(page, route);

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
    require_live: process.env.YZU_REQUIRE_LIVE === "1",
    notes: [
      "Screenshots committed under docs/screenshots-review/ for ChatGPT + GitHub connector review.",
      "Zip at repo root: research-drive-screenshots.zip",
      "Set YZU_REQUIRE_LIVE=1 to fail capture unless header shows Live registry (API on :8765).",
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
