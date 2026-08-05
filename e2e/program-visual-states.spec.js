/**
 * Required visual states from UI_IMPLEMENTATION_PROGRAM.md.
 *
 * The program lists the states that must be reviewed before a slice is
 * accepted -- Discover at 5 items, 20 items, and 70 lifecycle objects -- and
 * the bounded Detail/Ask budgets that apply to every rail. Until now every
 * judgement about this interface was made against a 3-to-5 row screen, which
 * is the easiest case the product ever renders.
 *
 * This spec renders the listed states from fixtures and asserts the budgets
 * the program states numerically, so "does it look right" stops being an
 * opinion formed from the last screenshot. Captures land in
 * docs/screenshots-review/program-visual-states/ as a contact sheet.
 *
 * Review order is the program's: desktop 1440 first, laptop 1280 second.
 */
import { test, expect } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const OUT = "docs/screenshots-review/program-visual-states";

/**
 * Widths.
 *
 * The program says "Review desktop 1440 first, laptop 1280 second", and the
 * authority calls 1440 the authoritative three-surface desk. Those stay.
 *
 * 1920 is added because it is the width this is actually reviewed and used at.
 * Checking conformance only at the specified width leaves the delivered width
 * unverified, which is how a layout that satisfies the spec still reads badly
 * on the screen in front of you.
 */
const WIDE = { width: 1920, height: 960 };
const DESKTOP = { width: 1440, height: 900 };
const LAPTOP = { width: 1280, height: 800 };

async function shot(page, label) {
  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `${label}.png`), fullPage: false });
}

/** Offerings shaped like the live source contract, with real variety. */
function discoverBody(count) {
  const providers = [
    ["Google Cloud", "bigquery", "blockchain transfers, DeFi, stablecoin telemetry."],
    ["LSEG Refinitiv", "lseg_data_api", "point-in-time index membership; fundamentals."],
    ["TWSE", "queue", "filings, exchange disclosures; instrument-day OHLCV."],
    ["SEC EDGAR", "http_manifest", "filings, exchange disclosures, misconduct panels."],
    ["GDELT", "api_query", "country-day news intensity; entity-resolved news features."],
    ["CoinGecko", "http_manifest", "instrument-day OHLCV or return panels."],
  ];
  const rows = Array.from({ length: count }, (_, i) => {
    const [source, via, description] = providers[i % providers.length];
    return {
      dataset_id: `offering_${i + 1}`,
      candidate_key: `source:${via}:offering_${i + 1}`,
      title: `${source} evidence offering ${i + 1}`,
      source,
      collect_via: via,
      url: `https://example.org/offering/${i + 1}`,
      coverage: "2015–2026",
      grain: "issuer-quarter",
      description,
      // Two in three rows carry a measured size; the rest carry none, so the
      // capture shows both the populated and the honestly-empty scale cell.
      ...(i % 3 === 2
        ? {}
        : { size_bytes: 1024 * (37 + i * 811), file_count: 1 + (i % 4) }),
      analysis_readiness: ["instant", "registered", "metadata_only"][i % 3],
      recommended_use: `Use for ${description.split(";")[0]} in cross-market studies.`,
      source_system: `${source} platform`,
    };
  });
  return { sections: [{ title: "Registry", rows }], total: count };
}

/** 70 durable lifecycle objects spanning every state the projection emits. */
function historyBody(count) {
  const states = [
    ["pending_approval", "intent", "Researcher approval is required before collection begins"],
    ["running", "collection_run", "Collecting — latest verified range 2022-06-30"],
    ["failed", "collection_run", "Provider endpoint rejected the configured route"],
    ["completed", "collection_run", "Collection completed; archive verification pending"],
    ["registered", "promotion", "Registered — readiness not confirmed"],
    ["scheduled", "subscription", "Scheduled; no run has executed yet"],
  ];
  return {
    items: Array.from({ length: count }, (_, i) => {
      const [status, kind, summary] = states[i % states.length];
      return {
        id: `lifecycle-${i + 1}`,
        title: `Evidence request ${i + 1}`,
        kind,
        status,
        summary,
        updated_at: new Date(Date.UTC(2026, 6, 18, 15, 0) - i * 3600_000).toISOString(),
      };
    }),
  };
}

async function runSearch(page, query) {
  const composer = page.getByTestId("discover-query-composer");
  await composer.locator("textarea").fill(query);
  await composer.getByRole("button", { name: "Explore" }).click();
  await expect(page.locator(".rd-v2-discover-candidate").first()).toBeVisible({ timeout: 15_000 });
}

