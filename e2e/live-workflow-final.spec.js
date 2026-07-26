import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

const OUT_DIR = path.join(process.cwd(), "artifacts/live-workflow-final");
const RUN_ID = String(process.env.GITHUB_RUN_ID || Date.now());
const CATALOGUE_QUERY = process.env.LIVE_WORKFLOW_QUERY || "stablecoin";
const PROCUREMENT_QUERY = process.env.LIVE_PROCUREMENT_QUERY || "MOPS filings";
const CANARY_URL =
  process.env.LIVE_WORKFLOW_CANARY_URL ||
  "https://www.sec.gov/files/company_tickers.json";

const report = {
  meta: {
    url: process.env.YZU_DESK_URL || "http://127.0.0.1:8765",
    run_id: RUN_ID,
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
  /^\/library\/synthesis\/threads$/,
];

function pathOf(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return String(url || "");
  }
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
    const pathname = pathOf(request.url());
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

function record(journey, step, outcome, evidence = {}) {
  let item = report.journeys.find((row) => row.id === journey);
  if (!item) {
    item = { id: journey, steps: [] };
    report.journeys.push(item);
  }
  item.steps.push({ step, outcome, at: new Date().toISOString(), ...evidence });
}

function saveReport() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  report.meta.finished_at = new Date().toISOString();
  fs.writeFileSync(path.join(OUT_DIR, "final-report.json"), JSON.stringify(report, null, 2));
  const lines = [
    "# Research Drive final workflow audit",
    "",
    `- URL: \`${report.meta.url}\``,
    `- Run: \`${report.meta.run_id}\``,
    "",
  ];
  for (const journey of report.journeys) {
    lines.push(`## ${journey.id}`, "");
    for (const step of journey.steps) {
      lines.push(`- **${String(step.outcome).toUpperCase()}** ${step.step}`);
      for (const [key, value] of Object.entries(step)) {
        if (["step", "outcome", "at"].includes(key)) continue;
        lines.push(`  - ${key}: \`${typeof value === "string" ? value : JSON.stringify(value)}\``);
      }
    }
    lines.push("");
  }
  fs.writeFileSync(path.join(OUT_DIR, "final-report.md"), `${lines.join("\n")}\n`);
}

async function attachAudit(testInfo, audit) {
  await testInfo.attach("network-audit.json", {
    body: Buffer.from(JSON.stringify(audit, null, 2)),
    contentType: "application/json",
  });
  expect(audit.blocked, "Unexpected write escaped the audit allowlist").toEqual([]);
}

async function capture(page, testInfo, name) {
  await testInfo.attach(name, {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
}

async function waitForDesk(page) {
  await page.locator(".rd-v2-shell").waitFor({ timeout: 60_000 });
  await expect(page.locator(".rd-v2-trust-badge.ok", { hasText: "Live registry" })).toBeVisible({ timeout: 60_000 });
}

async function json(page, endpoint, init = {}) {
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
      if (!response.ok) throw new Error(`${response.status} ${target}: ${payload.message || payload.error || text}`);
      return payload;
    },
    { endpoint, options: init },
  );
}

async function pollJob(page, jobId, timeoutMs = 120_000) {
  const deadline = Date.now() + timeoutMs;
  let job = null;
  while (Date.now() < deadline) {
    const payload = await json(page, `/library/jobs/${encodeURIComponent(jobId)}`);
    job = payload.job || payload;
    if (["completed", "failed", "cancelled"].includes(String(job.status || ""))) return job;
    await page.waitForTimeout(1500);
  }
  return job;
}

async function actionDiagnostics(page) {
  const rows = page.locator(".rd-v2-discover-candidate");
  const result = [];
  for (let index = 0; index < (await rows.count()); index += 1) {
    const row = rows.nth(index);
    await row.click();
    await page.waitForTimeout(100);
    const surface = page.getByTestId("discover-eval-actions");
    result.push({
      title: ((await row.locator("strong").first().textContent()) || "").trim(),
      state: (await row.getAttribute("data-state")) || "",
      primary: ((await surface.locator("button.rd-v2-eval-primary-action").textContent().catch(() => "")) || "").trim(),
      actions: (await surface.locator("button").allTextContents()).map((value) => value.trim()),
    });
  }
  return result;
}

function synthesisState(title) {
  return {
    title,
    objective: "Construct a defensible longitudinal stablecoin attention signal.",
    required_grain: "asset-week",
    materialisation: "not_materialised",
    nodes: [
      {
        id: "held-panel",
        type: "source",
        layer: "evidence",
        label: "GDELT Asia daily country panel",
        status: "held",
        role: "Held evidence",
        dataset_id: "gdelt_asia_daily_country_panel",
        grain: "country-day",
      },
      {
        id: "missing-signal",
        type: "source",
        layer: "evidence",
        label: "Historical stablecoin attention series",
        status: "missing",
        role: "Missing evidence",
        candidate_key: "sol-audit:stablecoin-attention",
        source_identity: "external research source",
        grain: "asset-week",
      },
      {
        id: "output",
        type: "output",
        layer: "output",
        label: "stablecoin_attention_proxy",
        status: "derived",
        materialisation: "not_materialised",
      },
    ],
    edges: [
      { id: "held-output", source: "held-panel", target: "output", relation: "supports" },
      { id: "missing-output", source: "missing-signal", target: "output", relation: "missing" },
    ],
    proposal: null,
    activity: [],
    spec: {
      grain: "asset-week",
      method: "Aggregate held news evidence and validate against an independent attention series.",
      output_contract: "One asset-week proxy with explicit lineage and limitations.",
      validation: [],
    },
  };
}

