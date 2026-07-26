import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, "artifacts/live-workflow-completion");
const REPORT_JSON = path.join(OUT_DIR, "completion-report.json");
const REPORT_MD = path.join(OUT_DIR, "completion-report.md");
const RUN_ID = String(process.env.GITHUB_RUN_ID || Date.now());
const SEARCH_QUERY = process.env.LIVE_WORKFLOW_QUERY || "stablecoin";
const PROCUREMENT_QUERY = process.env.LIVE_PROCUREMENT_QUERY || "MOPS filings";
const CANARY_URL = process.env.LIVE_WORKFLOW_CANARY_URL || "https://api.datacite.org/dois/10.5281/zenodo.1000000";

const report = {
  meta: {
    url: process.env.YZU_DESK_URL || "https://previous.easycamp.tech",
    run_id: RUN_ID,
    search_query: SEARCH_QUERY,
    procurement_query: PROCUREMENT_QUERY,
    started_at: new Date().toISOString(),
  },
  journeys: [],
};

const SAFE_POSTS = [
  /^\/library\/desk\/(session|warm)$/,
  /^\/library\/discover\/probe$/,
  /^\/library\/discover\/collect$/,
  /^\/library\/jobs$/,
  /^\/library\/jobs\/[^/]+\/(approve|cancel)$/,
];

function pathnameOf(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return String(url || "");
  }
}

function journey(id) {
  let item = report.journeys.find((entry) => entry.id === id);
  if (!item) {
    item = { id, steps: [] };
    report.journeys.push(item);
  }
  return item;
}

function record(id, step, status, evidence = {}) {
  journey(id).steps.push({ step, status, at: new Date().toISOString(), ...evidence });
}

function saveReport() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  report.meta.finished_at = new Date().toISOString();
  fs.writeFileSync(REPORT_JSON, JSON.stringify(report, null, 2));
  const lines = [
    "# Research Drive live workflow completion report",
    "",
    `- URL: \`${report.meta.url}\``,
    `- Run: \`${report.meta.run_id}\``,
    `- Search query: \`${report.meta.search_query}\``,
    `- Procurement query: \`${report.meta.procurement_query}\``,
    "",
  ];
  for (const item of report.journeys) {
    lines.push(`## ${item.id}`, "");
    for (const step of item.steps) {
      lines.push(`- **${String(step.status).toUpperCase()}** ${step.step}`);
      for (const [key, value] of Object.entries(step)) {
        if (["step", "status", "at"].includes(key)) continue;
        lines.push(`  - ${key}: \`${typeof value === "string" ? value : JSON.stringify(value)}\``);
      }
    }
    lines.push("");
  }
  fs.writeFileSync(REPORT_MD, `${lines.join("\n")}\n`);
}

function newAudit() {
  return { allowed: [], blocked: [], telemetry: [], pageErrors: [], consoleErrors: [] };
}

async function installGuard(page, audit) {
  page.on("pageerror", (error) => audit.pageErrors.push(String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") audit.consoleErrors.push(message.text());
  });
  await page.route("**/*", async (route) => {
    const request = route.request();
    const method = request.method().toUpperCase();
    const pathname = pathnameOf(request.url());
    if (["GET", "HEAD", "OPTIONS"].includes(method)) {
      await route.continue();
      return;
    }
    if (method === "POST" && pathname === "/cdn-cgi/rum") {
      audit.telemetry.push({ method, pathname });
      await route.abort("blockedbyclient");
      return;
    }
    if (method === "POST" && SAFE_POSTS.some((pattern) => pattern.test(pathname))) {
      audit.allowed.push({ method, pathname });
      await route.continue();
      return;
    }
    audit.blocked.push({ method, pathname });
    await route.abort("blockedbyclient");
  });
}

async function attachAudit(testInfo, audit) {
  await testInfo.attach("network-audit.json", {
    body: Buffer.from(JSON.stringify(audit, null, 2)),
    contentType: "application/json",
  });
}

async function capture(page, testInfo, name) {
  const body = await page.screenshot({ fullPage: true });
  await testInfo.attach(name, { body, contentType: "image/png" });
}

async function waitForDesk(page) {
  await page.locator(".rd-v2-shell").waitFor({ timeout: 60_000 });
  await expect(page.locator(".rd-v2-trust-badge.ok", { hasText: "Live registry" })).toBeVisible({ timeout: 60_000 });
}

async function sameOriginJson(page, endpoint, init = {}) {
  return page.evaluate(
    async ({ endpoint: target, options }) => {
      const response = await fetch(target, {
        credentials: "include",
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
        body: options.body ? JSON.stringify(options.body) : undefined,
      });
      const text = await response.text();
      let payload = {};
      try {
        payload = text ? JSON.parse(text) : {};
      } catch {
        payload = { raw: text };
      }
      if (!response.ok) {
        throw new Error(`${response.status} ${target}: ${payload.message || payload.error || text}`);
      }
      return payload;
    },
    { endpoint, options: init },
  );
}

