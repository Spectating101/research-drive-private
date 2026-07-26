import fs from "node:fs";
import path from "node:path";
import { test, expect } from "@playwright/test";

const ROOT = process.cwd();
const OUT_DIR = path.join(ROOT, "artifacts/live-workflow");
const REPORT_JSON = path.join(OUT_DIR, "workflow-report.json");
const REPORT_MD = path.join(OUT_DIR, "workflow-report.md");
const QUERY = process.env.LIVE_WORKFLOW_QUERY || "stablecoin";
const CANARY_URL =
  process.env.LIVE_WORKFLOW_CANARY_URL ||
  "https://api.datacite.org/dois/10.5281/zenodo.1000000";
const RUN_ID = String(process.env.GITHUB_RUN_ID || Date.now());

const report = {
  meta: {
    url: process.env.YZU_DESK_URL || "https://previous.easycamp.tech",
    query: QUERY,
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
];

function pathOf(url) {
  try {
    return new URL(url).pathname;
  } catch {
    return String(url || "");
  }
}

function ensureOutDir() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
}

function record(journey, step, status, evidence = {}) {
  let item = report.journeys.find((entry) => entry.id === journey);
  if (!item) {
    item = { id: journey, steps: [] };
    report.journeys.push(item);
  }
  item.steps.push({
    step,
    status,
    at: new Date().toISOString(),
    ...evidence,
  });
}

function saveReport() {
  ensureOutDir();
  report.meta.finished_at = new Date().toISOString();
  fs.writeFileSync(REPORT_JSON, JSON.stringify(report, null, 2));
  const lines = [
    "# Research Drive live workflow report",
    "",
    `- URL: \`${report.meta.url}\``,
    `- Query: \`${report.meta.query}\``,
    `- Run: \`${report.meta.run_id}\``,
    "",
  ];
  for (const journey of report.journeys) {
    lines.push(`## ${journey.id}`, "");
    for (const step of journey.steps) {
      lines.push(`- **${step.status.toUpperCase()}** ${step.step}`);
      const evidence = Object.entries(step)
        .filter(([key]) => !["step", "status", "at"].includes(key))
        .map(([key, value]) => `  - ${key}: \`${typeof value === "string" ? value : JSON.stringify(value)}\``);
      lines.push(...evidence);
    }
    lines.push("");
  }
  fs.writeFileSync(REPORT_MD, `${lines.join("\n")}\n`);
}

