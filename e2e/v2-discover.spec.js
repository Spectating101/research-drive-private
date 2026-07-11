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
    await expect(page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate')).toHaveCount(1, { timeout: 10_000 });
    await expect(page.locator(".rd-v2-discover-list-panel")).toContainText("TWSE OpenAPI");
    await expect(page.locator(".rd-v2-discover-pipeline")).toContainText("Search");
    await expect(page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "External" })).toBeVisible();
  });

  test("selecting discover row opens evaluation surface with decision hierarchy", async ({ page }) => {
    await page.locator(".rd-v2-search-pill input").fill("MOPS");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate').first().click();
    const surface = page.getByTestId("discover-eval-surface");
    await expect(surface).toBeVisible();
    await expect(surface.locator(".rd-v2-eval-title")).toContainText("MOPS financial statements");
    await expect(surface).toContainText("Can I use this?");
    await expect(surface).toContainText("Useful for");
    await expect(surface).toContainText("Still unknown");
    await expect(surface.locator(".rd-v2-eval-tech")).toBeVisible();
    await expect(surface.locator(".rd-v2-eval-tech")).not.toHaveAttribute("open");
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary", { hasText: "Add to lab" })).toBeVisible();
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("What we know");
    await expect(page.locator("aside.rd-v2-rail")).not.toContainText("Possession");
  });

  test("Discover candidate Ask actions carry candidate context", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();

    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Ask about this source" }).click();
    await expect(rail.getByRole("tab", { name: "Ask" })).toHaveAttribute("aria-selected", "true");
    await expect(rail.locator(".rd-v2-ask-ctx")).toContainText("MOPS financial statements");
    await expect(page.getByTestId("ask-messages")).toContainText("Assess this");
    await expect(page.getByTestId("ask-messages")).toContainText("MOPS financial statements");
  });

  test("Probe source shows verified facts; technical evidence stays collapsed", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    const surface = page.getByTestId("discover-eval-surface");
    await expect(surface.locator(".rd-v2-eval-verified")).toContainText("text/csv");
    await expect(surface.locator(".rd-v2-eval-verified")).toContainText(/domain observed/i);
    await expect(surface.locator(".rd-v2-eval-verified")).not.toContainText("MOPS publisher");
    await expect(surface.locator(".rd-v2-eval-inferred")).toContainText(/direct file|machine-readable/i);
    await expect(surface.locator(".rd-v2-eval-tech")).not.toHaveAttribute("open");
    await surface.locator(".rd-v2-eval-tech > summary").click();
    await expect(surface.locator(".rd-v2-eval-tech")).toHaveAttribute("open", "");
    await expect(surface.locator(".rd-v2-eval-tech")).toContainText("Connector ID");
    await expect(surface.locator(".rd-v2-eval-tech")).toContainText("direct_file");
  });

  test("probe toast is candidate-scoped and clears on selection change", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Registry",
            rows: [
              {
                title: "Bare public CSV index",
                source: "Web",
                url: "https://example.com/index.csv",
              },
              {
                dataset_id: "mops_financial_statements_ext",
                title: "MOPS financial statements (Taiwan)",
                source: "MOPS",
                collect_via: "mops_tw",
                url: "https://mops.twse.com.tw/example",
              },
            ],
          },
        ],
        total: 2,
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("csv");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', {
      hasText: "Bare public CSV index",
    }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    const toast = page.locator(".rd-v2-toast");
    await expect(toast).toBeVisible();
    await expect(toast).toContainText("Bare public CSV index probed");
    await expect(toast).toHaveAttribute("data-toast-scope", "discover-probe");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', {
      hasText: "MOPS financial statements",
    }).click();
    await expect(page.getByTestId("discover-eval-surface")).toContainText("Acquisition available");
    await expect(page.getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified")).toHaveCount(0);
    await expect(page.locator(".rd-v2-toast[data-toast-scope='discover-probe']")).toHaveCount(0);
    await expect(page.locator(".rd-v2-toast")).toHaveCount(0);
  });

  test("Ask shows context-transition notice when history already exists", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await expect(page.getByTestId("ask-messages")).toContainText("Find datasets for: mops");
    await page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Detail" }).click();
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
    await page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" }).click();
    await expect(page.locator(".rd-v2-ask-ctx")).toContainText("Selected context · MOPS financial statements");
    await expect(page.getByTestId("ask-context-notice")).toContainText("New messages use this source context");
    await expect(page.getByTestId("ask-messages")).toContainText("Find datasets for: mops");
    const chatBodies = [];
    page.on("request", (req) => {
      if (req.url().includes("/library/chat") && req.method() === "POST") {
        chatBodies.push(req.postData() || "");
      }
    });
    await page.getByTestId("ask-composer").fill("What should I probe next?");
    await page.locator(".rd-v2-ask-input").getByRole("button", { name: "Send" }).click();
    await expect.poll(() => chatBodies.join("\n")).toMatch(/\[context:.*MOPS|mops_financial_statements/i);
  });

  test("Add to lab after probe stays on Detail with lifecycle", async ({ page }) => {
    await mockV2Api(page, { discoverBody: MOCK_DISCOVER_HIT });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(page.getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified")).toBeVisible();
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Add to lab" }).click();
    await expect(rail.getByRole("tab", { name: "Detail" })).toHaveAttribute("aria-selected", "true");
    const life = page.getByTestId("discover-lifecycle");
    await expect(life).toBeVisible();
    await expect(life).toContainText("Approval required");
    await expect(rail.locator(".rd-v2-rail-sticky .rd-v2-btn.primary")).toContainText("Review approval");
    const toast = page.locator(".rd-v2-toast");
    await expect(toast).toBeVisible();
    await expect(toast).toContainText(/approval required|queued/i);
    await expect(toast).not.toContainText(/job-discover-collect/i);
  });

  test("exact lifecycle job drives Collection status; title-only job does not", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: MOCK_DISCOVER_HIT,
      jobsBody: {
        jobs: [
          {
            id: "job-title-only",
            status: "running",
            plan: { title: "MOPS financial statements (Taiwan)" },
            candidate_key: null,
            connector_id: null,
          },
          {
            id: "job-exact",
            status: "failed",
            candidate_key: "dataset:mops_financial_statements_ext",
            connector_id: "example_com_data",
            error: "HTTP 403 from source",
            updated_at: "2026-07-10T12:00:00Z",
            plan: { title: "MOPS financial statements (Taiwan)" },
          },
        ],
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
    const life = page.getByTestId("discover-lifecycle");
    await expect(life).toContainText("Failed");
    await expect(life).toContainText("HTTP 403");
    await expect(page.locator("aside .rd-v2-rail-sticky .rd-v2-btn.primary")).toContainText(
      "Track in Resources",
    );
  });

  test("Track in Resources selects exact job row", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: MOCK_DISCOVER_HIT,
      jobsBody: {
        jobs: [
          {
            id: "job-exact-track",
            status: "pending_approval",
            candidate_key: "dataset:mops_financial_statements_ext",
            connector_id: "example_com_data",
            plan: { title: "MOPS financial statements (Taiwan)" },
          },
        ],
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
    await page.locator("aside .rd-v2-rail-sticky").getByRole("button", { name: "Review approval" }).click();
    await expect(page.locator(".yzu-sidebar")).toContainText("Resources");
    await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS financial statements");
    await expect(page.locator("aside.rd-v2-rail")).toContainText(/pending approval|approval/i);
  });

  test("registered without query readiness is not Query ready", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: MOCK_DISCOVER_HIT,
      jobsBody: {
        jobs: [
          {
            id: "job-reg",
            status: "completed",
            candidate_key: "dataset:mops_financial_statements_ext",
            registered_dataset_id: "mops_financial_statements_2026",
            plan: { title: "MOPS" },
          },
        ],
      },
    });
    await page.route("**/datasets", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([
          {
            dataset_id: "mops_financial_statements_2026",
            name: "MOPS statements",
            analysis_readiness: "metadata_search",
          },
        ]),
      }),
    );
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("mops");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
    const life = page.getByTestId("discover-lifecycle");
    await expect(life).toContainText("Registered in lab");
    await expect(life).not.toContainText("Query ready");
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
    const mops = page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', {
      hasText: "MOPS financial statements",
    });
    const twse = page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', {
      hasText: "TWSE OpenAPI governance",
    });
    await mops.click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(page.getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified")).toBeVisible();
    await twse.click();
    await expect(rail).toContainText("TWSE OpenAPI");
    await expect(page.getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified")).toHaveCount(0);
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
    await expect(page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate')).toHaveCount(2);
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
    const rowA = page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', {
      hasText: "MOPS financial statements",
    }).first();
    const rowB = page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', {
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
    const mops = page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', {
      hasText: "MOPS financial statements",
    });
    const twse = page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', {
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
    await expect(page.getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified")).toHaveCount(0);
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
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate').first().click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(page.getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified")).toBeVisible();
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
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate', { hasText: "MOPS" }).click();
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
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate').first().click();
    await expect(page.locator("aside.rd-v2-rail")).toContainText("MOPS");

    await page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "External" }).click();
    await expect(page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "External" })).toHaveClass(/on/);

    await page.locator(".rd-v2-search-pill input").fill("no-such-dataset-xyz");
    await expect(page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "All" })).toHaveClass(/on/);
    await expect(page.locator("aside.rd-v2-rail")).toContainText("No candidate selected");
  });

  test("D1 taxonomy: honest kinds, no FIT grid, filters map", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Mixed",
            rows: [
              {
                dataset_id: "gdelt_asia_daily_country_panel",
                title: "Asia daily news-risk panel",
                source: "GDELT",
                analysis_readiness: "instant",
                local_root: "research_panels/gdelt",
                coverage: "2018–2026 · Asia",
                description: "Lab panel ready for query",
              },
              {
                dataset_id: "registry_card_only",
                title: "Registry metadata card",
                source: "Lab registry",
                in_lab: true,
                description: "Registered metadata without a query path",
              },
              {
                title: "Inspectable open page",
                source: "Web",
                url: "https://example.com/open-data",
                description: "Public page without a collection route",
              },
              {
                title: "Licensed vendor fundamentals",
                source: "Vendor",
                manual_access: true,
                access_mode: "licensed",
                license: "Proprietary — commercial license",
                description: "Requires entitlement",
              },
            ],
          },
        ],
        total: 4,
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("panel");
    await page.locator(".rd-v2-search-pill input").press("Enter");

    const rows = page.locator(".rd-v2-catalog button.row.rd-v2-discover-candidate");
    await expect(rows).toHaveCount(4, { timeout: 10_000 });
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external"]')).toHaveCount(0);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="local-query-ready"]')).toHaveCount(1);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="local-metadata"]')).toHaveCount(1);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external-discoverable"]')).toHaveCount(1);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="licensed-manual"]')).toHaveCount(1);

    await expect(page.locator(".rd-v2-discover-fact", { hasText: "Fit" })).toHaveCount(0);
    await expect(page.locator(".rd-v2-discover-list-panel")).not.toContainText("Faculty finance");
    await expect(page.locator(".rd-v2-discover-list-panel")).not.toContainText("FIT · ACCESS · PROBE · DESTINATION");
    await expect(page.locator(".rd-v2-discover-pipeline")).toContainText("Process overview");
    await expect(page.locator(".rd-v2-discover-pipeline-steps span.on")).toHaveCount(0);
    await expect(page.locator(".rd-v2-discover-pipeline-steps span.done")).toHaveCount(0);

    // Single taxonomy statement — no duplicate readiness pill on normal rows
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="local-query-ready"] .rd-v2-discover-possession')).toContainText(
      "In lab · Query ready",
    );
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="local-query-ready"] .rd-v2-pill')).toHaveCount(0);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external-discoverable"] .rd-v2-pill')).toHaveCount(0);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="licensed-manual"] .rd-v2-pill')).toContainText("Manual access");
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="licensed-manual"] .rd-v2-discover-possession')).toContainText(
      "Licensed / manual access",
    );

    // Group order: local query-ready, local metadata, external, licensed
    await expect(rows.nth(0)).toHaveAttribute("data-kind", "local-query-ready");
    await expect(rows.nth(1)).toHaveAttribute("data-kind", "local-metadata");
    await expect(rows.nth(2)).toHaveAttribute("data-kind", "external-discoverable");
    await expect(rows.nth(3)).toHaveAttribute("data-kind", "licensed-manual");

    await page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "Query ready" }).click();
    await expect(page.locator(".rd-v2-catalog button.row.rd-v2-discover-candidate")).toHaveCount(1);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="local-query-ready"]')).toHaveCount(1);

    await page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "Needs access" }).click();
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="licensed-manual"]')).toHaveCount(1);
  });

  test("D1 taxonomy: probe stamps External · Probed without inventing acquisition", async ({ page }) => {
    await mockV2Api(page, {
      discoverBody: {
        sections: [
          {
            title: "Probeable",
            rows: [
              {
                title: "Bare public CSV index",
                source: "Web",
                url: "https://example.com/index.csv",
                description: "No collect_via — probe only",
              },
            ],
          },
        ],
        total: 1,
      },
    });
    await page.goto("/?tab=browse", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
    await page.locator(".rd-v2-search-pill input").fill("csv");
    const row = page.locator(".rd-v2-catalog button.row.rd-v2-discover-candidate").first();
    await expect(row).toHaveAttribute("data-kind", "external-discoverable");
    await row.click();
    const rail = page.locator("aside.rd-v2-rail");
    await rail.locator(".rd-v2-rail-sticky").getByRole("button", { name: "Probe source" }).click();
    await expect(page.getByTestId("discover-eval-surface").locator(".rd-v2-eval-verified")).toBeVisible();
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external-probed"]')).toHaveCount(1);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external-acquirable"]')).toHaveCount(0);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external-probed"] .rd-v2-pill')).toHaveCount(0);
    await expect(page.locator('.rd-v2-catalog button.row[data-kind="external-probed"] .rd-v2-discover-possession')).toContainText(
      "External · Probed",
    );
  });

  test("Preview ext opens external metadata modal", async ({ page }) => {
    await page.locator(".rd-v2-search-pill input").fill("TWSE");
    await page.locator(".rd-v2-search-pill input").press("Enter");
    await page.locator('.rd-v2-catalog button.row.rd-v2-discover-candidate').first().click();
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
