import { mkdir } from "node:fs/promises";
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

async function openTab(page, label) {
  await page.locator("aside.yzu-sidebar").getByRole("button", { name: label, exact: true }).click();
}

async function waitForHomeEvidence(page) {
  const continuation = page.getByTestId("home-continue");
  await expect(continuation.locator("h2")).toBeVisible();
  await expect(continuation.getByRole("button", { name: "Continue" })).toBeVisible();
  await expect(page.locator(".rd-v2-home-recent .rd-v2-catalog button.row").first()).toBeVisible();
}

test.describe("Research Drive release visual contract", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("desktop renders navigation, research workspace, and persistent Detail Ask rail", async ({ page }) => {
    const shell = page.locator(".rd-v2-shell");
    const header = page.locator("header.rd-v2-header");
    const sidebar = page.locator("aside.yzu-sidebar");
    const main = page.locator("main.yzu-main");
    const rail = page.locator("aside.rd-v2-rail");

    await expect(header.getByText("Research Drive", { exact: true })).toBeVisible();
    await expect(header.getByRole("textbox", { name: "Search Research Drive" })).toBeVisible();
    await expect(sidebar.getByRole("button")).toHaveCount(7);
    await expect(main).toBeVisible();
    await expect(rail.getByRole("tab", { name: "Detail" })).toBeVisible();
    await expect(rail.getByRole("tab", { name: "Ask" })).toBeVisible();

    const geometry = await shell.evaluate((node) => {
      const style = getComputedStyle(node);
      const boxes = {
        sidebar: document.querySelector("aside.yzu-sidebar")?.getBoundingClientRect(),
        main: document.querySelector("main.yzu-main")?.getBoundingClientRect(),
        rail: document.querySelector("aside.rd-v2-rail")?.getBoundingClientRect(),
      };
      return {
        columns: style.gridTemplateColumns,
        sidebar: Math.round(boxes.sidebar?.width || 0),
        main: Math.round(boxes.main?.width || 0),
        rail: Math.round(boxes.rail?.width || 0),
      };
    });

    expect(geometry.columns).toContain("px");
    expect(geometry.sidebar).toBeGreaterThanOrEqual(210);
    expect(geometry.main).toBeGreaterThan(geometry.rail);
    expect(geometry.rail).toBeGreaterThanOrEqual(370);
  });

  test("Home follows resume then entrances then attention then recent evidence", async ({ page }) => {
    const pageRoot = page.locator(".rd-v2-home-page");
    const continuation = page.getByTestId("home-continue");
    const actions = page.locator(".rd-v2-home-actions");
    const attention = page.getByRole("region", { name: "Attention queue" });
    const recent = page.getByRole("region", { name: "Recent research assets" });

    await waitForHomeEvidence(page);
    await expect(actions.getByRole("button", { name: /Search the lab/i })).toBeVisible();
    await expect(actions.getByRole("button", { name: /Discover data/i })).toBeVisible();
    await expect(actions.getByRole("button", { name: /Ask the assistant/i })).toBeVisible();
    await expect(attention).toBeVisible();
    await expect(recent).toBeVisible();

    const order = await pageRoot.evaluate((root) => {
      const selectors = [
        "[data-testid='home-continue']",
        ".rd-v2-home-actions",
        ".rd-v2-home-attention",
        ".rd-v2-home-recent",
      ];
      return selectors.map((selector) => root.querySelector(selector)?.getBoundingClientRect().top || 0);
    });
    expect(order).toEqual([...order].sort((a, b) => a - b));
    await expect(continuation).toBeVisible();
  });

  test("all faculty pages remain implemented in the shared shell", async ({ page }) => {
    const destinations = [
      ["Library", "Library"],
      ["Discover", "Discover"],
      ["Synthesis", "Synthesis"],
      ["Resources", "Resources"],
      ["Profile", "Profile"],
      ["Settings", "Settings"],
    ];

    for (const [tab, title] of destinations) {
      await openTab(page, tab);
      await expect(page.locator(".rd-v2-page-head h1", { hasText: title })).toBeVisible();
      await expect(page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" })).toBeVisible();
    }
  });

  test("Settings keeps faculty status visible and technical endpoints collapsed", async ({ page }) => {
    await openTab(page, "Settings");

    const summary = page.getByRole("region", { name: "Research desk status" });
    await expect(summary).toContainText("Browser access");
    await expect(summary).toContainText("Research assistant");
    await expect(summary).toContainText("Archive");
    await expect(page.getByText("Research services", { exact: true })).toBeVisible();

    const advanced = page.locator("details.rd-v2-settings-advanced");
    await expect(advanced).not.toHaveAttribute("open", "");
    await expect(page.getByText(":8765", { exact: true })).not.toBeVisible();
    await advanced.locator("summary").click();
    await expect(page.getByText(":8765", { exact: true })).toBeVisible();
    await expect(page.getByText(":5178", { exact: true })).toBeVisible();
  });

  test("long research identities wrap instead of breaking the visible Detail pane", async ({ page }) => {
    await page.goto("/?tab=library&folder=research_panels/gdelt", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const firstDataset = page.locator('.rd-v2-library-asset[data-kind="dataset"]').first();
    await expect(firstDataset).toBeVisible();
    await firstDataset.click();

    const rail = page.locator("aside.rd-v2-rail");
    const detailPane = rail.locator('[data-testid="rail-pane-detail"]');
    const railBox = await rail.boundingBox();
    await expect(detailPane).toBeVisible();
    const overflowing = await detailPane.evaluate((node) => node.scrollWidth > node.clientWidth + 2);
    expect(overflowing).toBe(false);
    expect(railBox?.width || 0).toBeGreaterThanOrEqual(370);
  });

  test("capture every implemented release page for pixel review", async ({ page }) => {
    await mkdir("artifacts/release-visual", { recursive: true });
    const pages = [
      ["Home", "home"],
      ["Library", "library"],
      ["Discover", "discover"],
      ["Synthesis", "synthesis"],
      ["Resources", "resources"],
      ["Profile", "profile"],
      ["Settings", "settings"],
    ];

    await waitForHomeEvidence(page);
    for (const [label, file] of pages) {
      if (label !== "Home") await openTab(page, label);
      await page.waitForTimeout(120);
      await page.screenshot({ path: `artifacts/release-visual/${file}-1440x900.png`, fullPage: false });
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await waitForHomeEvidence(page);
    await page.screenshot({ path: "artifacts/release-visual/home-390x844.png", fullPage: false });
  });
});

test.describe("Research Drive mobile composition", () => {
  test("the active page remains primary and the complete resume object precedes the collapsible rail", async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await waitForHomeEvidence(page);

    await expect(page.locator("main.yzu-main")).toBeVisible();
    const continuation = page.getByTestId("home-continue");
    await expect(continuation.locator("h2")).toBeVisible();
    await expect(continuation.getByRole("button", { name: "Continue" })).toBeVisible();
    await expect(continuation.getByRole("button", { name: "Open in Library" })).toBeVisible();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail.getByRole("button", { name: /Show Detail · Ask|Hide panel/ })).toBeVisible();

    const viewportOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    expect(viewportOverflow).toBe(false);
  });
});
