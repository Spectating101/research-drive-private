import fs from "node:fs";
import { test, expect } from "@playwright/test";
import { MOCK_DISCOVER_HIT, mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const ARTIFACT_DIR = "artifacts/release-visual";

function ensureArtifactDir() {
  fs.mkdirSync(ARTIFACT_DIR, { recursive: true });
}

function durationSeconds(value) {
  const raw = String(value || "").trim();
  if (!raw) return 0;
  if (raw.endsWith("ms")) return Number.parseFloat(raw) / 1000;
  return Number.parseFloat(raw);
}

test.describe("Research Drive RC2.1 transient decoration layer", () => {
  test("Ask uses compact, honest indeterminate activity feedback", async ({ page }) => {
    await mockV2Api(page);
    await page.unroute("**/api/library/chat/stream");
    await page.unroute("**/api/library/chat");
    const delayedChat = async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 2400));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "decoration-test",
          reply: "The selected asset is grounded in the current Research Drive context.",
          action: "answer",
        }),
      });
    };
    await page.route("**/api/library/chat/stream", delayedChat);
    await page.route("**/api/library/chat", delayedChat);

    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const rail = page.locator("aside.rd-v2-rail");
    await rail.getByRole("tab", { name: "Ask" }).click();
    await rail.getByTestId("ask-composer").fill("Explain what this asset can safely support.");
    await rail.getByRole("button", { name: "Send" }).click();

    const progress = rail.getByTestId("interaction-progress");
    const activityBar = progress.getByRole("progressbar");
    const announcement = progress.locator(".rd-v2-progress-announcement");
    const elapsedMeta = progress.locator(".rd-v2-progress-card-meta");
    await expect(progress).toBeVisible();
    await expect(progress.locator("li")).toHaveCount(4);
    await expect(progress).toContainText(/Active · \d+s/);
    await expect(announcement).toHaveAttribute("role", "status");
    await expect(announcement).toHaveAttribute("aria-live", "polite");
    await expect(announcement).toHaveText(/Preparing|Searching|Checking|Composing|Planning/);
    await expect(elapsedMeta).toHaveAttribute("aria-hidden", "true");
    await expect(activityBar).not.toHaveAttribute("aria-valuenow", /.+/);
    await expect(activityBar).not.toHaveAttribute("aria-valuemax", /.+/);
    await expect(activityBar).toHaveAttribute("aria-valuetext", /Preparing|Searching|Checking|Composing|Planning/);

    const activityVisual = await progress.evaluate((node) => ({
      height: node.getBoundingClientRect().height,
      overflows: node.scrollWidth > node.clientWidth + 1,
    }));
    expect(activityVisual.height).toBeLessThan(230);
    expect(activityVisual.overflows).toBe(false);

    const barAnimation = await progress.locator(".rd-v2-progress-phase-fill").evaluate((node) => {
      const computed = getComputedStyle(node);
      return { name: computed.animationName, count: computed.animationIterationCount };
    });
    expect(barAnimation.name).toContain("rd-decor-progress-indeterminate");
    expect(barAnimation.count).toBe("infinite");

    await page.waitForTimeout(1150);
    const activeStep = Number(await progress.getAttribute("data-active-step"));
    expect(activeStep).toBeGreaterThanOrEqual(2);
    await expect(progress.locator('li[data-state="past"]')).not.toHaveCount(0);
    await expect(progress.locator('li[data-state="past"] .rd-v2-progress-marker svg')).toHaveCount(0);

    ensureArtifactDir();
    await page.screenshot({ path: `${ARTIFACT_DIR}/decoration-ask-activity-1440x900.png`, fullPage: true });

    await expect(progress).toHaveCount(0, { timeout: 10_000 });
    await expect(rail).toContainText("grounded in the current Research Drive context");
    await expect(rail.getByRole("progressbar")).toHaveCount(0);
  });

  test("productive motion is unified, spatially stable, keyboard-visible, and removable", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);

    const motionTokens = await page.evaluate(() => {
      const computed = getComputedStyle(document.documentElement);
      return {
        press: computed.getPropertyValue("--rd-decor-duration-press").trim(),
        fade: computed.getPropertyValue("--rd-decor-duration-fade").trim(),
        small: computed.getPropertyValue("--rd-decor-duration-small").trim(),
        system: computed.getPropertyValue("--rd-decor-duration-system").trim(),
      };
    });
    expect(motionTokens).toEqual({ press: "70ms", fade: "110ms", small: "150ms", system: "240ms" });

    const pageMotion = await page.locator(".rd-v2-page").first().evaluate((node) => {
      const computed = getComputedStyle(node);
      return { name: computed.animationName, duration: computed.animationDuration, transform: computed.transform };
    });
    expect(pageMotion.name).toBe("rd-page-enter");
    expect(pageMotion.duration).toBe("0.11s");
    expect(pageMotion.transform).toBe("none");

    const search = page.locator(".rd-v2-search-pill input");
    await search.fill("mops");
    const candidate = page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" });
    await expect(candidate).toBeVisible();

    const baseline = await candidate.evaluate((node) => {
      const computed = getComputedStyle(node);
      return { boxShadow: computed.boxShadow, transform: computed.transform };
    });
    await candidate.hover();
    await page.waitForTimeout(180);
    const hovered = await candidate.evaluate((node) => {
      const computed = getComputedStyle(node);
      return { boxShadow: computed.boxShadow, transform: computed.transform };
    });
    expect(hovered.boxShadow).not.toBe(baseline.boxShadow);
    expect(hovered.transform).toBe("none");

    await search.hover();
    await page.waitForTimeout(220);
    const resting = await candidate.evaluate((node) => {
      const computed = getComputedStyle(node);
      return { boxShadow: computed.boxShadow, transform: computed.transform };
    });
    expect(resting.boxShadow).toBe(baseline.boxShadow);
    expect(resting.transform).toBe("none");

    await page.keyboard.press("Tab");
    await candidate.focus();
    const focusStyle = await candidate.evaluate((node) => {
      const computed = getComputedStyle(node);
      return { style: computed.outlineStyle, width: computed.outlineWidth };
    });
    expect(focusStyle.style).not.toBe("none");
    expect(focusStyle.width).not.toBe("0px");

    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForShell(page);
    const reducedSearch = page.locator(".rd-v2-search-pill input");
    await reducedSearch.fill("mops");
    const reducedCandidate = page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" });
    await reducedCandidate.hover();

    const reducedStyles = await reducedCandidate.evaluate((node) => {
      const computed = getComputedStyle(node);
      return { transform: computed.transform, transitionDuration: computed.transitionDuration };
    });
    expect(reducedStyles.transform).toBe("none");
    const reducedDurations = reducedStyles.transitionDuration.split(",").map(durationSeconds);
    expect(Math.max(...reducedDurations)).toBeLessThanOrEqual(0.00001);

    const reducedPageAnimation = await page.locator(".rd-v2-page").first().evaluate(
      (node) => getComputedStyle(node).animationName,
    );
    expect(reducedPageAnimation).toBe("none");

    await page.setViewportSize({ width: 390, height: 844 });
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 2);
    expect(overflow).toBe(false);

    ensureArtifactDir();
    await page.screenshot({ path: `${ARTIFACT_DIR}/decoration-reduced-motion-mobile-390x844.png`, fullPage: false });
  });
});
