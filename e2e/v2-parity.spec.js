import { test, expect } from "@playwright/test";

const MOCK_DATASETS = {
  datasets: [
    {
      dataset_id: "gdelt_asia_daily_country_panel",
      name: "Asia daily news-risk panel",
      grain: "country-day",
      analysis_readiness: "instant",
      local_root: "research_panels/gdelt",
      source: "GDELT GKG",
      coverage: "2018–2026",
    },
    {
      dataset_id: "ticker_week_country_broadcast_panel",
      name: "Ticker week panel",
      grain: "country-week",
      analysis_readiness: "instant",
    },
  ],
};

const MOCK_HEALTH = {
  status: "ok",
  datasets: 2,
  desk: {
    jobs: { running: 1, pending_approval: 0 },
    composer_configured: true,
    storage_tiers: { canonical: { quota_tb: 5, used_tb: 2.1 } },
    gdrive: { ok: true },
  },
};

async function mockApi(page) {
  await page.route("**/datasets", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_DATASETS) }),
  );
  await page.route("**/datasets/*", (route) => {
    const id = decodeURIComponent(route.request().url().split("/datasets/")[1] || "");
    const row = MOCK_DATASETS.datasets.find((d) => d.dataset_id === id) || MOCK_DATASETS.datasets[0];
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(row) });
  });
  await page.route("**/health*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_HEALTH) }),
  );
  await page.route("**/library/discover*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sections: [], total: 0 }),
    }),
  );
  await page.route("**/library/search*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sections: [], total: 0 }),
    }),
  );
  await page.route("**/library/ops*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ collection_queue: { pending: 0 }, datacite_harvest: { running: 2 } }),
    }),
  );
  await page.route("**/library/jobs*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ jobs: [] }),
    }),
  );
  await page.route("**/yzu/acquisitions*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ acquisitions: [] }),
    }),
  );
  await page.route("**/library/faculty/profile*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ found: true, profile: { name_en: "Test Prof", discipline: "YZU" } }),
    }),
  );
  await page.route("**/query/*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        rows: [{ date: "2026-04-30", country: "TW", score: 0.82 }],
      }),
    }),
  );
}

async function v2Nav(page, label) {
  await page.locator("aside.yzu-sidebar").getByRole("button", { name: label, exact: true }).click();
}

async function selectFirstDataset(page) {
  await page.goto("/?tab=library&folder=research_panels/gdelt", { waitUntil: "domcontentloaded" });
  await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
  const row = page.locator('.rd-v2-catalog button.row[data-kind="dataset"]').first();
  await row.waitFor({ state: "visible", timeout: 15_000 });
  await row.click();
}

