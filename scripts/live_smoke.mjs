/**
 * Live smoke against a running front door.
 *
 * Loads every destination at desktop and mobile and fails on any JS error,
 * any 4xx/5xx, or horizontal overflow. Written after a deploy where the only
 * verification available was "the page returned 200", which says nothing about
 * whether the app actually rendered.
 *
 * Usage:
 *   YZU_DESK_URL=http://127.0.0.1:8765 \
 *   YZU_DESK_ACCESS_TOKEN=... \
 *   node scripts/live_smoke.mjs
 *
 * Exits non-zero if any page has an issue, so it can gate a promotion.
 */
import { chromium } from "@playwright/test";

const BASE = process.env.YZU_DESK_URL || "http://127.0.0.1:8765";
const TOKEN = process.env.YZU_DESK_ACCESS_TOKEN || "";

const PAGES = [
  ["home", "/?tab=home"],
  ["library", "/?tab=library"],
  ["discover", "/?tab=browse"],
  ["discover-history", "/?tab=browse&mode=history"],
  ["synthesis", "/?tab=synthesis"],
  ["resources", "/?tab=resources"],
  ["profile", "/?tab=profile"],
  ["settings", "/?tab=settings"],
  ["cluster", "/?tab=cluster"],
];
const VIEWPORTS = [
  ["desktop", { width: 1440, height: 900 }],
  ["mobile", { width: 390, height: 844 }],
];

const browser = await chromium.launch();
let failures = 0;

for (const [vpName, viewport] of VIEWPORTS) {
  for (const [name, path] of PAGES) {
    const ctx = await browser.newContext({
      viewport,
      extraHTTPHeaders: TOKEN ? { "X-Desk-Token": TOKEN } : {},
    });
    const page = await ctx.newPage();
    const jsErrors = [];
    const badResponses = [];
    page.on("pageerror", (e) => jsErrors.push(e.message.slice(0, 120)));
    page.on("response", (r) => {
      if (r.status() >= 400) badResponses.push(`${r.status()} ${r.url().replace(BASE, "").split("?")[0]}`);
    });

    try {
      await page.goto(BASE + path, { waitUntil: "domcontentloaded", timeout: 30000 });
      await page.waitForTimeout(4000);
      const heading = (await page.locator("h1").first().innerText().catch(() => "—")).trim();
      const overflows = await page.evaluate(
        () => document.documentElement.scrollWidth > window.innerWidth + 1,
      );
      const unique = [...new Set(badResponses)];
      const bad = jsErrors.length || unique.length || overflows;
      if (bad) failures += 1;
      console.log(
        `${bad ? "FAIL" : "ok  "} ${vpName.padEnd(7)} ${name.padEnd(17)} h1="${heading}" ` +
          `js=${jsErrors.length} http>=400=${unique.length} overflow=${overflows}` +
          (bad ? `  ${[...jsErrors, ...unique].slice(0, 3).join(" ; ")}` : ""),
      );
    } catch (error) {
      failures += 1;
      console.log(`FAIL ${vpName.padEnd(7)} ${name.padEnd(17)} load failed: ${String(error).slice(0, 90)}`);
    }
    await ctx.close();
  }
}

await browser.close();
console.log(`\n${failures ? `${failures} page(s) with issues` : "all pages clean"} (${PAGES.length * VIEWPORTS.length} checked)`);
process.exit(failures ? 1 : 0);
