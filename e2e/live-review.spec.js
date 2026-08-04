import { test, expect } from "@playwright/test";

const REVIEW_QUERY = process.env.LIVE_REVIEW_QUERY || "stablecoin";
const KNOWN_FOLDER = process.env.LIVE_REVIEW_FOLDER || "news_events/news.gdelt-asia";
const KNOWN_DATASET = process.env.LIVE_REVIEW_DATASET || "gdelt_asia_daily_country_panel";

const SAFE_BOOTSTRAP_POSTS = new Set([
  "/library/desk/session",
  "/library/desk/warm",
]);
const SAFE_TELEMETRY_POSTS = new Set(["/cdn-cgi/rum"]);

function pathnameOf(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return url;
  }
}

async function installReadOnlyGuard(page, audit) {
  page.on("pageerror", (error) => audit.pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") audit.consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() < 400) return;
    const path = pathnameOf(response.url());
    if (SAFE_BOOTSTRAP_POSTS.has(path) || SAFE_TELEMETRY_POSTS.has(path)) return;
    audit.unexpectedHttp.push({ status: response.status(), path });
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const method = request.method().toUpperCase();
    const path = pathnameOf(request.url());

    if (["GET", "HEAD", "OPTIONS"].includes(method)) {
      await route.continue();
      return;
    }
    if (method === "POST" && SAFE_BOOTSTRAP_POSTS.has(path)) {
      audit.allowedBootstrap.push({ method, path });
      await route.continue();
      return;
    }
    if (method === "POST" && SAFE_TELEMETRY_POSTS.has(path)) {
      audit.suppressedTelemetry.push({ method, path });
      await route.abort("blockedbyclient");
      return;
    }

    audit.blockedMutations.push({ method, path });
    await route.abort("blockedbyclient");
  });
}

async function assertLayoutFits(page) {
  const dimensions = await expect.poll(() => page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body?.scrollWidth || 0,
  }))).toMatchObject({
    viewport: expect.any(Number),
    document: expect.any(Number),
    body: expect.any(Number),
  });
  void dimensions;
  const finalDimensions = await page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body?.scrollWidth || 0,
  }));
  expect(finalDimensions.document).toBeLessThanOrEqual(finalDimensions.viewport + 1);
  expect(finalDimensions.body).toBeLessThanOrEqual(finalDimensions.viewport + 1);
}

async function waitForDesk(page) {
  await page.locator(".rd-v2-shell").waitFor({ timeout: 45_000 });
  await expect(page.locator(".rd-v2-trust-badge.ok", { hasText: "Live registry" })).toBeVisible({
    timeout: 45_000,
  });
}

async function capture(page, testInfo, name) {
  const shot = await page.screenshot({ fullPage: true });
  await testInfo.attach(name, { body: shot, contentType: "image/png" });
}

async function finishAudit(testInfo, audit) {
  await testInfo.attach("read-only-audit.json", {
    body: Buffer.from(JSON.stringify(audit, null, 2)),
    contentType: "application/json",
  });
  expect(audit.blockedMutations, "The review attempted a runtime mutation").toEqual([]);
  expect(audit.pageErrors, "The page raised JavaScript errors").toEqual([]);
  expect(audit.unexpectedHttp, "The review received unexpected HTTP failures").toEqual([]);
}

function newAudit() {
  return {
    allowedBootstrap: [],
    suppressedTelemetry: [],
    blockedMutations: [],
    pageErrors: [],
    consoleErrors: [],
    unexpectedHttp: [],
  };
}