test.describe("v2 parity @ desk-v2-1440", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
  });

  test("shell grid keeps adaptive rail proportions without overflow", async ({ page }) => {
    const shell = page.locator(".rd-v2-shell");
    const metrics = await shell.evaluate((el) => {
      const s = getComputedStyle(el);
      const header = document.querySelector(".yzu-header");
      const sidebar = document.querySelector(".yzu-sidebar");
      const rail = document.querySelector(".rd-v2-rail");
      const main = document.querySelector(".yzu-main");
      return {
        cols: s.gridTemplateColumns,
        shellW: Math.round(el.getBoundingClientRect().width),
        headerH: header ? Math.round(header.getBoundingClientRect().height) : 0,
        sidebarW: sidebar ? Math.round(sidebar.getBoundingClientRect().width) : 0,
        mainW: main ? Math.round(main.getBoundingClientRect().width) : 0,
        railW: rail ? Math.round(rail.getBoundingClientRect().width) : 0,
      };
    });
    expect(metrics.cols).toContain("px");
    expect(metrics.shellW).toBeGreaterThanOrEqual(1438);
    expect(metrics.shellW).toBeLessThanOrEqual(1442);
    expect(metrics.headerH).toBeGreaterThanOrEqual(54);
    expect(metrics.headerH).toBeLessThanOrEqual(58);
    expect(metrics.sidebarW / metrics.shellW).toBeGreaterThanOrEqual(0.16);
    expect(metrics.sidebarW / metrics.shellW).toBeLessThanOrEqual(0.2);
    expect(metrics.railW / metrics.shellW).toBeGreaterThanOrEqual(0.28);
    expect(metrics.railW / metrics.shellW).toBeLessThanOrEqual(0.32);
    expect(metrics.mainW).toBeGreaterThan(metrics.railW);
    expect(metrics.mainW).toBeGreaterThan(metrics.sidebarW);
    expect(metrics.sidebarW + metrics.mainW + metrics.railW).toBeLessThanOrEqual(metrics.shellW + 2);
  });

  test("sidebar tabs render page chrome", async ({ page }) => {
    const tabs = [
      ["Home", "Home"],
      ["Library", "Library"],
      ["Discover", "Discover"],
      ["Resources", "Resources"],
      ["Profile", "Test Prof"],
      ["Settings", "Desk setup"],
    ];
    for (const [nav, heading] of tabs) {
      await v2Nav(page, nav);
      if (nav === "Profile") {
        await expect(page.locator(".rd-v2-profile-name", { hasText: heading })).toBeVisible();
      } else {
        await expect(page.locator(".rd-v2-page-head h1", { hasText: heading })).toBeVisible();
      }
    }
    await expect(page.locator("aside.yzu-sidebar nav button", { hasText: "Cluster" })).toHaveCount(0);
  });

  test("cluster tab still reachable via URL while deferred", async ({ page }) => {
    await page.goto("/?tab=cluster", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Cluster" })).toBeVisible();
  });

  test("Detail rail has sticky CTAs and segmented toggle", async ({ page }) => {
    await selectFirstDataset(page);
    await expect(page.locator(".rd-v2-rail-toggle button.on", { hasText: "Detail" })).toBeVisible();
    await expect(page.locator('[data-testid="rail-pane-ask"]')).toBeHidden();
    await expect(
      page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary", { hasText: "Preview rows" }),
    ).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: /^Source$/ })).toBeVisible();
    await page.locator(".rd-v2-rail-toggle").getByRole("tab", { name: "Ask" }).click();
    await expect(page.getByTestId("ask-composer")).toBeVisible();
    await expect(page.locator('[data-testid="rail-pane-detail"] .rd-v2-rail-sticky')).not.toBeVisible();
  });

  test("preview modal overlays main only with footer actions", async ({ page }) => {
    await selectFirstDataset(page);
    await page.locator("aside .rd-v2-rail-sticky").getByRole("button", { name: "Preview rows" }).click();
    const modal = page.locator(".rd-v2-preview-modal");
    await expect(modal).toBeVisible();
    await expect(modal.getByRole("button", { name: "Export CSV" })).toBeVisible();
    await expect(modal.getByRole("button", { name: "Open query engine" })).toBeVisible();
    await expect(page.locator(".rd-v2-rail-toggle")).toBeVisible();
    await page.keyboard.press("Escape");
    await expect(modal).toHaveCount(0);
  });

  test("institutional visual hierarchy gives research objects editorial authority", async ({ page }) => {
    const visual = await page.evaluate(() => {
      const root = getComputedStyle(document.documentElement);
      const title = getComputedStyle(document.querySelector(".rd-v2-page-head h1"));
      const lead = getComputedStyle(document.querySelector(".rd-v2-lead"));
      return {
        canvas: root.getPropertyValue("--rd-canvas").trim().toLowerCase(),
        ink: root.getPropertyValue("--rd-text").trim().toLowerCase(),
        evidence: root.getPropertyValue("--rd-evidence").trim().toLowerCase(),
        titleFont: title.fontFamily,
        titleSize: Number.parseFloat(title.fontSize),
        leadSize: Number.parseFloat(lead.fontSize),
      };
    });

    expect(visual.canvas).toBe("#f7f6f2");
    expect(visual.ink).toBe("#172033");
    expect(visual.evidence).toBe("#102a43");
    expect(visual.titleFont).toContain("Source Serif 4");
    expect(visual.titleSize).toBeGreaterThanOrEqual(28);
    expect(visual.leadSize).toBeGreaterThanOrEqual(14);
  });
});
