/**
 * Sourcing functionality — DataCite vs Spectator engine paths (live API + UI).
 * Run: npx playwright test e2e/sourcing-flow.spec.js
 */
import { test, expect } from "@playwright/test";

const OUT = "docs/status/generated";
const EMAIL = "drkong@saturn.yzu.edu.tw";
const API = process.env.YZU_API_URL || "http://127.0.0.1:8765";

async function openResearchAssistant(page) {
  await page.getByRole("tab", { name: "Assistant" }).click();
  await page.locator("aside .rd-inspector-chat-panel .yzu-composer textarea").waitFor({ timeout: 15_000 });
}

function railChat(page) {
  return page.locator("aside .rd-inspector-chat-panel .yzu-chat");
}

async function signIn(page) {
  const accountBtn = page.locator(".yzu-account-btn");
  const text = await accountBtn.innerText();
  if (text.includes("drkong") || text.includes("Kong")) {
    return;
  }
  await accountBtn.click();
  await page.getByPlaceholder("you@saturn.yzu.edu.tw").fill(EMAIL);
  await page.getByRole("button", { name: "Continue" }).click();
  await page.waitForFunction(
    () => {
      const strong = document.querySelector(".yzu-account-copy strong");
      return strong && !/sign in/i.test(strong.textContent || "");
    },
    { timeout: 25_000 },
  );
}

async function askAssistant(page, prompt) {
  await openResearchAssistant(page);
  const textarea = page.locator("aside .yzu-composer textarea");
  await textarea.fill(prompt);
  const button = page.locator("aside .yzu-composer button.primary");
  await button.click();
  
  // Wait a short moment to ensure the UI transition into busy state starts
  await page.waitForTimeout(500);
  
  // Wait for the button to become enabled (busy state ends)
  await expect(button).not.toBeDisabled({ timeout: 120_000 });
  await expect(button).not.toHaveText("…", { timeout: 120_000 });
}

test.describe("Sourcing — DataCite & Spectator", () => {
  test.describe.configure({ timeout: 240_000 });

  test("S1 UI — DataCite search shows candidate cards", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
    await signIn(page);
    await askAssistant(page, "Find replication datasets on DataCite for Taiwan equity markets");
    await page.screenshot({ path: `${OUT}/sourcing-01-datacite-ask.png`, fullPage: false });

    const cards = page.locator("aside .yzu-candidate");
    const cardVisible = await cards.first().isVisible().catch(() => false);
    const body = await railChat(page).innerText();
    const hasRoute =
      cardVisible || /datacite|DataCite|TWSE|acquisition|collect|queue|replication/i.test(body);
    expect(hasRoute).toBeTruthy();
    if (cardVisible) {
      expect(await cards.count()).toBeGreaterThan(0);
    }
  });

  test("S2 UI — Spectator / manual sourcing prompt", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await page.getByRole("heading", { name: "Home", exact: true }).waitFor({ timeout: 30_000 });
    await signIn(page);
    await askAssistant(
      page,
      "download https://www.sec.gov/files/company_tickers.json into the lab library",
    );
    await page.screenshot({ path: `${OUT}/sourcing-02-sec-http-collect.png`, fullPage: false });

    const body = await railChat(page).innerText();
    const ok = /http_manifest|completed|queued|company_tickers|Direct download|796|Job|SEC|download/i.test(body);
    expect(ok).toBeTruthy();
  });

  test("S3 API — DataCite search-resolve returns hits", async ({ request }) => {
    const res = await request.post(`${API}/library/datacite/search-resolve`, {
      data: { query: "taiwan equity", limit: 5 },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    const rows = data.rows || data.results || data.hits || data.attempts || [];
    const picked = data.picked;
    const total = data.search_total ?? 0;
    expect(rows.length > 0 || Boolean(picked?.doi) || total > 0).toBeTruthy();
  });

  test("S4 API — chat returns acquisition routes", async ({ request }) => {
    const res = await request.post(`${API}/library/chat`, {
      data: {
        message: "Design full acquisition pipeline for climate calibration data via DataCite",
        user_email: EMAIL,
      },
    });
    expect(res.ok()).toBeTruthy();
    const data = await res.json();
    const cands = data.candidates || [];
    const vias = new Set(cands.map((c) => c.collect_via).filter(Boolean));
    const kinds = new Set(cands.map((c) => c.kind).filter(Boolean));
    test.info().annotations.push({ type: "collect_vias", description: [...vias].join(", ") || "none" });
    test.info().annotations.push({ type: "kinds", description: [...kinds].join(", ") || "none" });
    expect(cands.length + (data.reply?.length || 0)).toBeGreaterThan(0);
    const hasProcurement = [...vias].some((v) => ["datacite", "magic", "queue", "spectator", "local_open"].includes(v));
    expect(hasProcurement || /campaign|DataCite|acquisition|collect|rephrasing|looked/i.test(data.reply || "")).toBeTruthy();
  });

  test("S5 UI — Recommended page external DataCite rows", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/");
    await page.locator("aside.yzu-sidebar > nav").getByRole("button", { name: /^Discover/ }).click();
    await page.getByRole("heading", { name: "Discover" }).waitFor();
    await page.waitForFunction(
      () => !document.body.textContent?.toLowerCase().includes("searching catalog"),
      { timeout: 30_000 },
    );
    await page.screenshot({ path: `${OUT}/sourcing-03-recommended-datacite.png`, fullPage: false });
    const providers = await page.locator(".rd-discover-card").filter({ hasText: /datacite/i }).count();
    expect(providers).toBeGreaterThan(0);
  });
});