async function heading(page) {
  return ((await page.locator("main.yzu-main h1").first().textContent().catch(() => "")) || "").trim();
}

async function candidateDiagnostics(page) {
  const rows = page.locator(".rd-v2-discover-candidate");
  const count = await rows.count();
  const diagnostics = [];
  for (let index = 0; index < count; index += 1) {
    const row = rows.nth(index);
    await row.click();
    await page.waitForTimeout(100);
    const actions = page.getByTestId("discover-eval-actions");
    diagnostics.push({
      index,
      title: ((await row.locator("strong").first().textContent().catch(() => "")) || "").trim(),
      state: (await row.getAttribute("data-state")) || "",
      kind: (await row.getAttribute("data-kind")) || "",
      primary: ((await actions.locator("button.rd-v2-eval-primary-action").textContent().catch(() => "")) || "").trim(),
      actions: await actions.locator("button").allTextContents().catch(() => []),
    });
  }
  return diagnostics;
}

async function selectOperationalCandidate(page) {
  const rows = page.locator(".rd-v2-discover-candidate");
  const count = await rows.count();
  for (let index = 0; index < count; index += 1) {
    const row = rows.nth(index);
    await row.click();
    await page.waitForTimeout(150);
    const actions = page.getByTestId("discover-eval-actions");
    const labels = (await actions.locator("button").allTextContents()).map((value) => value.trim());
    const primary = ((await actions.locator("button.rd-v2-eval-primary-action").textContent().catch(() => "")) || "").trim();
    if (labels.some((label) => /probe source/i.test(label)) || /request|add to lab|collect/i.test(primary)) {
      return { row, index, labels, primary };
    }
  }
  return null;
}

async function pollJob(page, jobId, timeoutMs = 150_000) {
  const deadline = Date.now() + timeoutMs;
  let job = null;
  while (Date.now() < deadline) {
    const payload = await sameOriginJson(page, `/library/jobs/${encodeURIComponent(jobId)}`);
    job = payload.job || payload;
    if (["completed", "failed", "cancelled"].includes(String(job.status || ""))) return job;
    await page.waitForTimeout(2500);
  }
  return job;
}

test.afterAll(() => saveReport());

