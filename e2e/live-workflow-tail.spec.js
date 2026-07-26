import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

const OUT_DIR = path.join(process.cwd(), "artifacts/live-workflow-tail");
const RUN_ID = String(process.env.GITHUB_RUN_ID || Date.now());
const CANARY_URL = process.env.LIVE_WORKFLOW_CANARY_URL || "https://www.sec.gov/files/company_tickers.json";
const report = { meta: { url: process.env.YZU_DESK_URL || "http://127.0.0.1:8765", run_id: RUN_ID }, journeys: [] };

const SAFE_POSTS = [
  /^\/library\/desk\/(session|warm)$/,
  /^\/library\/synthesis\/threads$/,
  /^\/library\/chat(?:\/stream)?$/,
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
  fs.writeFileSync(path.join(OUT_DIR, "tail-report.json"), JSON.stringify(report, null, 2));
  const lines = ["# Research Drive workflow tail audit", "", `- URL: \`${report.meta.url}\``, `- Run: \`${RUN_ID}\``, ""];
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
  fs.writeFileSync(path.join(OUT_DIR, "tail-report.md"), `${lines.join("\n")}\n`);
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
  expect(audit.blocked, "Unexpected write escaped the tail allowlist").toEqual([]);
}

async function capture(page, testInfo, name) {
  await testInfo.attach(name, { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
}

async function waitForDesk(page) {
  await page.locator(".rd-v2-shell").waitFor({ timeout: 60_000 });
  await expect(page.locator(".rd-v2-trust-badge.ok", { hasText: "Live registry" })).toBeVisible({ timeout: 60_000 });
}

async function requestJson(page, endpoint, init = {}) {
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
    const payload = await requestJson(page, `/library/jobs/${encodeURIComponent(jobId)}`);
    job = payload.job || payload;
    if (["completed", "failed", "cancelled"].includes(String(job.status || ""))) return job;
    await page.waitForTimeout(1500);
  }
  return job;
}

function synthesisState(title) {
  return {
    title,
    objective: "Construct a defensible stablecoin attention signal.",
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
        candidate_key: "sol-tail:stablecoin-attention",
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
      method: "Aggregate held evidence and validate against an independent signal.",
      output_contract: "One asset-week proxy with explicit lineage and limitations.",
      validation: [],
    },
  };
}

test.describe.configure({ mode: "serial" });
test.afterAll(saveReport);

test("Synthesis thread carries through the real Ask request", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);

  const title = `Sol Ask thread ${RUN_ID}`;
  const payload = await requestJson(page, "/library/synthesis/threads", {
    method: "POST",
    body: {
      title,
      objective: "Construct a defensible stablecoin attention signal.",
      required_grain: "asset-week",
      session_id: `sol-tail-${RUN_ID}`,
      state: synthesisState(title),
    },
  });
  const created = payload.thread || payload;
  record("Synthesis Ask", "Create durable thread", created.id ? "pass" : "fail", { thread_id: created.id || "" });

  await page.reload({ waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  const thread = page.getByTestId("synthesis-thread-item").filter({ hasText: title }).first();
  const visible = await thread.isVisible({ timeout: 30_000 }).catch(() => false);
  record("Synthesis Ask", "Recover created thread after reload", visible ? "pass" : "fail");
  if (!visible) {
    await attachAudit(testInfo, audit);
    return;
  }
  await thread.click();
  await page.waitForTimeout(300);

  const askAction = page.getByRole("button", { name: /Discuss construction in Ask|Challenge in Ask/i }).first();
  if (!(await askAction.isVisible().catch(() => false))) {
    record("Synthesis Ask", "Expose Ask handoff", "fail", { reason: "No Ask control" });
    await capture(page, testInfo, "synthesis-no-ask-control");
    await attachAudit(testInfo, audit);
    return;
  }

  const chatPromise = page.waitForResponse(
    (response) => {
      const pathname = pathnameOf(response.url());
      return response.request().method() === "POST" && ["/library/chat", "/library/chat/stream"].includes(pathname);
    },
    { timeout: 60_000 },
  );
  await askAction.click();
  const chatResponse = await chatPromise;
  const responseText = await chatResponse.text().catch(() => "");
  const askSelected = await page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" }).getAttribute("aria-selected");
  record("Synthesis Ask", "Send selected thread context through Ask", chatResponse.ok() && askSelected === "true" ? "pass" : "fail", {
    http_status: chatResponse.status(),
    ask_selected: askSelected,
    response_excerpt: responseText.slice(0, 500),
  });
  await capture(page, testInfo, "synthesis-ask-response");
  await attachAudit(testInfo, audit);
});

test("SEC source-probe canary crosses the complete worker lifecycle", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);

  const jobId = `sol-sec-probe-${RUN_ID}`.replace(/[^A-Za-z0-9._:-]/g, "-").slice(0, 100);
  const submittedPayload = await requestJson(page, "/library/jobs", {
    method: "POST",
    body: {
      title: `Sol SEC source-probe ${RUN_ID}`,
      request: { job_id: jobId, idempotency_key: jobId, canary: true, review_lane: "sol/live-review" },
      plan: { job_type: "source_probe", url: CANARY_URL, title: "SEC company tickers probe", launchable: true },
      auto_approve: false,
    },
  });
  let job = submittedPayload.job || submittedPayload;
  record("Job lifecycle", "Create pending-approval canary", job.status === "pending_approval" ? "pass" : "fail", {
    job_id: job.id,
    job_status: job.status,
  });
  await capture(page, testInfo, "job-pending");

  const approvedPayload = await requestJson(page, `/library/jobs/${encodeURIComponent(job.id)}/approve`, {
    method: "POST",
    body: {},
  });
  job = approvedPayload.job || approvedPayload;
  record("Job lifecycle", "Approve exact pending canary", ["queued", "running", "completed"].includes(job.status) ? "pass" : "fail", {
    job_id: job.id,
    job_status: job.status,
  });

  job = await pollJob(page, job.id);
  record("Job lifecycle", "Worker reaches completion", job?.status === "completed" ? "pass" : "fail", {
    job_id: job?.id || jobId,
    job_status: job?.status || "unknown",
    error: job?.error || "",
    connector_id: job?.result?.connector_id || "",
    run_id: job?.run_id || job?.execution?.run_id || "",
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "job-completed");
  await attachAudit(testInfo, audit);
});

test("Profile suggestion handoff is recorded as a product failure", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);

  const action = page.getByRole("button", { name: /Search →|Link →|Open →/ }).first();
  if (!(await action.isVisible().catch(() => false))) {
    record("Profile", "Carry research suggestion into Discover", "fail", { reason: "No action visible" });
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
  await capture(page, testInfo, "profile-handoff-result");
  await attachAudit(testInfo, audit);
});