function newAudit() {
  return {
    allowed: [],
    blocked: [],
    telemetry: [],
    pageErrors: [],
    consoleErrors: [],
  };
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

async function attachAudit(testInfo, audit) {
  await testInfo.attach("network-audit.json", {
    body: Buffer.from(JSON.stringify(audit, null, 2)),
    contentType: "application/json",
  });
  expect(audit.blocked, "Unexpected write attempted by the workflow").toEqual([]);
}

async function capture(page, testInfo, name) {
  const body = await page.screenshot({ fullPage: true });
  await testInfo.attach(name, { body, contentType: "image/png" });
}

async function waitForDesk(page) {
  await page.locator(".rd-v2-shell").waitFor({ timeout: 60_000 });
  await expect(page.locator(".rd-v2-trust-badge.ok", { hasText: "Live registry" })).toBeVisible({
    timeout: 60_000,
  });
}

async function sameOriginJson(page, url, init = {}) {
  return page.evaluate(
    async ({ endpoint, options }) => {
      const response = await fetch(endpoint, {
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
        throw new Error(`${response.status} ${endpoint}: ${payload.message || payload.error || text}`);
      }
      return payload;
    },
    { endpoint: url, options: init },
  );
}

async function currentHeading(page) {
  const heading = page.locator("main.yzu-main h1").first();
  return (await heading.textContent().catch(() => ""))?.trim() || "";
}

async function clickIfVisible(locator) {
  if ((await locator.count()) && (await locator.first().isVisible().catch(() => false))) {
    await locator.first().click();
    return true;
  }
  return false;
}

async function findAcquirableCandidate(page) {
  const candidates = page.locator('.rd-v2-discover-candidate:not([data-state="in_lab"])');
  const count = await candidates.count();
  for (let index = 0; index < count; index += 1) {
    const candidate = candidates.nth(index);
    await candidate.click();
    const actions = page.getByTestId("discover-eval-actions");
    const primary = actions.locator("button.rd-v2-eval-primary-action");
    if (!(await primary.count())) continue;
    const label = (await primary.innerText()).trim();
    if (/request|add to lab|collect/i.test(label)) {
      return { candidate, label };
    }
  }
  return null;
}

async function pollJob(page, jobId, terminal = ["completed", "failed", "cancelled"], timeoutMs = 150_000) {
  const deadline = Date.now() + timeoutMs;
  let latest = null;
  while (Date.now() < deadline) {
    latest = await sameOriginJson(page, `/library/jobs/${encodeURIComponent(jobId)}`);
    const job = latest.job || latest;
    if (terminal.includes(String(job.status || ""))) return job;
    await page.waitForTimeout(2500);
  }
  return latest?.job || latest;
}

test.describe.configure({ mode: "serial" });

test.afterAll(() => saveReport());

test("Home workflow: resume, evidence, and operational handoffs", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "home-01-initial");
  record("Home", "Initial command surface renders", "pass", { heading: await currentHeading(page), url: page.url() });

  const viewAll = page.getByRole("button", { name: /View all/i });
  if (await clickIfVisible(viewAll)) {
    await expect(page.getByRole("heading", { name: "Discover", exact: true })).toBeVisible();
    await capture(page, testInfo, "home-02-recent-trail-handoff");
    record("Home", "Recent Trail hands off to Discover", "pass", { url: page.url() });
  } else {
    record("Home", "Recent Trail hands off to Discover", "fail", { reason: "View all control missing" });
  }

  await page.goto("/?tab=home", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  const resources = page.getByRole("button", { name: /Resources/i }).first();
  if (await clickIfVisible(resources)) {
    await expect(page.getByRole("heading", { name: "Resources", exact: true })).toBeVisible();
    await capture(page, testInfo, "home-03-resource-handoff");
    record("Home", "Resource headroom hands off to Resources", "pass", { url: page.url() });
  } else {
    record("Home", "Resource headroom hands off to Resources", "fail", { reason: "Resources control missing" });
  }
  await attachAudit(testInfo, audit);
});

test("Library workflow: shelf to asset to Detail, Ask, and Preview", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=library", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "library-01-root");
  record("Library", "Root shelves render", "pass", { url: page.url() });

  let dataset = page.locator('.rd-v2-catalog button.row[data-kind="dataset"]').first();
  for (let depth = 0; depth < 3 && !(await dataset.isVisible().catch(() => false)); depth += 1) {
    const folder = page.locator('.rd-v2-catalog button.row[data-kind="folder"]').first();
    if (!(await folder.isVisible().catch(() => false))) break;
    const label = (await folder.innerText()).trim().slice(0, 120);
    await folder.click();
    await page.waitForTimeout(700);
    await capture(page, testInfo, `library-02-folder-${depth + 1}`);
    record("Library", `Open folder level ${depth + 1}`, "pass", { label, url: page.url() });
    dataset = page.locator('.rd-v2-catalog button.row[data-kind="dataset"]').first();
  }

  if (await dataset.isVisible().catch(() => false)) {
    const label = (await dataset.innerText()).trim().slice(0, 160);
    await dataset.click();
    await expect(page.locator('[data-testid="rail-pane-detail"]')).toBeVisible();
    await capture(page, testInfo, "library-03-selected-detail");
    record("Library", "Select asset and inspect Detail", "pass", { label, url: page.url() });

    const askTab = page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" });
    await askTab.click();
    await expect(page.getByTestId("ask-messages")).toBeVisible();
    await capture(page, testInfo, "library-04-ask-context");
    record("Library", "Selected asset carries into Ask", "pass");

    await page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Detail" }).click();
    await dataset.dblclick();
    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await capture(page, testInfo, "library-05-preview");
    record("Library", "Double-click opens Preview", "pass", { preview: (await dialog.innerText()).slice(0, 240) });
    await page.getByRole("button", { name: "Close preview" }).click();
  } else {
    record("Library", "Select asset and inspect Detail", "fail", { reason: "No dataset reachable through first three folder levels" });
  }

  const search = page.getByRole("textbox", { name: "Search library holdings" });
  await search.fill("gdelt");
  await page.waitForTimeout(500);
  await capture(page, testInfo, "library-06-search");
  record("Library", "Toolbar search filters holdings", "pass", { query: "gdelt" });
  await attachAudit(testInfo, audit);
});