test("Discover catalogue evaluation exposes its actual action boundary", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto(`/?tab=browse&q=${encodeURIComponent(SEARCH_QUERY)}`, { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await expect(page.getByRole("region", { name: "Best fit" })).toBeVisible({ timeout: 60_000 });
  const diagnostics = await candidateDiagnostics(page);
  await capture(page, testInfo, "discover-catalogue-actions");
  record("Discover catalogue", "Enumerate candidate action contracts", "observed", {
    candidates: diagnostics,
    page_errors: audit.pageErrors,
  });
  const requestable = diagnostics.filter((item) => /request|add to lab|collect/i.test(item.primary));
  record(
    "Discover catalogue",
    "Catalogue records expose executable procurement action",
    requestable.length ? "pass" : "fail",
    { requestable_count: requestable.length },
  );
  await attachAudit(testInfo, audit);
});

test("Discover operational route: select, probe, request, History, cleanup", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto(`/?tab=browse&q=${encodeURIComponent(PROCUREMENT_QUERY)}`, { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await expect(page.getByRole("region", { name: "Best fit" })).toBeVisible({ timeout: 60_000 });
  await capture(page, testInfo, "discover-operational-01-results");

  const target = await selectOperationalCandidate(page);
  if (!target) {
    const diagnostics = await candidateDiagnostics(page);
    record("Discover operational", "Find source with probe/request contract", "fail", { candidates: diagnostics });
    await attachAudit(testInfo, audit);
    return;
  }

  const title = ((await target.row.locator("strong").first().textContent()) || "").trim();
  record("Discover operational", "Select operational source candidate", "pass", {
    title,
    state: await target.row.getAttribute("data-state"),
    primary: target.primary,
    actions: target.labels,
  });
  await capture(page, testInfo, "discover-operational-02-selected");

  const actions = page.getByTestId("discover-eval-actions");
  const probe = actions.getByRole("button", { name: /Probe source/i });
  if (await probe.isVisible().catch(() => false)) {
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes("/library/discover/probe") && response.request().method() === "POST",
      { timeout: 60_000 },
    );
    await probe.click();
    const response = await responsePromise;
    const payload = await response.json().catch(() => ({}));
    await page.waitForTimeout(500);
    const verifiedVisible = await page.getByRole("region", { name: "Verified" }).isVisible().catch(() => false);
    record("Discover operational", "Probe source through live runtime", response.ok() && verifiedVisible ? "pass" : "fail", {
      http_status: response.status(),
      verified_visible: verifiedVisible,
      connector_id: payload?.connector?.connector_id || payload?.connector?.id || "",
    });
    await capture(page, testInfo, "discover-operational-03-probed");
  } else {
    record("Discover operational", "Probe source through live runtime", "fail", { reason: "Probe action absent" });
  }

  const primary = actions.locator("button.rd-v2-eval-primary-action");
  const primaryLabel = ((await primary.textContent().catch(() => "")) || "").trim();
  if (!/request|add to lab|collect/i.test(primaryLabel)) {
    record("Discover operational", "Move from evaluation to durable request", "fail", {
      reason: "Primary action is not a request/collection transition",
      primary: primaryLabel,
      actions: await actions.locator("button").allTextContents(),
    });
    await attachAudit(testInfo, audit);
    return;
  }

  await primary.click();
  const confirm = page.getByTestId("discover-request-confirm");
  if (!(await confirm.isVisible().catch(() => false))) {
    record("Discover operational", "Move from evaluation to durable request", "fail", {
      reason: "No explicit confirmation boundary",
      primary: primaryLabel,
    });
    await attachAudit(testInfo, audit);
    return;
  }

  const collectPromise = page.waitForResponse(
    (response) => response.url().includes("/library/discover/collect") && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await confirm.getByRole("button", { name: "Confirm request" }).click();
  const collectResponse = await collectPromise;
  const collectPayload = await collectResponse.json().catch(() => ({}));
  const created = collectPayload.job || collectPayload;
  const lifecycleVisible = await page.getByTestId("discover-lifecycle").isVisible({ timeout: 60_000 }).catch(() => false);
  record("Discover operational", "Create pending-approval lifecycle item", collectResponse.ok() && lifecycleVisible ? "pass" : "fail", {
    job_id: created.id || "",
    status: created.status || "",
    lifecycle_visible: lifecycleVisible,
  });
  await capture(page, testInfo, "discover-operational-04-requested");

  await page.getByRole("tab", { name: /History/i }).click();
  const historyVisible = await page.locator(".rd-v2-discover-page--history").isVisible({ timeout: 30_000 }).catch(() => false);
  record("Discover operational", "Open durable History after request", historyVisible ? "pass" : "fail", { url: page.url() });
  await capture(page, testInfo, "discover-operational-05-history");

  if (created.id) {
    const cancelledPayload = await sameOriginJson(page, `/library/jobs/${encodeURIComponent(created.id)}/cancel`, {
      method: "POST",
      body: {},
    });
    const cancelled = cancelledPayload.job || cancelledPayload;
    record("Discover operational", "Cancel controlled request after audit", cancelled.status === "cancelled" ? "pass" : "fail", {
      job_id: created.id,
      status: cancelled.status,
    });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForDesk(page);
    await capture(page, testInfo, "discover-operational-06-cancelled");
  }
  await attachAudit(testInfo, audit);
});

test("Profile handoff is exercised without stopping the remaining audit", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  const action = page.getByRole("button", { name: /Search →|Link →|Open →/ }).first();
  if (!(await action.isVisible().catch(() => false))) {
    record("Profile", "Research action enters Discover", "fail", { reason: "No research action visible" });
    await attachAudit(testInfo, audit);
    return;
  }
  const label = ((await action.textContent()) || "").trim();
  await action.click();
  await page.waitForTimeout(700);
  const currentHeading = await heading(page);
  const query = new URL(page.url()).searchParams.get("q") || "";
  const passed = currentHeading === "Discover" && Boolean(query) && audit.pageErrors.length === 0;
  record("Profile", "Research action enters Discover", passed ? "pass" : "fail", {
    action: label,
    heading: currentHeading,
    query,
    url: page.url(),
    page_errors: audit.pageErrors,
  });
  await capture(page, testInfo, "profile-handoff-result");
  await attachAudit(testInfo, audit);
});

test("Settings local workflow persists display choices", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=settings", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "settings-01-initial");
  const defaultTab = page.locator("#rd-settings-default-tab");
  const onSelect = page.locator("#rd-settings-on-select");
  const controlsVisible = await defaultTab.isVisible().catch(() => false) && await onSelect.isVisible().catch(() => false);
  if (!controlsVisible) {
    record("Settings", "Display preferences are editable", "fail", { reason: "Preference controls missing" });
    await attachAudit(testInfo, audit);
    return;
  }
  await defaultTab.selectOption("library");
  await onSelect.selectOption("ask");
  record("Settings", "Display preferences are editable", "pass", {
    default_tab: await defaultTab.inputValue(),
    on_select: await onSelect.inputValue(),
  });
  await page.goto("/", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  const currentHeading = await heading(page);
  record("Settings", "Default route preference applies", currentHeading === "Library" ? "pass" : "fail", {
    heading: currentHeading,
    url: page.url(),
  });
  await capture(page, testInfo, "settings-02-default-route");
  await attachAudit(testInfo, audit);
});

test("Synthesis read workflow preserves thread context into Ask", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  const threads = page.getByTestId("synthesis-thread-item");
  const count = await threads.count();
  record("Synthesis", "Durable threads load", count ? "pass" : "fail", { thread_count: count });
  await capture(page, testInfo, "synthesis-01-threads");
  if (!count) {
    await attachAudit(testInfo, audit);
    return;
  }
  const target = threads.nth(Math.min(1, count - 1));
  const threadLabel = ((await target.textContent()) || "").trim().slice(0, 180);
  await target.click();
  await page.waitForTimeout(500);
  const constructionVisible = await page.locator("[data-testid^='synthesis-']").first().isVisible().catch(() => false);
  record("Synthesis", "Select thread and render its current state", constructionVisible ? "pass" : "fail", {
    thread: threadLabel,
  });
  const askAction = page.getByRole("button", { name: /Discuss construction in Ask|Challenge in Ask/i }).first();
  if (await askAction.isVisible().catch(() => false)) {
    await askAction.click();
    const askSelected = await page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" }).getAttribute("aria-selected");
    record("Synthesis", "Carry selected thread into Ask", askSelected === "true" ? "pass" : "fail", {
      aria_selected: askSelected,
    });
    await capture(page, testInfo, "synthesis-02-ask");
  } else {
    record("Synthesis", "Carry selected thread into Ask", "fail", { reason: "Ask action missing" });
  }
  await attachAudit(testInfo, audit);
});