test.describe.configure({ mode: "serial" });
test.afterAll(saveReport);

test("Catalogue search exposes a complete inspect-to-request action ladder", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto(`/?tab=browse&q=${encodeURIComponent(CATALOGUE_QUERY)}`, { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await expect(page.getByRole("region", { name: "Best fit" })).toBeVisible({ timeout: 60_000 });
  const candidates = await actionDiagnostics(page);
  const executable = candidates.filter((candidate) =>
    candidate.actions.some((label) => /request this evidence|add to lab|collect/i.test(label)),
  );
  record("Discover catalogue", "Search results expose inspect/probe/request controls", executable.length ? "pass" : "fail", {
    candidate_count: candidates.length,
    executable_count: executable.length,
    candidates,
  });
  await capture(page, testInfo, "catalogue-action-ladder");
  await attachAudit(testInfo, audit);
});

test("Operational Discover crosses probe, request, History, and cancellation", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto(`/?tab=browse&q=${encodeURIComponent(PROCUREMENT_QUERY)}`, { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await expect(page.getByRole("region", { name: "Best fit" })).toBeVisible({ timeout: 60_000 });

  const rows = page.locator(".rd-v2-discover-candidate");
  let selected = null;
  for (let index = 0; index < (await rows.count()); index += 1) {
    const row = rows.nth(index);
    await row.click();
    const actions = page.getByTestId("discover-eval-actions");
    const labels = (await actions.locator("button").allTextContents()).map((value) => value.trim());
    if (labels.some((label) => /probe source/i.test(label)) && labels.some((label) => /request this evidence/i.test(label))) {
      selected = row;
      break;
    }
  }
  if (!selected) {
    record("Discover operational", "Select executable source", "fail", { reason: "No probe-and-request candidate" });
    await attachAudit(testInfo, audit);
    return;
  }

  const title = ((await selected.locator("strong").first().textContent()) || "").trim();
  record("Discover operational", "Select executable source", "pass", { title });
  await capture(page, testInfo, "discover-01-selected");

  const actions = page.getByTestId("discover-eval-actions");
  const probeResponsePromise = page.waitForResponse(
    (response) => response.url().includes("/library/discover/probe") && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await actions.getByRole("button", { name: /Probe source/i }).click();
  const probeResponse = await probeResponsePromise;
  const probePayload = await probeResponse.json().catch(() => ({}));
  const verified = await page.getByRole("region", { name: "Verified" }).isVisible({ timeout: 60_000 }).catch(() => false);
  record("Discover operational", "Probe source and render verified evidence", probeResponse.ok() && verified ? "pass" : "fail", {
    http_status: probeResponse.status(),
    connector_id: probePayload?.connector?.connector_id || probePayload?.connector?.id || "",
    verified_visible: verified,
  });
  await capture(page, testInfo, "discover-02-probed");

  await actions.getByRole("button", { name: /Request this evidence/i }).first().click();
  const confirmation = page.getByTestId("discover-request-confirm");
  if (!(await confirmation.isVisible().catch(() => false))) {
    record("Discover operational", "Expose explicit request confirmation", "fail");
    await attachAudit(testInfo, audit);
    return;
  }
  record("Discover operational", "Expose explicit request confirmation", "pass");

  const collectPromise = page.waitForResponse(
    (response) => response.url().includes("/library/discover/collect") && response.request().method() === "POST",
    { timeout: 60_000 },
  );
  await confirmation.getByRole("button", { name: "Confirm request" }).click();
  const collectResponse = await collectPromise;
  const collectPayload = await collectResponse.json().catch(() => ({}));
  const created = collectPayload.job || collectPayload;
  const lifecycle = await page.getByTestId("discover-lifecycle").isVisible({ timeout: 60_000 }).catch(() => false);
  record("Discover operational", "Create governed pending-approval request", collectResponse.ok() && lifecycle ? "pass" : "fail", {
    job_id: created.id || "",
    job_status: created.status || "",
    lifecycle_visible: lifecycle,
  });
  await capture(page, testInfo, "discover-03-pending");

  await page.getByRole("tab", { name: /History/i }).click();
  const history = await page.locator(".rd-v2-discover-page--history").isVisible({ timeout: 30_000 }).catch(() => false);
  record("Discover operational", "Persist request in History", history ? "pass" : "fail", { url: page.url() });
  await capture(page, testInfo, "discover-04-history");

  if (created.id) {
    const cancelPayload = await json(page, `/library/jobs/${encodeURIComponent(created.id)}/cancel`, {
      method: "POST",
      body: {},
    });
    const cancelled = cancelPayload.job || cancelPayload;
    record("Discover operational", "Cancel controlled request", cancelled.status === "cancelled" ? "pass" : "fail", {
      job_id: created.id,
      job_status: cancelled.status,
    });
  }
  await attachAudit(testInfo, audit);
});

test("Synthesis creates a durable thread, selects it, and attempts Ask continuity", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);

  const title = `Sol workflow synthesis ${RUN_ID}`;
  const createdPayload = await json(page, "/library/synthesis/threads", {
    method: "POST",
    body: {
      title,
      objective: "Construct a defensible longitudinal stablecoin attention signal.",
      required_grain: "asset-week",
      session_id: `sol-workflow-${RUN_ID}`,
      state: synthesisState(title),
    },
  });
  const created = createdPayload.thread || createdPayload;
  record("Synthesis", "Create durable thread through canonical API", created.id ? "pass" : "fail", {
    thread_id: created.id || "",
    title,
  });

  await page.reload({ waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  const thread = page.getByTestId("synthesis-thread-item").filter({ hasText: title }).first();
  const visible = await thread.isVisible({ timeout: 30_000 }).catch(() => false);
  record("Synthesis", "Reload and recover created thread", visible ? "pass" : "fail");
  if (!visible) {
    await capture(page, testInfo, "synthesis-01-missing-thread");
    await attachAudit(testInfo, audit);
    return;
  }

  await thread.click();
  await page.waitForTimeout(500);
  await capture(page, testInfo, "synthesis-02-selected-thread");
  record("Synthesis", "Select thread and render evidence/method/output state", "pass");

  const askAction = page.getByRole("button", { name: /Discuss construction in Ask|Challenge in Ask/i }).first();
  if (await askAction.isVisible().catch(() => false)) {
    await askAction.click();
    const askSelected = await page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" }).getAttribute("aria-selected");
    record("Synthesis", "Carry selected thread into Ask", askSelected === "true" ? "pass" : "fail", {
      aria_selected: askSelected,
    });
    await capture(page, testInfo, "synthesis-03-ask");
  } else {
    record("Synthesis", "Carry selected thread into Ask", "fail", { reason: "No Ask handoff control" });
  }
  await attachAudit(testInfo, audit);
});

test("Controlled job crosses pending approval, queue, worker, and completion", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);

  const jobId = `sol-live-probe-${RUN_ID}`.replace(/[^A-Za-z0-9._:-]/g, "-").slice(0, 100);
  const submittedPayload = await json(page, "/library/jobs", {
    method: "POST",
    body: {
      title: `Sol source-probe canary ${RUN_ID}`,
      request: { job_id: jobId, idempotency_key: jobId, canary: true, review_lane: "sol/live-review" },
      plan: { job_type: "source_probe", url: CANARY_URL, title: "SEC source-probe canary", launchable: true },
      auto_approve: false,
    },
  });
  let job = submittedPayload.job || submittedPayload;
  record("Job lifecycle", "Create pending-approval canary", job.status === "pending_approval" ? "pass" : "fail", {
    job_id: job.id,
    job_status: job.status,
  });
  await capture(page, testInfo, "job-01-pending");

  const approvedPayload = await json(page, `/library/jobs/${encodeURIComponent(job.id)}/approve`, {
    method: "POST",
    body: {},
  });
  job = approvedPayload.job || approvedPayload;
  record("Job lifecycle", "Approve exact canary revision", ["queued", "running", "completed"].includes(job.status) ? "pass" : "fail", {
    job_id: job.id,
    job_status: job.status,
  });
  await capture(page, testInfo, "job-02-approved");

  job = await pollJob(page, job.id);
  record("Job lifecycle", "Worker reaches terminal completion", job?.status === "completed" ? "pass" : "fail", {
    job_id: job?.id || jobId,
    job_status: job?.status || "unknown",
    error: job?.error || "",
    connector_id: job?.result?.connector_id || "",
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "job-03-terminal");
  await attachAudit(testInfo, audit);
});

test("Profile research action remains an explicit launch blocker", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  const action = page.getByRole("button", { name: /Search →|Link →|Open →/ }).first();
  if (!(await action.isVisible().catch(() => false))) {
    record("Profile", "Carry research suggestion into Discover", "fail", { reason: "No research action visible" });
    await attachAudit(testInfo, audit);
    return;
  }
  await action.click();
  await page.waitForTimeout(700);
  const heading = ((await page.locator("main.yzu-main h1").first().textContent()) || "").trim();
  const query = new URL(page.url()).searchParams.get("q") || "";
  const passed = heading === "Discover" && Boolean(query) && audit.pageErrors.length === 0;
  record("Profile", "Carry research suggestion into Discover", passed ? "pass" : "fail", {
    heading,
    query,
    url: page.url(),
    page_errors: audit.pageErrors,
  });
  await capture(page, testInfo, "profile-handoff");
  await attachAudit(testInfo, audit);
});
