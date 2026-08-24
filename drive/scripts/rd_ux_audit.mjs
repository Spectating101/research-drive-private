#!/usr/bin/env node
/**
 * Heuristic UX audit — flags weird/stale UI after nav v2 rebuild.
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const BASE = process.env.YZU_DESK_URL || "http://127.0.0.1:8765";
const OUT = path.resolve("docs/status/generated/rd-audit");
const REPORT = path.resolve("docs/status/generated/research-drive-ux-audit.json");
const HTML = path.resolve("docs/status/generated/research-drive-ux-audit.html");

function flag(id, severity, message, extra = {}) {
  return { id, severity, message, ...extra };
}

async function navSidebar(page, label) {
  await page.locator("aside.yzu-sidebar > nav").first().getByRole("button", { name: new RegExp(`^${label}`) }).click();
  await page.waitForTimeout(500);
}

async function auditPage(page) {
  const findings = [];
  const shots = [];

  async function shot(name) {
    const file = `${name}.png`;
    await page.screenshot({ path: path.join(OUT, file), fullPage: false });
    shots.push(file);
    return file;
  }

  async function domAudit() {
    return page.evaluate(() => {
      const text = (sel) => [...document.querySelectorAll(sel)].map((el) => el.textContent?.trim()).filter(Boolean);
      const visible = (el) => {
        if (!el) return false;
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 0 && r.height > 0 && s.visibility !== "hidden" && s.display !== "none" && s.opacity !== "0";
      };
      const headings = text("main h1, main h2, .rd-page-bar h1, .rd-home-head h1, .rd-chat-head h1");
      const loading = text(".rd-loading-row, .rd-skeleton-block").length;
      const loadingText = [...document.querySelectorAll("main *")].filter((el) => {
        const t = el.textContent?.trim();
        return t === "Loading…" || t === "Loading registry…" || t === "Searching…";
      }).filter(visible).map((el) => el.textContent?.trim());
      const badges = [...document.querySelectorAll(".yzu-nav-badge")].map((el) => ({
        label: el.closest("button")?.textContent?.replace(/\d+/g, "").trim(),
        count: el.textContent?.trim(),
        visible: visible(el),
      }));
      const duplicateH1 = headings.filter((h, i) => headings.indexOf(h) !== i);
      const staleStrings = ["Lab data library", "Featured datasets", "Lab Drive", "Source data", "Procurement dashboard"];
      const staleHits = staleStrings.filter((s) => document.body.innerText.includes(s));
      const mainProcure = document.querySelector("main .yzu-procure.main");
      const sinkProcure = document.querySelector(".rd-ask-sink .yzu-procure");
      const inspector = document.querySelector("aside.yzu-inspector");
      const inspectorVisible = inspector && visible(inspector);
      const viewClass = [...document.querySelector(".yzu-shell")?.classList || []].find((c) => c.startsWith("rd-view-"));
      const emptyAgent = document.querySelector("main .agent.empty");
      const chatHead = document.querySelector(".rd-chat-head h1")?.textContent?.trim();
      const pageBarHead = document.querySelector(".rd-page-bar h1")?.textContent?.trim();
      const discoverCards = document.querySelectorAll(".rd-discover-card").length;
      const discoverRows = document.querySelectorAll(".rd-result-row").length;
      const catalogRows = document.querySelectorAll(".rd-catalog-table tbody tr:not(.rd-skeleton-row)").length;
      const clusterLanes = document.querySelectorAll(".rd-cluster-lane").length;
      const clusterCards = document.querySelectorAll(".rd-cluster-card").length;
      const browseVisible = !!document.querySelector(".rd-browse-surface");
      const overflowX = document.documentElement.scrollWidth > window.innerWidth + 2;
      const lowContrast = [...document.querySelectorAll(".muted")].filter(visible).length;
      return {
        headings,
        duplicateH1,
        loading,
        loadingText: [...new Set(loadingText)],
        badges,
        staleHits,
        mainProcureVisible: mainProcure && visible(mainProcure),
        sinkProcurePresent: !!sinkProcure,
        inspectorVisible,
        viewClass,
        emptyAgentVisible: emptyAgent && visible(emptyAgent),
        chatHead,
        pageBarHead,
        discoverCards,
        discoverRows,
        catalogRows,
        clusterLanes,
        clusterCards,
        browseVisible,
        overflowX,
        lowContrast,
        bodySnippet: document.body.innerText.slice(0, 800),
      };
    });
  }

  // ── Home ──
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: /What the lab holds/i }).waitFor({ timeout: 30_000 });
  await page.waitForTimeout(800);
  let d = await domAudit();
  await shot("01-home");
  if (!d.headings.some((h) => /What the lab holds/i.test(h))) {
    findings.push(flag("home-heading", "high", "Home L1 heading missing"));
  }
  if (d.loadingText.length) {
    findings.push(flag("home-loading", "medium", `Home still shows loading: ${d.loadingText.join(", ")}`));
  }
  if (d.staleHits.length) {
    findings.push(flag("home-stale", "medium", `Stale copy on home: ${d.staleHits.join(", ")}`));
  }
  if (d.catalogRows === 0) {
    findings.push(flag("home-empty-table", "medium", "Home featured table has 0 data rows"));
  }
  if (d.headings.length > 2) {
    findings.push(flag("home-heading-noise", "low", `Home has ${d.headings.length} headings: ${d.headings.join(" | ")}`));
  }

  // ── Drive ──
  await navSidebar(page, "Drive");
  await page.getByRole("heading", { name: "Drive", exact: true }).waitFor({ timeout: 15_000 });
  await page.waitForTimeout(600);
  d = await domAudit();
  await shot("02-drive-all");
  if (d.staleHits.includes("Lab Drive")) {
    findings.push(flag("drive-stale-scope", "medium", '"Lab Drive" still visible in Drive view (should be "Lab")'));
  }
  const scopeLabels = await page.locator(".rd-col-scope").allTextContents();
  if (scopeLabels.some((s) => /Lab Drive/i.test(s))) {
    findings.push(flag("drive-scope-column", "low", `Scope column still says "Lab Drive": ${scopeLabels.filter((s) => /Lab Drive/i.test(s)).slice(0, 3).join(", ")}`));
  }

  await page.getByRole("button", { name: "Lab", exact: true }).click();
  await page.waitForTimeout(400);
  d = await domAudit();
  await shot("03-drive-lab");
  if (d.catalogRows === 0) {
    findings.push(flag("drive-lab-empty", "high", "Lab Drive scope shows 0 catalog rows"));
  }

  // ── Discover ──
  await navSidebar(page, "Discover");
  await page.getByRole("heading", { name: /^Discover$/ }).waitFor({ timeout: 15_000 });
  await page.waitForFunction(
    () => document.querySelector(".rd-discover-card, .rd-discover-empty, .rd-discover-skeleton"),
    { timeout: 45_000 },
  );
  await page.waitForTimeout(600);
  d = await domAudit();
  await shot("04-discover");
  if (d.loadingText.includes("Searching…")) {
    findings.push(flag("discover-stuck-loading", "medium", "Discover still shows 'Searching…' after wait"));
  }
  if (d.discoverRows > 0 && d.discoverCards === 0) {
    findings.push(flag("discover-old-layout", "high", "Discover still uses old .rd-result-row list, not card grid"));
  }
  if (d.discoverCards === 0 && !d.bodySnippet.includes("No results")) {
    findings.push(flag("discover-no-cards", "medium", "Discover has no cards and no empty state"));
  }

  // Browse drill-in
  const browseBtn = page.locator(".rd-discover-card").first().getByRole("button", { name: "Browse" });
  if (await browseBtn.count()) {
    await browseBtn.click();
    await page.waitForTimeout(600);
    d = await domAudit();
    await shot("05-browse");
    if (!d.browseVisible) {
      findings.push(flag("browse-missing", "high", "Browse button did not open Browse view"));
    }
    if (d.inspectorVisible) {
      findings.push(flag("browse-inspector", "low", "Inspector still visible on Browse (expected hidden)"));
    }
    await page.getByRole("button", { name: /Discover/ }).first().click();
    await page.waitForTimeout(400);
  } else {
    findings.push(flag("browse-skip", "low", "No discover cards — skipped Browse drill-in"));
  }

  // ── Cluster ──
  await navSidebar(page, "Cluster");
  await page.getByRole("heading", { name: /^Cluster$/ }).waitFor({ timeout: 15_000 });
  await page.waitForTimeout(500);
  d = await domAudit();
  await shot("06-cluster");
  if (d.clusterCards > 0 && d.clusterLanes === 0) {
    findings.push(flag("cluster-old-layout", "medium", "Cluster still uses old .rd-cluster-card buckets"));
  }
  if (d.bodySnippet.includes("Procured") || d.bodySnippet.includes("Web scrape")) {
    findings.push(flag("cluster-stale-domains", "low", 'Cluster shows legacy bucket names like "Procured" / "Web scrape"'));
  }

  // ── Chat ──
  await navSidebar(page, "Chat");
  await page.getByRole("heading", { name: /Source & compare/i }).waitFor({ timeout: 15_000 });
  await page.waitForTimeout(500);
  d = await domAudit();
  await shot("07-chat");
  if (!d.mainProcureVisible) {
    findings.push(flag("chat-not-visible", "high", "Chat procure panel not visible in main"));
  }
  if (d.chatHead && d.pageBarHead) {
    findings.push(flag("chat-double-chrome", "medium", `Duplicate headers: chat-head="${d.chatHead}" + page-bar="${d.pageBarHead}"`));
  }
  if (d.inspectorVisible) {
    findings.push(flag("chat-inspector", "low", "Inspector visible on Chat (expected hidden)"));
  }
  const chatBadges = d.badges.filter((b) => /Chat/i.test(b.label || "") && b.visible);
  if (chatBadges.length) {
    findings.push(flag("chat-nav-badge", "medium", `Chat nav still has badge: ${JSON.stringify(chatBadges)}`));
  }

  // ── Activity ──
  await navSidebar(page, "Activity");
  await page.getByRole("heading", { name: /^Activity$/ }).waitFor({ timeout: 15_000 });
  await page.waitForTimeout(400);
  d = await domAudit();
  await shot("08-activity");
  if (d.headings.some((h) => /Procurement dashboard/i.test(h))) {
    findings.push(flag("activity-stale-title", "medium", 'Activity still titled "Procurement dashboard"'));
  }

  // ── Nav badges ──
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(400);
  d = await domAudit();
  const noisyBadges = d.badges.filter((b) => b.visible && b.count && !/Activity/i.test(b.label || ""));
  if (noisyBadges.length) {
    findings.push(flag("nav-noisy-badges", "medium", `Non-activity nav badges: ${noisyBadges.map((b) => `${b.label}=${b.count}`).join(", ")}`));
  }

  // ── Mobile stress ──
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(600);
  d = await domAudit();
  await shot("09-mobile");
  if (d.overflowX) {
    findings.push(flag("mobile-overflow", "medium", "Horizontal overflow on 390px viewport"));
  }

  return { findings, shots };
}

function buildHtml(report) {
  const bySeverity = { high: [], medium: [], low: [] };
  for (const f of report.findings) {
    (bySeverity[f.severity] || bySeverity.low).push(f);
  }
  const li = (arr) => arr.map((f) => `<li><strong>${f.id}</strong> — ${f.message}</li>`).join("\n");
  const shots = report.shots.map((s) => `<figure><img src="rd-audit/${s}" alt="${s}" /><figcaption>${s}</figcaption></figure>`).join("\n");
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>RD UX audit</title>
<style>
body{font-family:system-ui;background:#0a0e12;color:#e8eef4;margin:0;padding:24px}
h1{margin:0 0 8px} .meta{color:#8fa3b8;margin-bottom:24px}
.high{color:#f4a4a4}.medium{color:#f0c674}.low{color:#9aa8ba}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:16px;margin-top:24px}
figure{margin:0;background:#121820;border:1px solid #243040;border-radius:10px;overflow:hidden}
img{width:100%;display:block} figcaption{padding:8px 12px;font-size:12px;color:#8fa3b8}
ul{line-height:1.6}
</style></head><body>
<h1>Research Drive UX audit</h1>
<p class="meta">${report.at} · ${report.findings.length} findings · <a href="${BASE}">${BASE}</a></p>
<h2 class="high">High (${bySeverity.high.length})</h2><ul>${li(bySeverity.high) || "<li>none</li>"}</ul>
<h2 class="medium">Medium (${bySeverity.medium.length})</h2><ul>${li(bySeverity.medium) || "<li>none</li>"}</ul>
<h2 class="low">Low (${bySeverity.low.length})</h2><ul>${li(bySeverity.low) || "<li>none</li>"}</ul>
<h2>Screenshots</h2><div class="grid">${shots}</div>
</body></html>`;
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ headless: true, args: ["--disable-dev-shm-usage", "--no-sandbox"] });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const { findings, shots } = await auditPage(page);
  await browser.close();

  const report = { at: new Date().toISOString(), base: BASE, findings, shots };
  fs.writeFileSync(REPORT, JSON.stringify(report, null, 2));
  fs.writeFileSync(HTML, buildHtml(report));
  console.log(JSON.stringify({ findings: findings.length, high: findings.filter((f) => f.severity === "high").length }, null, 2));
  console.log(HTML);
  console.log(`file://${HTML}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
