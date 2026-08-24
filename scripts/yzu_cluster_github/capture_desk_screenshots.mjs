#!/usr/bin/env node
/**
 * Capture Research Drive v2 screenshots for ChatGPT / advisor visual review.
 *
 * Usage:
 *   node scripts/capture_desk_screenshots.mjs
 *   YZU_DESK_URL=http://127.0.0.1:5179 node scripts/capture_desk_screenshots.mjs
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
const PACKET_ZIP_PATH = path.join(ROOT, "research-drive-chatgpt-packet.zip");

const PACKET_DOCS = [
  "docs/DISCOVER_ACQUISITION.md",
  "docs/status/generated/CHATGPT_REVIEW_PACKET.md",
  "docs/status/generated/professor_demo_report.md",
  "docs/status/generated/professor_demo_report.json",
  "docs/PROFESSOR_DEMO_SCRIPT.md",
];

const BASE_URL = (process.env.YZU_DESK_URL || "http://127.0.0.1:5179").replace(/\/$/, "");
const FACULTY_EMAIL = process.env.CAPTURE_FACULTY_EMAIL || "drkong@saturn.yzu.edu.tw";

const DISCOVER_INTERACTIVE = new Set(["discover_acquire", "discover_probe", "discover_ask"]);

/** Queries tried in order until a non-lab acquisition candidate appears (web / DataCite / HF). */
const ACQUIRE_QUERY_CANDIDATES = (
  process.env.CAPTURE_ACQUIRE_QUERIES ||
  "MOPS director pledge raw filings Taiwan,ethereum stablecoin depeg arxiv,capture-external-acquire-2026"
)
  .split(",")
  .map((q) => q.trim())
  .filter(Boolean);

const VIEWPORTS = {
  desktop: { width: 1440, height: 900 },
  tablet: { width: 900, height: 1200 },
  mobile: { width: 390, height: 1200 },
};

const ROUTES = [
  { slug: "home", path: "/?tab=home", label: "Home" },
  {
    slug: "home-signed-in",
    path: "/?tab=home",
    label: "Home · faculty profile prompts",
    interactive: "home_signed_in",
  },
  {
    slug: "library-connections-queue",
    path: "/?tab=library&folder=connections&dataset=collection_queue_status",
    label: "Library · Apps & connections · collection queue",
  },
  { slug: "library", path: "/?tab=library", label: "Library root" },
  {
    slug: "library-stablecoin",
    path: "/?tab=library&folder=research_panels/stablecoin_trust_engagement/panel_weekly&dataset=stablecoin_trust_engagement_weekly",
    label: "Library · Stablecoin derived panel",
  },
  {
    slug: "library-stablecoin-preview",
    path: "/?tab=library&folder=research_panels/stablecoin_trust_engagement/panel_weekly&dataset=stablecoin_trust_engagement_weekly",
    label: "Library · Stablecoin preview modal",
    interactive: "library_preview",
  },
  {
    slug: "library-stablecoin-ask",
    path: "/?tab=library&folder=research_panels/stablecoin_trust_engagement/panel_weekly&dataset=stablecoin_trust_engagement_weekly",
    label: "Library · Stablecoin Ask rail",
    interactive: "ask_tab",
  },
  { slug: "profile", path: "/?tab=profile", label: "Profile" },
  { slug: "discover", path: "/?tab=browse", label: "Discover" },
  { slug: "discover-search", path: "/?tab=browse&q=TWSE", label: "Discover · TWSE search (in-lab hits)" },
  {
    slug: "discover-acquire",
    path: "/?tab=browse",
    label: "Discover · external acquisition candidate",
    interactive: "discover_acquire",
  },
  {
    slug: "discover-probe",
    path: "/?tab=browse",
    label: "Discover · probe result in rail",
    interactive: "discover_probe",
  },
  {
    slug: "discover-ask",
    path: "/?tab=browse",
    label: "Discover · Add to lab → Ask",
    interactive: "discover_ask",
  },
  { slug: "resources", path: "/?tab=resources", label: "Resources" },
];