test("Controlled source-probe job crosses approval, queue, worker, and terminal state", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  const jobId = `sol-live-probe-${RUN_ID}`.replace(/[^A-Za-z0-9._:-]/g, "-").slice(0, 100);
  let job = null;
  try {
    const submittedPayload = await sameOriginJson(page, "/library/jobs", {
      method: "POST",
      body: {
        title: `Sol live workflow canary ${RUN_ID}`,
        request: { job_id: jobId, idempotency_key: jobId, canary: true, review_lane: "sol/live-review" },
        plan: { job_type: "source_probe", url: CANARY_URL, title: "DataCite source-probe canary", launchable: true },
        auto_approve: false,
      },
    });
    job = submittedPayload.job || submittedPayload;
    record("Job lifecycle", "Create pending-approval canary", job.status === "pending_approval" ? "pass" : "fail", {
      job_id: job.id,
      status: job.status,
    });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForDesk(page);
    await capture(page, testInfo, "job-01-pending");

    const approvedPayload = await sameOriginJson(page, `/library/jobs/${encodeURIComponent(job.id)}/approve`, {
      method: "POST",
      body: {},
    });
    job = approvedPayload.job || approvedPayload;
    record("Job lifecycle", "Approve exact pending job", ["queued", "running", "completed"].includes(job.status) ? "pass" : "fail", {
      job_id: job.id,
      status: job.status,
    });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForDesk(page);
    await capture(page, testInfo, "job-02-approved");

    job = await pollJob(page, job.id);
    record("Job lifecycle", "Worker reaches terminal state", job?.status === "completed" ? "pass" : "fail", {
      job_id: job?.id || jobId,
      status: job?.status || "unknown",
      error: job?.error || "",
      result: job?.result || {},
    });
    await page.reload({ waitUntil: "domcontentloaded" });
    await waitForDesk(page);
    await capture(page, testInfo, "job-03-terminal");
  } catch (error) {
    record("Job lifecycle", "Execute controlled source-probe lifecycle", "fail", { error: String(error) });
  } finally {
    if (job?.id && !["completed", "failed", "cancelled"].includes(String(job.status || ""))) {
      try {
        const cancelledPayload = await sameOriginJson(page, `/library/jobs/${encodeURIComponent(job.id)}/cancel`, {
          method: "POST",
          body: {},
        });
        const cancelled = cancelledPayload.job || cancelledPayload;
        record("Job lifecycle", "Cleanup nonterminal canary", cancelled.status === "cancelled" ? "pass" : "fail", {
          job_id: job.id,
          status: cancelled.status,
        });
      } catch (cleanupError) {
        record("Job lifecycle", "Cleanup nonterminal canary", "fail", { error: String(cleanupError) });
      }
    }
  }
  await attachAudit(testInfo, audit);
});