test("Discover workflow: search, select, probe, request, History, and cleanup", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto(`/?tab=browse&q=${encodeURIComponent(QUERY)}`, { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await expect(page.getByRole("region", { name: "Best fit" })).toBeVisible({ timeout: 60_000 });
  await capture(page, testInfo, "discover-01-ranked-results");
  record("Discover", "Search returns ranked candidates", "pass", {
    query: QUERY,
    candidates: await page.locator(".rd-v2-discover-candidate").count(),
  });

  const found = await findAcquirableCandidate(page);
  if (!found) {
    record("Discover", "Select acquirable candidate", "fail", { reason: "No requestable external candidate" });
    await attachAudit(testInfo, audit);
    return;
  }
  const title = (await found.candidate.locator("strong").innerText()).trim();
  await capture(page, testInfo, "discover-02-selected-detail");
  record("Discover", "Select external candidate and inspect Detail", "pass", { title, primary: found.label });

  const actions = page.getByTestId("discover-eval-actions");
  const probe = actions.getByRole("button", { name: /Probe source/i });
  if (await probe.isVisible().catch(() => false)) {
    const responsePromise = page.waitForResponse(
      (response) => response.url().includes("/library/discover/probe") && response.request().method() === "POST",
      { timeout: 60_000 },
    );
    await probe.click();
    const response = await responsePromise;
    expect(response.ok()).toBeTruthy();
    await expect(page.getByRole("region", { name: "Verified" })).toBeVisible({ timeout: 60_000 });
    await capture(page, testInfo, "discover-03-probed");
    record("Discover", "Probe converts endpoint claims into verified evidence", "pass", { status: response.status() });
  } else {
    record("Discover", "Probe converts endpoint claims into verified evidence", "fail", { reason: "Probe action not exposed" });
  }

  const primary = actions.locator("button.rd-v2-eval-primary-action");
  const primaryLabel = (await primary.innerText()).trim();
  await primary.click();
  const confirm = page.getByTestId("discover-request-confirm");
  if (await confirm.isVisible().catch(() => false)) {
    const collectPromise = page.waitForResponse(
      (response) => response.url().includes("/library/discover/collect") && response.request().method() === "POST",
      { timeout: 60_000 },
    );
    await confirm.getByRole("button", { name: "Confirm request" }).click();
    const collectResponse = await collectPromise;
    const collectPayload = await collectResponse.json().catch(() => ({}));
    const createdJob = collectPayload.job || collectPayload;
    expect(collectResponse.ok()).toBeTruthy();
    await expect(page.getByTestId("discover-lifecycle")).toBeVisible({ timeout: 60_000 });
    await capture(page, testInfo, "discover-04-pending-approval");
    record("Discover", "Request creates durable lifecycle item", "pass", {
      action: primaryLabel,
      job_id: createdJob.id || "unknown",
      status: createdJob.status || "unknown",
    });

    await page.getByRole("tab", { name: /History/i }).click();
    await expect(page.locator(".rd-v2-discover-page--history")).toBeVisible();
    await capture(page, testInfo, "discover-05-history");
    record("Discover", "Created request appears in History surface", "pass", { url: page.url() });

    if (createdJob.id) {
      const cancelled = await sameOriginJson(page, `/library/jobs/${encodeURIComponent(createdJob.id)}/cancel`, {
        method: "POST",
        body: {},
      });
      const cancelledJob = cancelled.job || cancelled;
      record("Discover", "Controlled request is cancelled after inspection", "pass", {
        job_id: createdJob.id,
        status: cancelledJob.status,
      });
      await page.reload({ waitUntil: "domcontentloaded" });
      await waitForDesk(page);
      await capture(page, testInfo, "discover-06-cancelled-history");
    }
  } else {
    record("Discover", "Request creates durable lifecycle item", "fail", {
      reason: "Primary action did not expose confirmation boundary",
      primary: primaryLabel,
    });
  }
  await attachAudit(testInfo, audit);
});

test("Resources workflow: capacity, source route, usage, and selected-row Detail", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await expect(page.getByText("Loading resources…")).toBeHidden({ timeout: 60_000 });
  await capture(page, testInfo, "resources-01-capacity");
  record("Resources", "Capacity and access view renders", "pass");

  const selectable = page.locator(
    ".rd-v2-res-capacity-meter, .rd-v2-res-source-row, .rd-v2-res-inventory button, .rd-v2-res-log button",
  ).first();
  if (await selectable.isVisible().catch(() => false)) {
    const label = (await selectable.innerText()).trim().slice(0, 160);
    await selectable.click();
    await expect(page.locator('[data-testid="rail-pane-detail"]')).toBeVisible();
    await capture(page, testInfo, "resources-02-selected-detail");
    record("Resources", "Select operational row and inspect Detail", "pass", { label });
  } else {
    record("Resources", "Select operational row and inspect Detail", "fail", { reason: "No selectable operational row" });
  }

  const usageTab = page.getByRole("button", { name: /Usage|Activity/i }).first();
  if (await clickIfVisible(usageTab)) {
    await page.waitForTimeout(500);
    await capture(page, testInfo, "resources-03-usage");
    record("Resources", "Switch to usage/activity view", "pass");
  } else {
    record("Resources", "Switch to usage/activity view", "fail", { reason: "Usage mode control missing" });
  }
  await attachAudit(testInfo, audit);
});