function gitHead(cwd = ROOT) {
  const r = spawnSync("git", ["rev-parse", "--short", "HEAD"], { cwd, encoding: "utf8" });
  return r.status === 0 ? r.stdout.trim() : "unknown";
}

function yzuClusterHead() {
  const candidates = [
    process.env.YZU_CLUSTER_OUT,
    path.resolve(ROOT, "../yzu-cluster"),
    path.resolve(ROOT, "../../yzu-cluster"),
  ].filter(Boolean);
  for (const dir of candidates) {
    if (!dir || !fs.existsSync(path.join(dir, ".git"))) continue;
    const head = gitHead(dir);
    if (head !== "unknown") return head;
  }
  return null;
}

function resolveManifestGitHead() {
  if (process.env.CAPTURE_GIT_HEAD) return process.env.CAPTURE_GIT_HEAD;
  return yzuClusterHead() || gitHead();
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

async function assertResearchDrivePage(page) {
  const title = await page.title();
  if (!/research drive/i.test(title)) {
    throw new Error(
      `Wrong app at ${BASE_URL} (title="${title}"). Port 5178 may be Hardware-Splicer — use YZU_DESK_URL=http://127.0.0.1:5179 or stop the other Vite server.`,
    );
  }
}

async function waitForShell(page) {
  await page.waitForSelector(".rd-v2-shell, .yzu-shell", { timeout: 45_000 });
  await assertResearchDrivePage(page);
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

async function waitForDiscoverResults(page, { requireExternal = false } = {}) {
  await page.waitForFunction(
    (externalOnly) => {
      const text = document.body?.innerText || "";
      const offlineChip = Array.from(document.querySelectorAll(".rd-v2-chip")).some((el) =>
        (el.textContent || "").includes("Offline sample"),
      );
      if (offlineChip) return false;
      const hasLiveSource =
        text.includes("Discover API") ||
        text.includes("Unified search") ||
        text.includes("Open web");
      const hasResults = /\d+ results?/i.test(text);
      if (!hasResults) return false;
      if (!externalOnly) return hasLiveSource && hasResults;
      const externalRows = document.querySelectorAll(
        '.rd-v2-catalog button.row[data-kind="external"]:not([data-state="in_lab"])',
      );
      return hasLiveSource && externalRows.length > 0;
    },
    requireExternal,
    { timeout: 90_000 },
  );
}

async function loadAcquireSearch(page) {
  let lastError = null;
  for (const query of ACQUIRE_QUERY_CANDIDATES) {
    const url = `${BASE_URL}/?tab=browse&q=${encodeURIComponent(query)}`;
    await page.goto(url, { waitUntil: "load" });
    await waitForShell(page);
    try {
      await waitForDiscoverResults(page, { requireExternal: true });
      const allInLab = await page
        .locator(".rd-v2-discover-miss")
        .filter({ hasText: /already in your lab vault/i })
        .count();
      if (allInLab) {
        lastError = new Error(`Query "${query}" returned only in-lab matches`);
        continue;
      }
      return query;
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error("No external acquisition candidate found for any CAPTURE_ACQUIRE_QUERIES");
}

async function pickAcquireCandidate(page) {
  const picked = await page.evaluate(() => {
    const rows = Array.from(
      document.querySelectorAll('.rd-v2-catalog button.row[data-kind="external"]:not([data-state="in_lab"])'),
    );
    const score = (el) => {
      const sub = (el.querySelector(".rd-v2-discover-subline")?.textContent || "").trim();
      const hasUrl = /https?:\/\//i.test(sub) || /\.[a-z]{2,}(?:\s|·|$)/i.test(sub);
      const state = el.dataset.state || "";
      if (state === "probe_ready" && hasUrl) return 0;
      if (hasUrl) return 1;
      if (state === "probe_ready") return 2;
      return 3;
    };
    rows.sort((a, b) => score(a) - score(b));
    const best = rows[0];
    if (!best) return false;
    best.click();
    return true;
  });
  if (!picked) {
    throw new Error("No external candidate row (probe_ready with URL preferred)");
  }
  await page.waitForTimeout(400);
}

/** One search session → three screenshots (acquire / probe / ask). */
async function captureDiscoverAcquisitionLadder(browser, vpName, viewport, manifest) {
  const page = await browser.newPage({ viewport });
  const slugs = ["discover-acquire", "discover-probe", "discover-ask"];
  let query = "";
  try {
    query = await loadAcquireSearch(page);
    await pickAcquireCandidate(page);
    const rail = page.locator("aside.rd-v2-rail");
    await rail.waitFor({ state: "visible", timeout: 20_000 });
    await assertAcquireRail(page, "discover_acquire");
    manifest.acquire_query = query;

    for (const slug of slugs) {
      const prefix = `${vpName}-${slug}`;
      if (slug === "discover-probe") {
        const probeBtn = rail.getByRole("button", { name: "Probe source" });
        if (!(await probeBtn.isVisible())) {
          throw new Error(`Probe source not visible for query=${query}`);
        }
        await probeBtn.click();
        await page.waitForFunction(() => {
          const root = document.querySelector("aside.rd-v2-rail");
          const text = root?.textContent || "";
          return (
            text.includes("Probe result") ||
            text.includes("downloadable links") ||
            document.querySelector(".rd-v2-discover-probe-error")
          );
        }, { timeout: 60_000 });
        await assertAcquireRail(page, "discover_probe");
      }
      if (slug === "discover-ask") {
        const addBtn = rail.locator(".rd-v2-rail-sticky .rd-v2-btn.primary", { hasText: "Add to lab" });
        if (!(await addBtn.count())) {
          throw new Error(`Add to lab missing for query=${query}`);
        }
        await addBtn.click();
        await rail.getByRole("tab", { name: "Ask" }).click();
        await assertAskAddToLab(page);
        await page.waitForTimeout(600);
      }
      await page.screenshot({ path: path.join(OUT_DIR, `${prefix}-viewport.png`), fullPage: false });
      await page.screenshot({ path: path.join(OUT_DIR, `${prefix}-full.png`), fullPage: true });
      manifest.files.push(`${prefix}-viewport.png`, `${prefix}-full.png`);
      console.log(`ok ${vpName} ${slug} → acquire ladder (query=${query})`);
    }
  } finally {
    await page.close();
  }
  return query;
}

async function assertAcquireRail(page, mode) {
  await page.waitForFunction(
    (captureMode) => {
      const rail = document.querySelector("aside.rd-v2-rail");
      if (!rail) return false;
      const text = rail.textContent || "";
      if (/Status\s*In lab/i.test(text) || text.includes("Already registered in Library")) return false;
      if (text.includes("Open in Library") && !text.includes("Add to lab")) return false;
      if (captureMode === "discover_acquire") {
        return text.includes("Probe source") || text.includes("Add to lab");
      }
      if (captureMode === "discover_probe") {
        return (
          text.includes("Probe result") ||
          text.includes("downloadable links") ||
          text.includes("access_mode") ||
          Boolean(document.querySelector(".rd-v2-discover-probe-error"))
        );
      }
      return true;
    },
    mode,
    { timeout: 20_000 },
  );
}

async function assertAskAddToLab(page) {
  await page.waitForFunction(() => {
    const ask = document.querySelector('[data-testid="ask-messages"]');
    const text = ask?.textContent || "";
    return text.includes("Add to lab vault") && text.includes("Candidate (structured)");
  }, { timeout: 45_000 });
}

async function runRouteInteractive(page, mode) {
  if (DISCOVER_INTERACTIVE.has(mode)) {
    return runDiscoverInteractive(page, mode);
  }

  if (mode === "home_signed_in") {
    await page.evaluate((email) => {
      localStorage.setItem("procure_user_email", email);
    }, FACULTY_EMAIL);
    await page.reload({ waitUntil: "load" });
    await waitForShell(page);
    await page.waitForFunction(() => {
      const block = document.querySelector(".rd-v2-home-suggested");
      return block && (block.textContent || "").trim().length > 20;
    }, { timeout: 45_000 });
    await page.waitForTimeout(800);
    return FACULTY_EMAIL;
  }

  if (mode === "ask_tab") {
    const rail = page.locator("aside.rd-v2-rail");
    await rail.getByRole("tab", { name: "Ask" }).click();
    await page.waitForSelector('[data-testid="ask-messages"]', { timeout: 20_000 });
    await page.waitForTimeout(500);
    return "";
  }

  if (mode === "library_preview") {
    const previewBtn = page.getByRole("button", { name: /Preview rows/i }).first();
    await previewBtn.waitFor({ state: "visible", timeout: 20_000 });
    await previewBtn.click();
    await page.waitForSelector('[role="dialog"]', { timeout: 30_000 });
    await page.waitForFunction(() => {
      const dlg = document.querySelector('[role="dialog"]');
      const text = dlg?.textContent || "";
      return text.includes("Preview") && (text.includes("entity_id") || text.includes("Sample") || text.includes("rows"));
    }, { timeout: 45_000 });
    await page.waitForTimeout(600);
    return "";
  }

  throw new Error(`unknown interactive mode: ${mode}`);
}

async function runDiscoverInteractive(page, mode) {
  const query = await loadAcquireSearch(page);
  await pickAcquireCandidate(page);
  const rail = page.locator("aside.rd-v2-rail");
  await rail.waitFor({ state: "visible", timeout: 20_000 });
  await page.waitForTimeout(400);
  await assertAcquireRail(page, "discover_acquire");

  if (mode === "discover_acquire") {
    return query;
  }

  const probeBtn = rail.getByRole("button", { name: "Probe source" });
  if (!(await probeBtn.isVisible())) {
    throw new Error(`discover-${mode}: Probe source button not visible (query=${query})`);
  }
  await probeBtn.click();
  await page.waitForFunction(() => {
    const root = document.querySelector("aside.rd-v2-rail");
    if (!root) return false;
    const text = root.textContent || "";
    return (
      text.includes("Probe result") ||
      text.includes("downloadable links") ||
      document.querySelector(".rd-v2-discover-probe-error")
    );
  }, { timeout: 60_000 });
  await assertAcquireRail(page, "discover_probe");

  if (mode === "discover_probe") {
    return query;
  }

  const addBtn = rail.locator(".rd-v2-rail-sticky .rd-v2-btn.primary", { hasText: "Add to lab" });
  if (!(await addBtn.count())) {
    throw new Error(`discover-ask: Add to lab button missing (query=${query})`);
  }
  await addBtn.click();
  await rail.getByRole("tab", { name: "Ask" }).click();
  await assertAskAddToLab(page);
  await page.waitForTimeout(600);
  return query;
}

async function waitForRouteReady(page, route) {
  const requireLive = process.env.YZU_REQUIRE_LIVE === "1";

  const run = async () => {
    if (route.slug === "discover-search") {
      await page.waitForFunction(() => {
        const text = document.body?.innerText || "";
        return !text.includes("Showing offline matches while live catalogs refresh");
      }, { timeout: 60_000 });

      await waitForDiscoverResults(page);
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

    if (route.slug === "library-stablecoin") {
      await page.waitForFunction(() => {
        const text = document.body?.innerText || "";
        return (
          text.includes("stablecoin") &&
          (text.includes("Stablecoin trust") || text.includes("panel_weekly"))
        );
      }, { timeout: 45_000 });
    }

    if (route.slug === "home-signed-in") {
      await page.waitForFunction(() => {
        const block = document.querySelector(".rd-v2-home-suggested");
        return block && (block.textContent || "").includes("Suggested");
      }, { timeout: 45_000 });
    }

    if (route.slug === "profile") {
      await page.waitForFunction(() => {
        const text = document.body?.innerText || "";
        return /Asst\.|Prof\.|research profile|Research tracks/i.test(text);
      }, { timeout: 45_000 });
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
    if (
      route.slug === "discover-search" ||
      route.slug === "discover-acquire" ||
      route.slug === "discover-probe" ||
      route.slug === "discover-ask" ||
      route.slug === "resources"
    ) {
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
  let acquireQuery = "";
  if (route.interactive) {
    acquireQuery = await runRouteInteractive(page, route.interactive);
  }

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
  return { viewport: vpName, route: route.slug, url, label: route.label, acquireQuery };
}

function buildPacketZips(manifest) {
  manifest.captured_at = new Date().toISOString();
  manifest.git_head = resolveManifestGitHead();
  const monorepoHead = gitHead();
  if (monorepoHead !== "unknown" && monorepoHead !== manifest.git_head) {
    manifest.monorepo_git_head = monorepoHead;
  }
  fs.writeFileSync(path.join(OUT_DIR, "manifest.json"), `${JSON.stringify(manifest, null, 2)}\n`);

  for (const target of [ZIP_PATH, PACKET_ZIP_PATH]) {
    if (fs.existsSync(target)) fs.unlinkSync(target);
  }

  const zipArgs = ["-r", ZIP_PATH, "docs/screenshots-review"];
  const zip = spawnSync("zip", zipArgs, { cwd: ROOT, encoding: "utf8" });
  if (zip.status !== 0) {
    console.error(zip.stderr || zip.stdout);
    process.exit(1);
  }

  const packetEntries = ["docs/screenshots-review", ...PACKET_DOCS.filter((rel) => fs.existsSync(path.join(ROOT, rel)))];
  const packetZip = spawnSync("zip", ["-r", PACKET_ZIP_PATH, ...packetEntries], {
    cwd: ROOT,
    encoding: "utf8",
  });
  if (packetZip.status !== 0) {
    console.error(packetZip.stderr || packetZip.stdout);
    process.exit(1);
  }
}

async function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });

  const manifest = {
    product: "Research Drive (YZU Cluster procurement desk)",
    captured_at: new Date().toISOString(),
    base_url: BASE_URL,
    github_repo: "Spectating101/yzu-cluster",
    github_screenshots_path: "docs/screenshots-review/",
    git_head: "pending",
    viewports: VIEWPORTS,
    routes: ROUTES.map((r) => ({ slug: r.slug, path: r.path, label: r.label })),
    files: [],
    require_live: process.env.YZU_REQUIRE_LIVE === "1",
    notes: [
      "Screenshots committed under docs/screenshots-review/ for ChatGPT + GitHub connector review.",
      "Zip at repo root: research-drive-screenshots.zip (screenshots only)",
      "Full ChatGPT packet: research-drive-chatgpt-packet.zip (screenshots + markdown evidence)",
      "Set YZU_REQUIRE_LIVE=1 to fail capture unless header shows Live registry (API on :8765).",
    ],
  };

  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
  });

  try {
    const onlyVp = (process.env.CAPTURE_VIEWPORTS || "").split(",").map((s) => s.trim()).filter(Boolean);
    const onlyRoutes = (process.env.CAPTURE_ROUTES || "").split(",").map((s) => s.trim()).filter(Boolean);
    const viewports = Object.entries(VIEWPORTS).filter(([name]) => !onlyVp.length || onlyVp.includes(name));
    const routes = ROUTES.filter((r) => !onlyRoutes.length || onlyRoutes.includes(r.slug));
    const ACQUIRE_SLUGS = new Set(["discover-acquire", "discover-probe", "discover-ask"]);

    for (const [vpName, viewport] of viewports) {
      const acquireRoutes = routes.filter((r) => ACQUIRE_SLUGS.has(r.slug));
      const otherRoutes = routes.filter((r) => !ACQUIRE_SLUGS.has(r.slug));

      if (acquireRoutes.length) {
        await captureDiscoverAcquisitionLadder(browser, vpName, viewport, manifest);
      }

      for (const route of otherRoutes) {
        const shot = await captureRoute(browser, vpName, viewport, route);
        manifest.files.push(`${vpName}-${route.slug}-viewport.png`);
        manifest.files.push(`${vpName}-${route.slug}-full.png`);
        if (shot.acquireQuery) manifest.acquire_query = shot.acquireQuery;
        console.log(`ok ${vpName} ${route.slug} → ${shot.url}${shot.acquireQuery ? ` (acquire: ${shot.acquireQuery})` : ""}`);
      }
    }
  } finally {
    await browser.close();
  }

  buildPacketZips(manifest);

  console.log(`\nWrote ${ZIP_PATH}`);
  console.log(`Wrote ${PACKET_ZIP_PATH}`);
  console.log("Upload research-drive-chatgpt-packet.zip to ChatGPT (screenshots + markdown evidence).");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