test.describe("Research Drive live review — read only", () => {
  test("Home hierarchy and continuation surface", async ({ page }, testInfo) => {
    const audit = newAudit();
    await installReadOnlyGuard(page, audit);
    await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
    await waitForDesk(page);

    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "Pick up" })).toBeVisible();
    await expect(page.getByRole("region", { name: "Resource headroom" })).toBeVisible();
    await expect(page.locator("main.yzu-main")).toContainText(/Recommended evidence|Recent trail/);
    await assertLayoutFits(page);
    await capture(page, testInfo, "home-1440x900");
    await finishAudit(testInfo, audit);
  });

  test("Discover ranking, Detail, and resting Ask shell", async ({ page }, testInfo) => {
    const audit = newAudit();
    await installReadOnlyGuard(page, audit);
    await page.goto(`/?tab=browse&q=${encodeURIComponent(REVIEW_QUERY)}`, {
      waitUntil: "domcontentloaded",
    });
    await waitForDesk(page);

    await expect(page.getByRole("heading", { name: "Discover", exact: true })).toBeVisible();
    const bestFit = page.getByRole("region", { name: "Best fit" });
    await expect(bestFit).toBeVisible({ timeout: 45_000 });
    const firstCandidate = bestFit.getByRole("button").first();
    await expect(firstCandidate).toBeVisible();
    await firstCandidate.click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("region", { name: "Can I use this" })).toBeVisible();
    await expect(rail.getByRole("region", { name: "Lab coverage" })).toBeVisible();
    await expect(page.locator(".rd-v2-discover-candidate.selected")).toBeVisible();
    await rail.getByRole("tab", { name: "Ask" }).click();
    await expect(rail.getByTestId("ask-messages")).toBeVisible();
    await assertLayoutFits(page);
    await capture(page, testInfo, "discover-selected-source-1440x900");
    await finishAudit(testInfo, audit);
  });

  test("Library shelf and selected asset agree", async ({ page }, testInfo) => {
    const audit = newAudit();
    await installReadOnlyGuard(page, audit);
    await page.goto(
      `/?tab=library&folder=${encodeURIComponent(KNOWN_FOLDER)}&dataset=${encodeURIComponent(KNOWN_DATASET)}`,
      { waitUntil: "domcontentloaded" },
    );
    await waitForDesk(page);

    await expect(page.getByRole("heading", { name: "Library", exact: true })).toBeVisible();
    await expect(page.getByTestId("library-toolbar-search")).toBeVisible();
    await expect(page.getByRole("navigation", { name: "Breadcrumb" })).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Detail" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.locator('[data-testid="rail-pane-detail"]')).toContainText(/Ready|Query-ready|Unknown/i);
    await expect(page.locator("main.yzu-main")).not.toContainText("0 datasets");
    await assertLayoutFits(page);
    await capture(page, testInfo, "library-selected-asset-1440x900");
    await finishAudit(testInfo, audit);
  });

  for (const route of ["synthesis", "resources", "profile", "settings"]) {
    test(`${route} route renders without mutation or overflow`, async ({ page }, testInfo) => {
      const audit = newAudit();
      await installReadOnlyGuard(page, audit);
      await page.goto(`/?tab=${route}`, { waitUntil: "domcontentloaded" });
      await waitForDesk(page);

      const label = route[0].toUpperCase() + route.slice(1);
      await expect(page.getByRole("heading", { name: label, exact: true })).toBeVisible();
      await assertLayoutFits(page);
      await capture(page, testInfo, `${route}-1440x900`);
      await finishAudit(testInfo, audit);
    });
  }

  test("mobile Discover remains bounded", async ({ page }, testInfo) => {
    const audit = newAudit();
    await page.setViewportSize({ width: 390, height: 844 });
    await installReadOnlyGuard(page, audit);
    await page.goto(`/?tab=browse&q=${encodeURIComponent(REVIEW_QUERY)}`, {
      waitUntil: "domcontentloaded",
    });
    await waitForDesk(page);

    await expect(page.getByRole("heading", { name: "Discover", exact: true })).toBeVisible();
    await assertLayoutFits(page);
    await capture(page, testInfo, "discover-mobile-390x844");
    await finishAudit(testInfo, audit);
  });
});
