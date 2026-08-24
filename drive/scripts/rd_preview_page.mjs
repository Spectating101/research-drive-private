#!/usr/bin/env node
/**
 * Capture desk screenshots + emit a single HTML check page (live iframe + gallery).
 * Selectors aligned with docs/RESEARCH_DRIVE_UI_CONTRACT.md
 */
import { chromium } from "playwright";
import fs from "fs";
import path from "path";

const BASE = process.env.YZU_DESK_URL || "http://127.0.0.1:8765";
const OUT = path.resolve("docs/status/generated/rd-preview");
const HTML = path.resolve("docs/status/generated/research-drive-check.html");

const VIEWS = [
  { id: "home", nav: null, wait: /^Home$/ },
  { id: "drive-all", nav: "Drive", wait: /^Drive$/ },
  { id: "drive-lab", nav: "Drive", click: "Lab", wait: /^Drive$/ },
  { id: "discover", nav: "Discover", wait: /^Discover$/ },
  { id: "chat", nav: "Chat", wait: /Source & compare/i },
  { id: "cluster", nav: "Cluster", wait: /^Cluster$/ },
  { id: "activity", nav: "Activity", wait: /^Activity$/ },
];

async function navSidebar(page, label) {
  await page.locator("aside.yzu-sidebar > nav").first().getByRole("button", { name: new RegExp(`^${label}`) }).click();
  await page.waitForTimeout(500);
}

async function captureView(page, view) {
  if (view.nav) await navSidebar(page, view.nav);
  if (view.click) {
    await page.getByRole("button", { name: view.click, exact: true }).click();
    await page.waitForTimeout(400);
  }
  if (view.wait) {
    await page.getByRole("heading", { name: view.wait }).waitFor({ timeout: 30_000 }).catch(() => {});
  }
  if (view.id === "home") {
    await page.getByRole("heading", { name: "Recent" }).waitFor({ timeout: 15_000 }).catch(() => {});
  }
  if (view.id === "discover") {
    await page.waitForFunction(
      () => document.querySelector(".rd-discover-card, .rd-discover-empty, .rd-discover-skeleton"),
      { timeout: 60_000 },
    ).catch(() => {});
  }
  if (view.id.startsWith("drive")) {
    await page.waitForSelector(".rd-catalog-table tbody tr", { timeout: 20_000 }).catch(() => {});
  }
  await page.waitForTimeout(400);
  const file = `${view.id}.png`;
  await page.screenshot({ path: path.join(OUT, file), fullPage: false });
  const h1 = await page.locator(".rd-page-bar h1, .rd-home-head h1, .rd-chat-head h1").first().textContent().catch(() => "");
  return { id: view.id, file, h1: (h1 || "").trim(), label: view.nav || "Home" };
}

function buildHtml(meta, shots, problems) {
  const rel = "rd-preview";
  const cards = shots
    .map(
      (s) => `
    <figure class="shot">
      <figcaption><strong>${s.id}</strong> — ${s.h1 || s.label}</figcaption>
      <a href="${rel}/${s.file}" target="_blank"><img src="${rel}/${s.file}" alt="${s.id}" loading="lazy" /></a>
    </figure>`,
    )
    .join("\n");

  const problemList = problems.length
    ? `<ul class="problems">${problems.map((p) => `<li>${p}</li>`).join("")}</ul>`
    : `<p class="ok">Contract-aligned capture — no flags.</p>`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Research Drive — visual check</title>
  <style>
    :root { --bg: #0f1419; --panel: #151c24; --line: #243040; --text: #e8eef4; --muted: #8fa3b8; --accent: #6eb5ff; }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: system-ui, sans-serif; background: var(--bg); color: var(--text); line-height: 1.5; }
    header { padding: 20px 24px; border-bottom: 1px solid var(--line); background: var(--panel); }
    header h1 { margin: 0 0 6px; font-size: 1.35rem; }
    header p { margin: 0; color: var(--muted); font-size: 0.95rem; }
    header a { color: var(--accent); }
    .live { padding: 20px 24px; border-bottom: 1px solid var(--line); }
    .live h2 { margin: 0 0 12px; font-size: 1rem; }
    iframe { width: 100%; height: 720px; border: 1px solid var(--line); border-radius: 12px; background: #000; }
    .gallery { padding: 20px 24px 40px; }
    .gallery h2 { margin: 0 0 16px; font-size: 1rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(420px, 1fr)); gap: 16px; }
    .shot { margin: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }
    .shot figcaption { padding: 10px 14px; font-size: 0.85rem; border-bottom: 1px solid var(--line); }
    .shot img { display: block; width: 100%; height: auto; }
    .meta { padding: 0 24px 20px; color: var(--muted); font-size: 0.85rem; }
    .problems { color: #f0b86e; }
    .ok { color: #7dcea0; }
  </style>
</head>
<body>
  <header>
    <h1>Research Drive — visual check</h1>
    <p>Captured ${meta.at} · contract v1 · <a href="${BASE}" target="_blank">${BASE}</a></p>
  </header>
  <section class="live">
    <h2>Live app (iframe)</h2>
    <iframe src="${BASE}" title="Research Drive live"></iframe>
  </section>
  <section class="meta">${problemList}</section>
  <section class="gallery">
    <h2>Screenshots (click to open full size)</h2>
    <div class="grid">${cards}</div>
  </section>
</body>
</html>`;
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({
    headless: true,
    args: ["--disable-dev-shm-usage", "--no-sandbox"],
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  const problems = [];

  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 }).catch(() => {
    problems.push("Home not found — API down or stale bundle");
  });

  const shots = [];
  for (const view of VIEWS) {
    try {
      if (view.id === "home") {
        await page.goto(BASE, { waitUntil: "domcontentloaded" });
        await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 15_000 });
      }
      shots.push(await captureView(page, view));
    } catch (err) {
      problems.push(`${view.id}: ${err.message}`);
    }
  }

  await browser.close();

  const meta = { base: BASE, at: new Date().toISOString() };
  fs.writeFileSync(path.join(OUT, "meta.json"), JSON.stringify({ meta, shots, problems }, null, 2));
  fs.writeFileSync(HTML, buildHtml(meta, shots, problems));

  console.log(HTML);
  console.log(`file://${HTML}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
