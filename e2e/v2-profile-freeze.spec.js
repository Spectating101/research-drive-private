/**
 * Profile freeze showcase — asserts organic Memory/Works/Lab + DETAIL rail.
 * Run: TMPDIR=$PWD/.tmp-pw npx playwright test e2e/v2-profile-freeze.spec.js --retries=0
 */
import { test, expect } from "@playwright/test";
import path from "path";
import { fileURLToPath } from "url";
import { mockV2Api } from "./fixtures/v2MockApi.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT = path.resolve(__dirname, "../docs/status/generated/profile-freeze-showcase.png");

const PROFILE = {
  found: true,
  profile: {
    name_en: "Kong, De-Rong",
    title: "Assistant Professor",
    discipline: "Finance",
    email: "drkong@saturn.yzu.edu.tw",
    paper_count_parsed: 18,
    specialties: ["empirical asset pricing", "investment", "FinTech", "corporate finance"],
    domain_tags: ["asia_pacific", "corporate_finance", "equities", "fintech", "machine_learning", "nft", "on_chain", "taiwan_market"],
    research_tracks: [
      { id: "token", title: "Token taxonomy — on-chain and off-chain data", phase: "active_grant", weight: 10 },
      { id: "momentum", title: "Taiwan equity momentum with machine learning", weight: 7 },
    ],
    method_tags: ["machine_learning", "panel_data"],
    publication_highlights: [
      "Kong, D.-R. (2021). Alternative investments in the FinTech era.",
      "Bui et al. (2023). Momentum in machine learning: Evidence from the Taiwan stock market.",
    ],
    lab_fintech_stack: [
      { id: "coingecko", label: "CoinGecko prices", route: "vault" },
      { id: "stablecoin", label: "USDT on-chain flows", route: "bigquery" },
    ],
    procurement_recommendations: [
      { dataset: "TWSE daily prices", source_route: "vault", search_query: "TWSE daily prices" },
      { dataset: "MOPS financial statements", source_route: "mops", search_query: "MOPS financial statements" },
    ],
  },
};

test.describe("Profile freeze showcase", () => {
  test("Memory Works Lab and Detail rail match freeze", async ({ page }) => {
    await mockV2Api(page, { profileBody: PROFILE });
    await page.addInitScript(() => {
      try {
        localStorage.removeItem("procure_user_email");
      } catch {
        /* ignore */
      }
    });
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".rd-v2-profile-name")).not.toHaveText("Research profile", { timeout: 20_000 });
    await expect(page.getByRole("heading", { name: "Profile" })).toBeVisible();
    await expect(page.getByText("Research memory carried into Discover and Ask")).toBeVisible();

    const memory = page.getByTestId("profile-memory");
    await expect(memory).toBeVisible();
    await expect(memory.locator(".rd-v2-profile-memory-card").first()).toContainText(/Asset Pricing|FinTech|Finance/i);
    await expect(memory).toContainText(/Current research direction/i);
    await expect(memory).toContainText(/Taiwan equity momentum/i);
    await expect(memory).toContainText(/machine learning/i);

    const works = page.getByTestId("profile-works");
    await expect(works).toBeVisible();
    await expect(works).toContainText(/indexed/i);

    const lab = page.getByTestId("profile-lab");
    await expect(lab).toBeVisible();
    await expect(lab.getByText("Linked to you")).toBeVisible();
    await expect(lab.getByText("Suggested")).toBeVisible();
    await expect(lab.getByText(/Open →|Link →|Search →/).first()).toBeVisible();

    // No legacy split panes / tracks list
    await expect(page.getByTestId("profile-know")).toHaveCount(0);
    await expect(page.getByTestId("profile-offer")).toHaveCount(0);

    const detail = page.getByTestId("profile-detail-rail");
    await expect(detail).toBeVisible();
    await expect(detail.getByText("Scholar")).toBeVisible();
    await expect(detail.getByText("Strengths")).toBeVisible();
    await expect(detail.getByText("Desk")).toBeVisible();
    await expect(detail).toContainText(/faculty/i);

    await page.screenshot({ path: OUT, fullPage: true });
  });

  test("Strengths/Desk claims come from backend domain_tags, never guessed from label text", async ({ page }) => {
    // Regression: buildDeskRead() used to regex-match lab_fintech_stack labels
    // and procurement search_query text (e.g. /crypto|nft|.../) to invent a
    // "FinTech through-line" / topic claim. That's a script-brain substitute
    // for the backend's own curated classification (domain_tags, served by
    // faculty_profile.py profile_summary) — it can say things the registry
    // never declared, or fail to say things the registry did declare.
    const profileWithFintechTextButNoTag = {
      found: true,
      profile: {
        name_en: "Text Bait, No Domain Tag",
        title: "Assistant Professor",
        discipline: "Finance",
        email: "textbait@saturn.yzu.edu.tw",
        paper_count_parsed: 2,
        specialties: ["market microstructure"],
        research_tracks: [{ id: "mst", title: "Microstructure study", phase: "draft", weight: 5 }],
        method_tags: ["event_study"],
        domain_tags: [],
        lab_fintech_stack: [{ id: "crypto-vault", label: "CoinGecko crypto NFT token prices", route: "vault" }],
        procurement_recommendations: [],
      },
    };
    await mockV2Api(page, { profileBody: profileWithFintechTextButNoTag });
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".rd-v2-profile-name")).toHaveText("Text Bait, No Domain Tag", { timeout: 20_000 });

    const detail = page.getByTestId("profile-detail-rail");
    await expect(detail).toBeVisible();
    await expect(detail).not.toContainText("FinTech through-line");
    await expect(detail).not.toContainText("Market + on-chain panels");
    await expect(detail).not.toContainText("FinTech panels linked");
  });

  test("Strengths reflect a declared domain_tags fintech tag with no fintech-sounding label text", async ({ page }) => {
    const profileWithTagButNoText = {
      found: true,
      profile: {
        name_en: "Tag Only, No Text Bait",
        title: "Assistant Professor",
        discipline: "Finance",
        email: "tagonly@saturn.yzu.edu.tw",
        paper_count_parsed: 2,
        specialties: ["market microstructure"],
        research_tracks: [{ id: "mst", title: "Microstructure study", phase: "draft", weight: 5 }],
        method_tags: ["event_study"],
        domain_tags: ["fintech"],
        lab_fintech_stack: [{ id: "vendor-a", label: "Vendor A holdings", route: "vault" }],
        procurement_recommendations: [],
      },
    };
    await mockV2Api(page, { profileBody: profileWithTagButNoText });
    await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
    await expect(page.locator(".rd-v2-profile-name")).toHaveText("Tag Only, No Text Bait", { timeout: 20_000 });

    const detail = page.getByTestId("profile-detail-rail");
    await expect(detail).toBeVisible();
    await expect(detail).toContainText("FinTech through-line");
  });
});
