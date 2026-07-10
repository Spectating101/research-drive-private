import { test, expect } from "@playwright/test";
import {
  MOCK_DISCOVER_HIT,
  mockV2Api,
  v2Nav,
  waitForShell,
} from "./fixtures/v2MockApi.js";

test.describe("v2 Discover tab", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("empty state shows suggestions before search", async ({ page }) => {
    await expect(page.getByTestId("discover-empty")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Discover external datasets" })).toBeVisible();
    await expect(page.getByRole("button", { name: "TWSE governance" })).toBeVisible();
  });

  test("suggestion chip fills header search and shows demo results", async ({ page }) => {
    await page.getByRole("button", { name: "TWSE governance" }).click();
    await expect(page.locator(".rd-v2-search-pill input")).toHaveValue("TWSE governance");
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external"]')).toHaveCount(1, { timeout: 10_000 });
    await expect(page.locator(".rd-v2-discover-list-panel")).toContainText("TWSE OpenAPI");
    await expect(page.locator(".rd-v2-discover-pipeline")).toContainText("Search");
    await expect(page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "Ready to check" })).toBeVisible();
  });

  test("selecting discover row opens acquisition rail with Add to lab", async ({ page }) => {
    await page.locator(".rd-v2-search-pill input").fill("MOPS");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary", { hasText: "Add to lab" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Source" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Access" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Probe" })).toBeVisible();
    await expect(page.locator(".rd-v2-detail-label", { hasText: "Destination" })).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Acquisition state");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Registry");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("Probe");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS");
  });

  test("Discover candidate Ask actions carry candidate context", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Ask about this →" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-v2-ask-ctx")).toContainText("mops_financial_statements_ext");
    await expect(page.getByTestId("ask-messages")).toContainText("Assess this Discover candidate for procurement");
    await expect(page.getByTestId("ask-messages")).toContainText("MOPS financial statements");
  });

  test("Probe source shows connector summary in rail", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(rail.locator(".rd-v2-discover-probe-result")).toContainText("direct_file");
    await expect(rail.locator(".rd-v2-detail-label", { hasText: "Connector" })).toBeVisible();
  });

  test("Add to lab after probe queues structured Ask", async ({ page }) => {
    const chatBodies = [];
    page.on("request", (req) => {
      if (req.url().includes("/library/chat") && req.method() === "POST") {
        chatBodies.push(req.postData() || "");
      }
    });
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(rail.locator(".rd-v2-discover-probe-result")).toBeVisible();
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    const ask = page.getByTestId("ask-messages");
    await expect(ask).toContainText("Add to lab vault");
    await expect(ask).toContainText("Collection job queued");
    await expect(ask).toContainText("Track it in Resources");
    await expect(ask).not.toContainText("job-discover-collect-1");
    await expect(ask).not.toContainText("Candidate (structured)");
    await expect(ask).not.toContainText("example_com_data");
    const toast = page.locator(".rd-v2-toast");
    await expect(toast).toBeVisible();
    await expect(toast).toContainText("Collection job queued — track it in Resources");
    await expect(toast).not.toContainText("job-discover-collect-1");
    const joined = chatBodies.join("\n");
    expect(joined).toMatch(/Candidate \(structured\)|connector|MOPS financial statements/i);
    expect(joined).toMatch(/job-discover-collect-1|Collection job queued/i);
    expect(joined).toMatch(/candidate_key/);
  });

  test("probe evidence stays bound to the selected candidate", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Registry",
            rows: [
              {
                dataset_id: "mops_financial_statements_ext",
                title: "MOPS financial statements (Taiwan)",
                source: "MOPS",
                url: "https://mops.twse.com.tw/example",
              },
              {
                dataset_id: "twse_openapi_governance_ext",
                title: "TWSE OpenAPI governance disclosures",
                source: "TWSE",
                url: "https://openapi.twse.com.tw/example",
              },
            ],
          },
        ],
        total: 2,
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("governance");
    const mops = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
      hasText: "MOPS financial statements",
    });
    const twse = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
      hasText: "TWSE OpenAPI governance",
    });
    await mops.click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(rail.locator(".rd-v2-discover-probe-result")).toContainText("direct_file");
    await twse.click();
    await expect(rail).toContainText("TWSE OpenAPI");
    await expect(rail.locator(".rd-v2-discover-probe-result")).toHaveCount(0);
  });

  test("similar titles do not inherit queued state without candidate_key", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Registry",
            rows: [
              {
                title: "MOPS financial statements",
                source: "MOPS",
                url: "https://mops.twse.com.tw/a",
              },
              {
                title: "MOPS financial statements extended",
                source: "MOPS",
                url: "https://mops.twse.com.tw/b",
              },
            ],
          },
        ],
        total: 2,
      },
      // Job title overlaps both candidates — must NOT mark either queued without key
      jobsBody: {
        jobs: [
          {
            id: "job-title-only",
            status: "pending_approval",
            type: "procure",
            plan: { title: "MOPS financial statements" },
            request: {},
          },
        ],
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("MOPS");
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external"]')).toHaveCount(2);
    await expect(page.locator(".rd-v2-pill", { hasText: "Queued" })).toHaveCount(0);
  });

  test("exact candidate_key marks only the linked candidate queued", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Registry",
            rows: [
              {
                candidate_key: "url:https://mops.twse.com.tw/a",
                title: "MOPS financial statements",
                source: "MOPS",
                url: "https://mops.twse.com.tw/a",
              },
              {
                candidate_key: "url:https://mops.twse.com.tw/b",
                title: "MOPS financial statements extended",
                source: "MOPS",
                url: "https://mops.twse.com.tw/b",
              },
            ],
          },
        ],
        total: 2,
      },
      jobsBody: {
        jobs: [
          {
            id: "job-exact-a",
            status: "pending_approval",
            candidate_key: "url:https://mops.twse.com.tw/a",
            request: { candidate_key: "url:https://mops.twse.com.tw/a" },
            plan: { title: "MOPS financial statements" },
          },
        ],
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("MOPS");
    const rowA = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
      hasText: "MOPS financial statements",
    }).first();
    const rowB = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
      hasText: "MOPS financial statements extended",
    });
    await expect(rowA.locator(".rd-v2-pill", { hasText: "Queued" })).toHaveCount(1);
    await expect(rowB.locator(".rd-v2-pill", { hasText: "Queued" })).toHaveCount(0);
  });

  test("in-flight probe for A does not toast or show evidence after selecting B", async ({ page }) => {
    let releaseA;
    const aGate = new Promise((resolve) => {
      releaseA = resolve;
    });
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Registry",
            rows: [
              {
                dataset_id: "mops_financial_statements_ext",
                title: "MOPS financial statements (Taiwan)",
                source: "MOPS",
                url: "https://mops.twse.com.tw/example",
              },
              {
                dataset_id: "twse_openapi_governance_ext",
                title: "TWSE OpenAPI governance disclosures",
                source: "TWSE",
                url: "https://openapi.twse.com.tw/example",
              },
            ],
          },
        ],
        total: 2,
      },
    });
    await page.unroute("**/library/discover/probe");
    await page.route("**/library/discover/probe", async (route) => {
      if (route.request().method() !== "POST") {
        return route.continue();
      }
      let body = {};
      try {
        body = JSON.parse(route.request().postData() || "{}");
      } catch {
        body = {};
      }
      const key = String(body.candidate_key || "");
      if (key.includes("mops_financial_statements_ext") || String(body.url || "").includes("mops.twse")) {
        await aGate;
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          connector: {
            id: "delayed_probe",
            connector_id: "delayed_probe",
            status: "candidate",
            spec: { access_mode: "direct_file", content_type: "text/csv", discovered_files: [] },
          },
          summary: "direct_file delayed for A",
          candidate_key: key || null,
          connector_id: "delayed_probe",
        }),
      });
    });

    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("governance");
    const mops = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
      hasText: "MOPS financial statements",
    });
    const twse = page.locator('.rd-v2-catalog button.row[data-kind="external"]', {
      hasText: "TWSE OpenAPI governance",
    });
    await mops.click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await twse.click();
    await expect(rail).toContainText("TWSE OpenAPI");
    releaseA();
    await page.waitForTimeout(400);
    await expect(rail).toContainText("TWSE OpenAPI");
    await expect(rail.locator(".rd-v2-discover-probe-result")).toHaveCount(0);
    await expect(page.locator(".rd-v2-toast")).toHaveCount(0);
  });

  test("resolved_url drives candidate key, probe URL, and collect payload", async ({ page }) => {
    const probeBodies = [];
    const collectBodies = [];
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Registry",
            rows: [
              {
                title: "Redirected dataset",
                source: "web",
                url: "https://short.example/x",
                resolved_url: "https://cdn.example.com/final/data.csv",
                dataset_id: "",
              },
            ],
          },
        ],
        total: 1,
      },
    });
    await page.unroute("**/library/discover/probe");
    await page.route("**/library/discover/probe", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const body = JSON.parse(route.request().postData() || "{}");
      probeBodies.push(body);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          connector: {
            id: "cdn_final",
            connector_id: "cdn_final",
            status: "candidate",
            spec: {
              access_mode: "direct_file",
              source_url: body.url,
              discovered_files: [],
            },
          },
          summary: "direct_file",
          candidate_key: body.candidate_key || null,
          connector_id: "cdn_final",
          resolved_url: body.url,
        }),
      });
    });
    await page.unroute("**/library/discover/collect");
    await page.route("**/library/discover/collect", async (route) => {
      if (route.request().method() !== "POST") return route.continue();
      const body = JSON.parse(route.request().postData() || "{}");
      collectBodies.push(body);
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          job: {
            id: "job-resolved-1",
            status: "pending_approval",
            candidate_key: body.candidate_key,
            connector_id: body.connector_id,
            request: body,
          },
        }),
      });
    });

    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("Redirected");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(rail.locator(".rd-v2-discover-probe-result")).toBeVisible();
    expect(probeBodies[0].url).toBe("https://cdn.example.com/final/data.csv");
    expect(probeBodies[0].candidate_key).toBe("url:https://cdn.example.com/final/data.csv");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" }).click();
    await expect.poll(() => collectBodies.length).toBe(1);
    expect(collectBodies[0]).toMatchObject({
      candidate_key: "url:https://cdn.example.com/final/data.csv",
      connector_id: "cdn_final",
      source_identity: "web",
      url: "https://cdn.example.com/final/data.csv",
    });
    expect(collectBodies[0]).not.toHaveProperty("source");
  });

  test("manually opened mobile Detail shows the selected candidate", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 1200 });
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]', { hasText: "MOPS" }).click();
    // Open Detail sheet via rail tab control (existing mobile chrome)
    const detailTab = page.getByRole("tab", { name: "Detail" });
    if (await detailTab.count()) {
      await detailTab.click();
    }
    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("MOPS financial statements");
    await expect(rail).not.toContainText("No candidate selected");
  });

  test("new Discover query clears stale selected candidate and resets filters", async ({ page }) => {
    await page.locator(".rd-v2-search-pill input").fill("MOPS");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS");

    await page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "Queued" }).click();
    await expect(page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "Queued" })).toHaveClass(/on/);

    await page.locator(".rd-v2-search-pill input").fill("no-such-dataset-xyz");
    await expect(page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "All" })).toHaveClass(/on/);
    await expect(page.locator("aside.rd-v2-rail")).toContainText("No candidate selected");
  });

  test("Preview ext opens external metadata modal", async ({ page }) => {
    await page.locator(".rd-v2-search-pill input").fill("TWSE");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await page.locator('.rd-v2-catalog button.row[data-kind="external"]').first().click();
    await page.locator("aside .rd-v2-rail-sticky").getByRole("button", { name: "Preview source" }).click();
    const modal = page.locator(".rd-v2-preview-modal");
    await expect(modal).toBeVisible();
    await expect(modal).toContainText("Publisher");
    await expect(modal).toContainText("Row preview is available after Add to lab");
    await expect(modal.locator(".rd-v2-preview-foot").getByRole("button", { name: "Close" })).toBeVisible();
  });
});

test.describe("v2 Discover API integration", () => {
  test("live discover API rows render in list", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await v2Nav(page, "Discover");
    await expect(page.locator(".rd-v2-chip", { hasText: "Discover API" })).toBeVisible();
    await expect(page.locator(".rd-v2-chip", { hasText: "Offline sample" })).toHaveCount(0);
    await expect(page.locator(".rd-v2-discover-list-panel")).toContainText("MOPS financial statements");
  });
});