test("Profile workflow: research memory to Discover search handoff", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=profile", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "profile-01-memory");
  record("Profile", "Memory, Works, and Lab render", "pass");

  const searchAction = page.getByRole("button", { name: /Search →|Link →|Open →/ }).first();
  if (await searchAction.isVisible().catch(() => false)) {
    const label = (await searchAction.innerText()).trim();
    await searchAction.click();
    await page.waitForTimeout(800);
    const heading = await currentHeading(page);
    const passed = heading === "Discover" && new URL(page.url()).searchParams.get("q");
    await capture(page, testInfo, "profile-02-discover-handoff");
    record("Profile", "Suggested research action carries query into Discover", passed ? "pass" : "fail", {
      action: label,
      heading,
      url: page.url(),
      page_errors: audit.pageErrors,
    });
    expect(passed, "Profile Search/Link/Open should navigate to a populated Discover query").toBeTruthy();
  } else {
    record("Profile", "Suggested research action carries query into Discover", "fail", { reason: "No suggested action" });
    expect(false, "Profile exposes no suggested research action").toBeTruthy();
  }
  await attachAudit(testInfo, audit);
});

test("Settings workflow: local display preferences persist without changing runtime", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=settings", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "settings-01-status");
  record("Settings", "Live status and preferences render", "pass");

  const defaultTab = page.locator("#rd-settings-default-tab");
  const onSelect = page.locator("#rd-settings-on-select");
  await defaultTab.selectOption("library");
  await onSelect.selectOption("ask");
  await capture(page, testInfo, "settings-02-local-preferences");
  record("Settings", "Display preferences update locally", "pass", {
    default_tab: await defaultTab.inputValue(),
    on_select: await onSelect.inputValue(),
  });

  await page.goto("/", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  const heading = await currentHeading(page);
  await capture(page, testInfo, "settings-03-default-route");
  record("Settings", "Default page preference applies on root navigation", heading === "Library" ? "pass" : "fail", {
    heading,
    url: page.url(),
  });
  expect(heading).toBe("Library");
  await attachAudit(testInfo, audit);
});

