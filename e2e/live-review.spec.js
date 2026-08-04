import { test, expect } from "@playwright/test";

const REVIEW_TARGET = process.env.YZU_DESK_URL || "https://previous.easycamp.tech";
const REVIEW_ORIGIN = new URL(REVIEW_TARGET).origin;
const REVIEW_QUERY = process.env.LIVE_REVIEW_QUERY || "stablecoin";
const KNOWN_FOLDER = process.env.LIVE_REVIEW_FOLDER || "news_events/news.gdelt-asia";
const KNOWN_DATASET = process.env.LIVE_REVIEW_DATASET || "gdelt_asia_daily_country_panel";

const SAFE_BOOTSTRAP_POSTS = new Set([
  "/library/desk/session",
  "/library/desk/warm",
]);
const SAFE_TELEMETRY_POSTS = new Set(["/cdn-cgi/rum"]);

function parsedUrl(url) {
  try {
    return new URL(url);
  } catch {
    return null;
  }
}

function pathnameOf(url) {
  return parsedUrl(url)?.pathname || url;
}

function isReviewOrigin(url) {
  return parsedUrl(url)?.origin === REVIEW_ORIGIN;
}

async function installReadOnlyGuard(page, audit) {
  page.on("pageerror", (error) => audit.pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") audit.consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    const url = response.url();
    const path = pathnameOf(url);
    if (
      isReviewOrigin(url)
      && path.startsWith("/assets/")
      && /\.(?:js|css)(?:$|\?)/.test(url)
      && !audit.remoteAssets.includes(path)
    ) {
      audit.remoteAssets.push(path);
    }
    if (response.status() < 400) return;
    if (
      isReviewOrigin(url)
      && (SAFE_BOOTSTRAP_POSTS.has(path) || SAFE_TELEMETRY_POSTS.has(path))
    ) {
      return;
    }
    audit.unexpectedHttp.push({ status: response.status(), url });
  });

  await page.route("**/*", async (route) => {
    const request = route.request();
    const method = request.method().toUpperCase();
    const url = request.url();
    const path = pathnameOf(url);
    const sameOrigin = isReviewOrigin(url);

    if (["GET", "HEAD", "OPTIONS"].includes(method)) {
      await route.continue();
      return;
    }
    if (sameOrigin && method === "POST" && SAFE_BOOTSTRAP_POSTS.has(path)) {
      audit.allowedBootstrap.push({ method, path, origin: REVIEW_ORIGIN });
      await route.continue();
      return;
    }
    if (sameOrigin && method === "POST" && SAFE_TELEMETRY_POSTS.has(path)) {
      audit.suppressedTelemetry.push({ method, path, origin: REVIEW_ORIGIN });
      await route.fulfill({ status: 204, body: "" });
      return;
    }

    audit.blockedMutations.push({ method, url });
    await route.abort("blockedbyclient");
  });
}

async function assertLayoutFits(page) {
  await expect.poll(() => page.evaluate(() => ({
    viewport: document.documentElement.clientWidth,
    document: document.documentElement.scrollWidth,
    body: document.body?.scrollWidth || 0,
  }))).toMatchObject({
    viewport: expect.any(Number),
    document: expect.any(Number),
    body: expect.any(Number),
  });
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

async function finishAudit(page, testInfo, audit) {
  const documentAssets = await page.locator("script[src],link[rel='stylesheet'][href]").evaluateAll(
    (nodes) => nodes
      .map((node) => node.src || node.href)
      .filter(Boolean),
  );
  for (const url of documentAssets) {
    const parsed = parsedUrl(url);
    if (
      parsed?.origin === REVIEW_ORIGIN
      && parsed.pathname.startsWith("/assets/")
      && !audit.remoteAssets.includes(parsed.pathname)
    ) {
      audit.remoteAssets.push(parsed.pathname);
    }
  }
  audit.remoteAssets.sort();
  audit.reviewedUrl = page.url();
  audit.reviewOrigin = REVIEW_ORIGIN;

  await testInfo.attach("read-only-audit.json", {
    body: Buffer.from(JSON.stringify(audit, null, 2)),
    contentType: "application/json",
  });

  expect(audit.blockedMutations, "The review attempted a runtime mutation").toEqual([]);
  expect(audit.pageErrors, "The page raised JavaScript errors").toEqual([]);
  expect(audit.consoleErrors, "The page logged browser console errors").toEqual([]);
  expect(audit.unexpectedHttp, "The review received unexpected HTTP failures").toEqual([]);
  expect(
    audit.remoteAssets.some((asset) => /^\/assets\/.*\.js$/.test(asset)),
    "The audit did not capture the deployed JavaScript asset identity",
  ).toBe(true);
}

function newAudit() {
  return {
    allowedBootstrap: [],
    suppressedTelemetry: [],
    blockedMutations: [],
    pageErrors: [],
    consoleErrors: [],
    unexpectedHttp: [],
    remoteAssets: [],
    reviewedUrl: null,
    reviewOrigin: REVIEW_ORIGIN,
  };
}

test.describe("Research Drive deployed live review — read only", () => {
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
    await finishAudit(page, testInfo, audit);
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
    await finishAudit(page, testInfo, audit);
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

    const selectedShelfRow = page.locator(".rd-v2-catalog-list li.rd-v2-row-on");
    await expect(selectedShelfRow).toHaveCount(1);
    await expect(selectedShelfRow.locator("button[data-kind='dataset']")).toBeVisible();
    const selectedShelfText = (await selectedShelfRow.innerText()).trim();
    expect(selectedShelfText, "The selected Library row has no visible identity").not.toBe("");

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("tab", { name: "Detail" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(page.locator('[data-testid="rail-pane-detail"]')).toContainText(
      /Ready|Query-ready|Unknown/i,
    );
    await expect(page.locator("main.yzu-main")).not.toContainText("0 datasets");

    audit.librarySelection = {
      requestedDatasetId: KNOWN_DATASET,
      requestedFolderId: KNOWN_FOLDER,
      visibleSelectedRowText: selectedShelfText,
    };
    await assertLayoutFits(page);
    await capture(page, testInfo, "library-selected-asset-1440x900");
    await finishAudit(page, testInfo, audit);
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
      await finishAudit(page, testInfo, audit);
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
    await finishAudit(page, testInfo, audit);
  });
});
