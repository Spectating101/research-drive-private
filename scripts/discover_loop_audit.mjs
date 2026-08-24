#!/usr/bin/env node
/**
 * Discover Loop Anchor — headless 1920 audit (functional metrics).
 * Exit 0 only if card→search, status settle, and query preserve pass.
 */
import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const OUT = join(ROOT, "drive/.playwright-mcp");
const BASE = process.env.DISCOVER_AUDIT_URL || "http://127.0.0.1:5179";

mkdirSync(OUT, { recursive: true });

const failures = [];
const note = (k, ok, detail) => {
  const row = { k, ok, detail };
  console.log(JSON.stringify(row));
  if (!ok) failures.push(row);
};

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });

try {
  await page.goto(`${BASE}/?tab=browse`, { waitUntil: "domcontentloaded", timeout: 45000 });
  await page.waitForSelector(".rd-v2-shell", { timeout: 30000 });
  await page.waitForTimeout(600);

  // 1. Suggested card commits search
  const card = page.getByTestId("discover-suggested-card").first();
  const title = await card.locator("strong").innerText();
  await card.click();
  await page.waitForTimeout(2000);
  const afterCard = {
    empty: await page.getByTestId("discover-empty").count(),
    value: await page.getByTestId("discover-search-input").inputValue(),
    rows: await page.locator(".rd-v2-discover-candidate").count(),
    summary: await page.locator(".rd-v2-discover-search-summary").innerText().catch(() => ""),
  };
  note(
    "card-commits-search",
    afterCard.empty === 0 && afterCard.value === title && afterCard.rows > 0,
    afterCard,
  );
  note(
    "status-not-stuck-after-card",
    !/Checking|updating/i.test(afterCard.summary),
    afterCard.summary,
  );

  // 2. Query preserve across modes
  await page.getByTestId("discover-mode-toggle").getByRole("button", { name: /Activity/ }).click();
  await page.waitForTimeout(500);
  await page.getByTestId("discover-mode-toggle").getByRole("button", { name: "Search" }).click();
  await page.waitForTimeout(1500);
  const afterMode = await page.getByTestId("discover-search-input").inputValue();
  note("query-preserved", afterMode === title, { afterMode, title });

  // 3. Void under SERP list (list should own flex space — void below list panel content ok if panel fills)
  const voidMetrics = await page.evaluate(() => {
    const body = document.querySelector(".rd-v2-discover-page .rd-v2-body-scroll");
    const list = document.querySelector(".rd-v2-discover-list-panel");
    if (!body || !list) return { ok: false, reason: "missing" };
    const br = body.getBoundingClientRect();
    const lr = list.getBoundingClientRect();
    const voidBelowList = Math.round(br.bottom - lr.bottom);
    const listFills = lr.height >= br.height * 0.45;
    return { voidBelowList, listH: Math.round(lr.height), bodyH: Math.round(br.height), listFills };
  });
  note(
    "serp-density",
    voidMetrics.listFills || voidMetrics.voidBelowList <= 320,
    voidMetrics,
  );

  await page.screenshot({ path: join(OUT, "discover-loop-audit-1920.png"), fullPage: false });
  writeFileSync(join(OUT, "discover-loop-audit.json"), JSON.stringify({ failures, voidMetrics }, null, 2));
} finally {
  await browser.close();
}

if (failures.length) {
  console.error(`DISCOVER_LOOP_AUDIT_FAIL ${failures.length}`);
  process.exit(1);
}
console.log("DISCOVER_LOOP_AUDIT_OK");
process.exit(0);