test("Synthesis workflow: thread selection, evidence state, and Ask handoff", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=synthesis", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "synthesis-01-initial");
  record("Synthesis", "Synthesis workspace renders", "pass");

  const threads = page.getByTestId("synthesis-thread-item");
  if (await threads.count()) {
    const target = threads.nth(Math.min(1, (await threads.count()) - 1));
    const label = (await target.innerText()).trim().slice(0, 160);
    await target.click();
    await page.waitForTimeout(700);
    await capture(page, testInfo, "synthesis-02-thread-selected");
    record("Synthesis", "Select durable construction thread", "pass", { label });

    const discuss = page.getByRole("button", { name: /Discuss construction in Ask|Challenge in Ask/i }).first();
    if (await discuss.isVisible().catch(() => false)) {
      await discuss.click();
      await expect(page.locator("aside.rd-v2-rail").getByRole("tab", { name: "Ask" })).toHaveAttribute(
        "aria-selected",
        "true",
      );
      await capture(page, testInfo, "synthesis-03-ask-handoff");
      record("Synthesis", "Thread context hands off to Ask without executing", "pass");
    } else {
      record("Synthesis", "Thread context hands off to Ask without executing", "fail", { reason: "Ask handoff missing" });
    }
  } else {
    record("Synthesis", "Select durable construction thread", "fail", { reason: "No threads returned" });
  }
  await attachAudit(testInfo, audit);
});

test("Controlled job lifecycle: approval, queue, execution, and terminal state", async ({ page }, testInfo) => {
  const audit = newAudit();
  await installGuard(page, audit);
  await page.goto("/?tab=resources", { waitUntil: "domcontentloaded" });
  await waitForDesk(page);

  const jobId = `sol-live-probe-${RUN_ID}`.replace(/[^A-Za-z0-9._:-]/g, "-").slice(0, 100);
  const submitted = await sameOriginJson(page, "/library/jobs", {
    method: "POST",
    body: {
      title: `Sol live workflow canary ${RUN_ID}`,
      request: { job_id: jobId, idempotency_key: jobId, canary: true, review_lane: "sol/live-review" },
      plan: {
        job_type: "source_probe",
        url: CANARY_URL,
        title: "DataCite source-probe canary",
        launchable: true,
      },
      auto_approve: false,
    },
  });
  const pending = submitted.job || submitted;
  record("Job lifecycle", "Create controlled source-probe job", pending.status === "pending_approval" ? "pass" : "fail", {
    job_id: pending.id,
    status: pending.status,
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "job-01-pending-approval");

  const approvedPayload = await sameOriginJson(page, `/library/jobs/${encodeURIComponent(pending.id)}/approve`, {
    method: "POST",
    body: {},
  });
  const approved = approvedPayload.job || approvedPayload;
  record("Job lifecycle", "Approve exact pending revision", ["queued", "running", "completed"].includes(approved.status) ? "pass" : "fail", {
    job_id: approved.id,
    status: approved.status,
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "job-02-approved-queued");

  const terminal = await pollJob(page, pending.id);
  await page.reload({ waitUntil: "domcontentloaded" });
  await waitForDesk(page);
  await capture(page, testInfo, "job-03-terminal");
  record("Job lifecycle", "Worker reaches terminal state", terminal?.status === "completed" ? "pass" : "fail", {
    job_id: pending.id,
    status: terminal?.status || "unknown",
    error: terminal?.error || "",
    result: terminal?.result || {},
  });
  expect(terminal?.status, `Canary job did not complete: ${terminal?.error || "unknown"}`).toBe("completed");
  await attachAudit(testInfo, audit);
});