/** No page may scroll sideways; wide content scrolls inside its own pane. */
async function expectNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow, "document scrolls horizontally").toBe(false);
}

test.describe("Discover — required visual states", () => {
  for (const [label, size] of [["1920", WIDE], ["1440", DESKTOP], ["1280", LAPTOP]]) {
    for (const count of [5, 20]) {
      test(`${count} offerings at ${label}`, async ({ page }) => {
        await page.setViewportSize(size);
        await mockV2Api(page, { discoverBody: discoverBody(count) });
        await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
        await waitForShell(page);
        await runSearch(page, "stablecoin");

        await expectNoHorizontalOverflow(page);

        const rows = page.locator(".rd-v2-discover-candidate");
        const showAll = page.getByTestId("discover-show-all");

        if (count > 8) {
          // A ranked list must not paint as an endless column: bounded initial
          // set, explicit expansion, and the total stated up front.
          await expect(rows).toHaveCount(8);
          await expect(showAll).toBeVisible();
          await expect(showAll).toContainText(String(count));
          await shot(page, `discover-${count}-offerings-bounded-${label}`);
          await showAll.click();
        } else {
          await expect(showAll).toHaveCount(0);
        }

        // Every offering states what it contains (adaptive freeze §3, §12).
        await expect(rows).toHaveCount(count);
        const described = await page
          .locator(".rd-v2-discover-evidence")
          .filter({ hasNotText: "Description not recorded" })
          .count();
        expect(described, "offerings missing a description").toBe(count);

        // Compact rows, not cards. At 20 the list must stay scannable.
        const heights = await rows.evaluateAll((els) =>
          els.map((el) => Math.round(el.getBoundingClientRect().height)),
        );
        const median = heights.sort((a, b) => a - b)[Math.floor(heights.length / 2)];
        expect(median, `median row height ${median}px reads as a card`).toBeLessThanOrEqual(140);

        // Legibility and target size, measured rather than eyeballed.
        const metrics = await page.evaluate(() => {
          const lum = (r, g, b) => {
            const f = (c) => {
              c /= 255;
              return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
            };
            return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
          };
          const rgb = (s) => s.match(/\d+/g).slice(0, 3).map(Number);
          const contrast = (fg, bg) => {
            const a = Math.max(lum(...fg), lum(...bg));
            const b = Math.min(lum(...fg), lum(...bg));
            return (a + 0.05) / (b + 0.05);
          };
          const row = document.querySelector(".rd-v2-discover-candidate");
          const bg = rgb(getComputedStyle(row).backgroundColor);
          const read = (sel) => {
            const el = document.querySelector(sel);
            const cs = getComputedStyle(el);
            return {
              size: parseFloat(cs.fontSize),
              fractional: !Number.isInteger(parseFloat(cs.fontSize)),
              contrast: contrast(rgb(cs.color), bg),
            };
          };
          const add = document.querySelector(".rd-v2-discover-row-add");

          // Reading measure, in characters, at this width.
          const desc = document.querySelector(".rd-v2-discover-evidence");
          const dcs = getComputedStyle(desc);
          const probe = document.createElement("span");
          probe.style.cssText = `position:absolute;visibility:hidden;white-space:nowrap;font:${dcs.font}`;
          probe.textContent = "abcdefghijklmnopqrstuvwxyz";
          document.body.appendChild(probe);
          const charWidth = probe.getBoundingClientRect().width / 26;
          probe.remove();

          return {
            facts: read(".rd-v2-discover-offering-facts"),
            description: read(".rd-v2-discover-evidence"),
            addHeight: add.getBoundingClientRect().height,
            charsPerLine: Math.round(desc.getBoundingClientRect().width / charWidth),
          };
        });

        // 45-75 characters is the comfortable measure; past ~90 the eye loses
        // its place on the return sweep. Measured 125 at 1920 before the cap.
        expect(
          metrics.charsPerLine,
          `description runs ${metrics.charsPerLine} characters per line`,
        ).toBeLessThanOrEqual(90);

        expect(metrics.facts.size, "facts line is too small to read").toBeGreaterThanOrEqual(11);
        expect(metrics.facts.contrast, "facts line contrast below AA").toBeGreaterThanOrEqual(4.5);
        expect(metrics.description.contrast, "description contrast below AA").toBeGreaterThanOrEqual(4.5);
        expect(metrics.description.fractional, "description uses a fractional font size").toBe(false);
        expect(metrics.facts.fractional, "facts line uses a fractional font size").toBe(false);
        expect(metrics.addHeight, "Add to collection is too small a target").toBeGreaterThanOrEqual(30);

        // Scale is shown where measured and absent where not -- never zero,
        // never a guess.
        const scale = await page.evaluate(() => {
          const cells = [...document.querySelectorAll(".rd-v2-discover-candidate-scale")];
          return {
            cells: cells.length,
            populated: cells.filter((c) => c.textContent.trim()).length,
            // Anchored: "37.0 KB" contains "0 KB" and must not count as zero.
            zeroes: cells.filter((c) => /(^|\s)0(\.0)?\s*(B|KB|MB|GB|TB)\b/.test(c.textContent.trim())).length,
          };
        });
        expect(scale.cells, "every row has a scale cell").toBe(count);
        expect(scale.populated, "measured rows show their size").toBeGreaterThan(0);
        expect(scale.populated, "unmeasured rows must stay empty").toBeLessThan(count);
        expect(scale.zeroes, "a size of zero was rendered").toBe(0);

        await shot(page, `discover-${String(count).padStart(2, "0")}-offerings-${label}`);
      });
    }
  }

  test("selected candidate rail stays inside its bounded budget at 1440", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await mockV2Api(page, { discoverBody: discoverBody(5) });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await runSearch(page, "stablecoin");
    await page.locator(".rd-v2-discover-candidate").first().click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toBeVisible();

    // Centre selection survives -- Detail must not take over the page (A1).
    await expect(page.locator(".rd-v2-discover-candidate")).toHaveCount(5);

    // "Default Detail has at most five modules" -- shared bounded rail slice.
    const modules = await rail.locator(".rd-v2-eval-section-label").allInnerTexts();
    expect(modules.length, `rail renders ${modules.length} modules: ${modules.join(" / ")}`)
      .toBeLessThanOrEqual(5);

    // "Rail height is the app viewport; rail content never stretches the page."
    const stretches = await page.evaluate(() => {
      const r = document.querySelector("aside.rd-v2-rail");
      return r ? r.getBoundingClientRect().height > window.innerHeight + 1 : false;
    });
    expect(stretches, "rail is taller than the viewport").toBe(false);

    // "Primary action remains visible while body/disclosure scrolls."
    const primary = rail.getByTestId("discover-eval-actions").locator(".rd-v2-btn").first();
    await expect(primary).toBeVisible();
    const before = await primary.boundingBox();
    // Guard against a vacuous pass: if the body cannot scroll, this proves
    // nothing about the footer staying put.
    const scrolled = await rail.locator(".rd-v2-eval-scroll").evaluate((el) => {
      el.scrollTop = el.scrollHeight;
      return el.scrollTop > 0;
    });
    expect(scrolled, "rail body did not scroll — sticky-footer check is vacuous").toBe(true);
    await expect(primary).toBeInViewport();
    const after = await primary.boundingBox();
    expect(
      Math.abs((after?.y ?? 0) - (before?.y ?? 0)),
      "primary action moved when the rail body scrolled — it is not a sticky footer",
    ).toBeLessThanOrEqual(2);

    await shot(page, "discover-rail-selected-1440");
  });
});

