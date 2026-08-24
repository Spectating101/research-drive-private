#!/usr/bin/env node
/**
 * Honest UI audit — screenshots + DOM facts, not just pass/fail e2e.
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const BASE = process.env.YZU_DESK_URL || "http://127.0.0.1:8765";
const OUT = path.resolve("docs/status/generated/ui-audit-now");

async function facts(page) {
  return page.evaluate(() => {
    const vis = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return false;
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    const text = (sel) => document.querySelector(sel)?.textContent?.trim() || null;
    const count = (sel) => document.querySelectorAll(sel).length;
    return {
      h1: text(".rd-page-bar h1, .rd-hero h1"),
      subtitle: text(".rd-page-sub, .rd-hero .lead"),
      quickTiles: count(".rd-quick-tile"),
      libraryStats: vis(".rd-library-stats"),
      procureFootnote: vis(".rd-procure-footnote"),
      detailsIdle: vis(".rd-inspector-idle"),
      detailsPanel: vis(".rd-inspector-compact"),
      inspectorTabDetails: text(".rd-inspector-tabs button.active"),
      signInBanner: vis(".rd-signin-banner"),
      storageStrip: vis(".rd-storage-strip"),
      inspectorTabs: count(".rd-inspector-tabs button"),
      assistantHead: text(".ds-console-head h3"),
      selectionBar: vis(".rd-selection-bar"),
      scopeChip: vis(".rd-scope-chip"),
      discoverFilters: count(".rd-discover-toolbar .rd-chip"),
      actionChips: count(".yzu-advice-recs .yzu-chip"),
      actionStackBtns: count(".rd-action-btn"),
      selectedContext: vis(".rd-assistant-context"),
      recentRows: count(".rd-library-table tbody tr:not(.rd-skeleton-row)"),
      recentTitles: [...document.querySelectorAll(".rd-library-table .rd-title")].map((e) => e.textContent?.trim()).slice(0, 5),
      headerButtons: [...document.querySelectorAll(".rd-top-actions .btn-round")].map((e) => e.textContent?.trim()),
      searchPlaceholder: document.querySelector(".rd-search input")?.getAttribute("placeholder"),
      llmWarn: [...document.querySelectorAll(".yzu-banner.warn")].some((e) => e.textContent?.includes("LLM")),
      mainEmpty: (document.querySelector("main")?.innerText || "").length < 80,
      bundleHint: [...document.querySelectorAll("script[src]")].map((s) => s.getAttribute("src")).join(" "),
    };
  });
}

async function navSidebar(page, label) {
  await page.locator("aside.yzu-sidebar > nav").first().getByRole("button", { name: new RegExp(`^${label}`) }).click();
  await page.waitForTimeout(800);
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu"],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const report = { base: BASE, at: new Date().toISOString(), views: [], problems: [] };

  const shots = [];

  async function capture(name, extraWait = 0) {
    if (extraWait) await page.waitForTimeout(extraWait);
    const shot = path.join(OUT, `${name}.png`);
    try {
      await page.screenshot({ path: shot, fullPage: false });
    } catch (err) {
      report.problems.push(`${name}: screenshot failed (${err.message})`);
    }
    const f = await facts(page);
    report.views.push({ name, ...f, screenshot: shot });
    shots.push(name);
    return f;
  }

  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: /Lab data library/i }).waitFor({ timeout: 30_000 }).catch(() => {});
  await page.waitForTimeout(2500);

  const homeBeforeClick = await capture("01-home-initial", 0);
  if (homeBeforeClick.assistantHead === "Source data") report.problems.push("home: source chat visible before opt-in");
  if (!homeBeforeClick.libraryStats) report.problems.push("home: library stats strip missing");
  if (!homeBeforeClick.detailsIdle) report.problems.push("home: details idle state missing");
  const pillW = await page.evaluate(() => document.querySelector(".rd-library-table .rd-pill")?.getBoundingClientRect().width || 0);
  if (homeBeforeClick.recentRows === 0) report.problems.push("home: no featured dataset rows");

  if (pillW < 20) report.problems.push(`home: status pills collapsed (width=${pillW})`);

  await page.locator(".rd-library-table tbody tr").first().click({ timeout: 10000 }).catch(() => {});
  await page.waitForTimeout(400);
  const homeAfterClick = await capture("02-home-row-selected");
  if (!homeAfterClick.detailsPanel) report.problems.push("home: dataset details missing after row click");
  if (!homeAfterClick.selectionBar) report.problems.push("home: selection toolbar missing after row click");

  await navSidebar(page, "Discover");
  await page.waitForFunction(
    () => document.querySelector(".rd-result-list .rd-result-row, .rd-result-list .rd-result-empty, .rd-result-list p"),
    { timeout: 45000 },
  ).catch(() => {});
  const discover = await capture("03-discover", 500);
  if (discover.h1 !== "Discover") report.problems.push(`discover: unexpected title ${discover.h1}`);
  if (discover.discoverFilters < 5) report.problems.push(`discover: expected 5 filter chips, got ${discover.discoverFilters}`);

  await navSidebar(page, "Drive");
  await page.waitForSelector(".rd-catalog-table tbody tr, .yzu-drive-table tbody tr", { timeout: 20000 }).catch(() => {});
  const lab = await capture("04-drive");
  if (lab.inspectorTabs > 0 && !homeAfterClick.detailsPanel) {
    report.problems.push("lab: inspector tabs without details context");
  }

  await navSidebar(page, "Activity");
  await capture("05-activity");

  await browser.close();

  report.screenshots = shots;
  fs.writeFileSync(path.join(OUT, "report.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ out: OUT, problems: report.problems, views: report.views.map((v) => ({ name: v.name, h1: v.h1, quickTiles: v.quickTiles, actionChips: v.actionChips })) }, null, 2));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
