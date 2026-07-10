/**
 * Golden procurement path — API spine + v2 Ask job closure (mock + live).
 * Run live: bash scripts/run_research_query_engine.sh & npm run test:golden-procure
 */
import { test, expect } from "@playwright/test";
import { mockV2Api, waitForShell } from "./fixtures/v2MockApi.js";

const API = process.env.YZU_API_URL || "http://127.0.0.1:8765";
const EMAIL = process.env.DESK_TEST_EMAIL || "drkong@saturn.yzu.edu.tw";
const PROBE_URL = "https://www.sec.gov/files/company_tickers.json";

let apiLive = false;

async function probeDeskApiNative() {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      const res = await fetch(`${API}/health?live=1`, { signal: AbortSignal.timeout(15_000) });
      if (res.ok) {
        const body = await res.json();
        if (body.status === "ok") return true;
      }
    } catch {
      // Desk API may still be warming.
    }
    await new Promise((resolve) => setTimeout(resolve, 1_500));
  }
  return false;
}

test.beforeAll(async () => {
  apiLive = await probeDeskApiNative();
});

test.describe("procurement golden path @mock", () => {
  test.beforeEach(async ({ page }) => {
    await mockV2Api(page, {
      chatComplete: {
        reply: "Queued SEC company tickers for cluster collection.",
        action: "submit_collect",
        job_id: "job-golden-mock-01",
        job_status: "pending_approval",
        artifacts: {
          action: "submit_collect",
          job_id: "job-golden-mock-01",
          procurement_submit: true,
        },
      },
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
    await waitForShell(page);
  });

  test("Ask shows job tracker and approve affordance", async ({ page }) => {
    await page.locator("aside.yzu-sidebar").getByRole("button", { name: "Home", exact: true }).click();
    await page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" }).click();
    await page.getByTestId("ask-composer").fill("collect SEC company tickers JSON");
    await page.locator(".rd-v2-ask-send-row .rd-v2-btn.primary").click();
    await expect(page.getByTestId("ask-job-tracker")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("ask-job-tracker")).toContainText("Pending approval");
    await expect(page.getByTestId("ask-job-tracker").getByRole("button", { name: "Approve" })).toBeVisible();
  });
});

test.describe("procurement golden path @live-api", () => {
  test.beforeEach(() => {
    test.skip(!apiLive, `Desk API not live at ${API}`);
  });

  test("API discover → probe → library job submit path", async ({ request }) => {
    const discover = await request.get(
      `${API}/library/discover?q=${encodeURIComponent("SEC company tickers")}&limit=8`,
    );
    expect(discover.ok()).toBeTruthy();

    const probe = await request.post(`${API}/library/discover/probe`, {
      data: { url: PROBE_URL, name: "SEC tickers" },
    });
    expect(probe.ok()).toBeTruthy();
    const probeBody = await probe.json();
    expect(probeBody.connector || probeBody.summary).toBeTruthy();

    const submit = await request.post(`${API}/library/jobs`, {
      data: {
        title: "e2e golden: sec_company_tickers",
        auto_approve: false,
        plan: {
          job_type: "collection_queue_task",
          task_id: "sec_company_tickers",
          dataset_id: "sec_company_tickers",
          partition_id: "acquired.procured",
          launchable: true,
          timeout_seconds: 120,
        },
      },
    });
    expect(submit.ok()).toBeTruthy();
    const job = await submit.json();
    const jobId = job.id || job.job?.id;
    expect(jobId).toBeTruthy();

    const approve = await request.post(`${API}/library/jobs/${jobId}/approve`, { data: {} });
    expect(approve.ok()).toBeTruthy();
    const approved = await approve.json();
    expect(["queued", "running", "completed"]).toContain(approved.status);

    const get = await request.get(`${API}/library/jobs/${jobId}`);
    expect(get.ok()).toBeTruthy();
  });

  test("API chat session round-trip", async ({ request }) => {
    const chat = await request.post(`${API}/library/chat`, {
      data: { message: "status", user_email: EMAIL },
    });
    expect(chat.ok()).toBeTruthy();
    const payload = await chat.json();
    const sid = payload.session_id;
    expect(sid).toBeTruthy();
    const session = await request.get(`${API}/library/chat/${sid}`);
    expect(session.ok()).toBeTruthy();
    const body = await session.json();
    expect(Array.isArray(body.messages)).toBeTruthy();
    expect(body.messages.length).toBeGreaterThan(0);
  });

  test("API approve-safe endpoint", async ({ request }) => {
    const res = await request.post(`${API}/library/jobs/approve-safe`, { data: { limit: 50 } });
    expect(res.ok()).toBeTruthy();
    const body = await res.json();
    expect(body).toHaveProperty("approved_count");
  });
});