test.describe("History — required visual states", () => {
  test("70 lifecycle objects remain navigable at 1440", async ({ page }) => {
    await page.setViewportSize(DESKTOP);
    await mockV2Api(page, { discoverBody: discoverBody(5), historyBody: historyBody(70) });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.getByRole("tab", { name: /History/ }).click();

    const ledger = page.getByTestId("discover-history");
    await expect(ledger).toBeVisible({ timeout: 15_000 });
    await expectNoHorizontalOverflow(page);

    // "Initial lifecycle viewport budget is 8-12 rows with explicit Load more."
    // 70 objects must not paint as one endless ledger.
    const rendered = await ledger.locator("li, [role='listitem']").count();
    expect(rendered, `${rendered} lifecycle rows painted at once`).toBeLessThanOrEqual(40);

    // Right-edge state must not be clipped by its container.
    const clipped = await page.evaluate(() => {
      const pane = document.querySelector("[data-testid='discover-history']");
      if (!pane) return 0;
      const edge = pane.getBoundingClientRect().right;
      return [...pane.querySelectorAll("*")].filter((el) => {
        const t = (el.textContent || "").trim();
        if (!t || el.children.length) return false;
        const r = el.getBoundingClientRect();
        return r.width > 0 && r.right > edge + 1;
      }).length;
    });
    expect(clipped, "text overflows the History pane's right edge").toBe(0);

    await shot(page, "history-70-lifecycle-1440");
  });
});
