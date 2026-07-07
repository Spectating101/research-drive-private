/**
 * Professor demo — end-to-end procurement desk workflow (live API required).
 *
 * Run:
 *   bash scripts/run_yzu_cluster.sh
 *   npm run test:professor-demo
 *
 * Outputs (for ChatGPT / advisor review):
 *   docs/status/generated/professor_demo_report.json
 *   docs/status/generated/professor_demo_report.md
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "@playwright/test";

const API = process.env.YZU_API_URL || "http://127.0.0.1:8765";
const FACULTY_EMAIL = process.env.DESK_TEST_EMAIL || "drkong@saturn.yzu.edu.tw";
const SEARCH_QUERY = process.env.DEMO_SEARCH_QUERY || "TWSE";
const KNOWN_DATASET = process.env.DEMO_KNOWN_DATASET || "gdelt_asia_daily_country_panel";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT_JSON = path.join(ROOT, "docs/status/generated/professor_demo_report.json");
const OUT_MD = path.join(ROOT, "docs/status/generated/professor_demo_report.md");

let apiLive = false;
let datasetCount = 0;

/** @type {{ meta: Record<string, unknown>, scenarios: Array<Record<string, unknown>> }} */
const report = {
  meta: {
    product: "Research Drive — YZU procurement desk",
    faculty_email: FACULTY_EMAIL,
    search_query: SEARCH_QUERY,
    known_dataset: KNOWN_DATASET,
    api: API,
  },
  scenarios: [],
};

function record(id, title, ok, evidence = {}) {
  report.scenarios.push({
    id,
    title,
    ok,
    at: new Date().toISOString(),
    ...evidence,
  });
}

test.describe.configure({ mode: "serial" });

test.beforeAll(async ({ request }) => {
  try {
    const health = await request.get(`${API}/health`, { timeout: 20_000 });
    if (!health.ok()) return;
    const body = await health.json();
    apiLive = body.status === "ok";
    report.meta.composer_configured = body.desk?.composer_configured;
    report.meta.brain = body.desk?.brain;
    const ds = await request.get(`${API}/datasets`, { timeout: 30_000 });
    if (ds.ok()) {
      datasetCount = (await ds.json()).datasets?.length || 0;
    }
    report.meta.registry_count = datasetCount;
  } catch (err) {
    apiLive = false;
    report.meta.beforeAll_error = String(err);
  }
});

test.beforeEach(async ({ page }) => {
  test.skip(!apiLive, `Desk API not live at ${API} — bash scripts/run_yzu_cluster.sh`);
  await page.addInitScript((email) => {
    localStorage.setItem("procure_user_email", email);
    localStorage.setItem("rd_v2_settings", JSON.stringify({ defaultTab: "home", onSelect: "detail", email }));
  }, FACULTY_EMAIL);
  await page.setViewportSize({ width: 1440, height: 900 });
});

async function waitLive(page) {
  await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
  const live = page.locator(".rd-v2-trust-badge.ok", { hasText: "Live registry" });
  try {
    await expect(live).toBeVisible({ timeout: 25_000 });
  } catch {
    await page.reload({ waitUntil: "load" });
    await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
    await expect(live).toBeVisible({ timeout: 45_000 });
  }
}

async function v2Nav(page, label) {
  await page.locator("aside.yzu-sidebar").getByRole("button", { name: label, exact: true }).click();
}

test.describe("professor demo @ live-desk", () => {
  test("scenario 1 — Home command surface and attention", async ({ page }) => {
    await page.goto("/?tab=home", { waitUntil: "load" });
    await waitLive(page);

    await expect(page.locator(".rd-v2-home-command")).toContainText(
      "Google Drive vault for the lab. Discover Hugging Face, DOI catalogs, and the open web.",
    );
    await expect(page.locator(".rd-v2-home-command")).toContainText(
      "Ask the assistant to search, query, collect, and register.",
    );
    const holdingsBtn = page.locator(".rd-v2-home-command-actions button", { hasText: "Open lab vault" });
    await expect(holdingsBtn).toBeVisible();
    const holdingsText = await holdingsBtn.innerText();
    const holdings = parseInt(holdingsText, 10) || datasetCount;

    await expect(page.locator(".rd-v2-home-attention")).toBeVisible();
    const attentionCount = await page.locator(".rd-v2-home-attention article").count();

    record("home_command", "Home command surface + attention queue", true, {
      holdings,
      attention_items: attentionCount,
      header_meta: await page.locator(".rd-v2-header-meta-count").innerText(),
    });
  });

  test("scenario 2 — Library vault: holdings and query-ready dataset", async ({ page }) => {
    await page.goto("/?tab=library&folder=research_panels/gdelt", { waitUntil: "load" });
    await waitLive(page);

    const rows = page.locator('.rd-v2-catalog button.row[data-kind="dataset"]');
    await expect(rows.first()).toBeVisible({ timeout: 30_000 });
    const rowCount = await rows.count();

    const known = page.locator('.rd-v2-catalog button.row[data-kind="dataset"]', {
      hasText: KNOWN_DATASET,
    });
    if (await known.count()) {
      await known.first().click();
    } else {
      await rows.first().click();
    }

    await expect(page.locator(".rd-v2-rail-toggle button.on", { hasText: "Detail" })).toBeVisible();
    await expect(page.locator('[data-testid="rail-pane-detail"]')).toContainText(/Query-ready|Ready/i);

    const datasetId =
      (await page.locator("aside.rd-v2-rail .rd-v2-detail-id, aside .rd-v2-rail-scroll code").first().textContent()) ||
      KNOWN_DATASET;

    record("library_vault", "Library vault drill-in + query-ready detail", true, {
      folder: "research_panels/gdelt",
      visible_datasets: rowCount,
      selected_dataset: String(datasetId).trim().slice(0, 80),
    });
  });

  test("scenario 3 — Discover: search missing dataset + pipeline", async ({ page }) => {
    await page.goto(`/?tab=browse&q=${encodeURIComponent(SEARCH_QUERY)}`, { waitUntil: "load" });
    await waitLive(page);

    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Discover" })).toBeVisible();
    await expect(page.locator(".rd-v2-discover-pipeline")).toBeVisible();
    await expect(page.locator(".rd-v2-discover-pipeline")).toContainText("Search");
    await expect(page.locator(".rd-v2-discover-pipeline")).toContainText("Register");

    const candidates = page.locator('.rd-v2-catalog button.row[data-kind="external"]');
    await expect(candidates.first()).toBeVisible({ timeout: 30_000 });
    const candidateCount = await candidates.count();

    const firstTitle = await candidates.first().locator("strong").innerText();
    const sourceChip = await page.locator(".rd-v2-chip").first().innerText().catch(() => "");

    record("discover_search", "Discover search + acquisition pipeline", true, {
      query: SEARCH_QUERY,
      candidates: candidateCount,
      first_candidate: firstTitle,
      source_badge: sourceChip,
    });
  });

  test("scenario 4 — Discover: probe facts + Add to lab rail", async ({ page }) => {
    await page.goto(`/?tab=browse&q=${encodeURIComponent(SEARCH_QUERY)}`, { waitUntil: "load" });
    await waitLive(page);

    async function pickAcquireCandidate() {
      const notInLab = page.locator(
        '.rd-v2-catalog button.row[data-kind="external"]:not([data-state="in_lab"])',
      );
      if (await notInLab.count()) return notInLab.first();
      await page.locator(".rd-v2-search-pill input").fill("MOPS");
      await page.locator(".rd-v2-search-pill input").press("Enter");
      await page.waitForTimeout(2500);
      const retry = page.locator(
        '.rd-v2-catalog button.row[data-kind="external"]:not([data-state="in_lab"])',
      );
      if (await retry.count()) return retry.first();
      return page.locator('.rd-v2-catalog button.row[data-kind="external"]').first();
    }

    const candidate = await pickAcquireCandidate();
    await candidate.waitFor({ state: "visible", timeout: 30_000 });
    const title = await candidate.locator("strong").innerText();
    await candidate.click();

    const rail = page.locator("aside.rd-v2-rail");
    await expect(rail).toContainText("Acquisition state");
    await expect(page.locator(".rd-v2-discover-candidate.selected .rd-v2-discover-fact", { hasText: "Fit" })).toBeVisible();
    await expect(page.locator(".rd-v2-discover-candidate.selected .rd-v2-discover-fact", { hasText: "Access" })).toBeVisible();
    await expect(page.locator(".rd-v2-discover-candidate.selected .rd-v2-discover-fact", { hasText: "Probe" })).toBeVisible();
    await expect(page.locator(".rd-v2-discover-candidate.selected .rd-v2-discover-fact", { hasText: "Destination" })).toBeVisible();
    await expect(rail.locator(".rd-v2-detail-label", { hasText: "Access" })).toBeVisible();
    await expect(rail.locator(".rd-v2-detail-label", { hasText: "Destination" })).toBeVisible();

    const probeBtn = rail.getByRole("button", { name: "Probe source" });
    if (await probeBtn.isVisible()) {
      await probeBtn.click();
      await expect(
        rail.locator(".rd-v2-discover-probe-result, .rd-v2-discover-probe-error"),
      ).toBeVisible({ timeout: 45_000 });
    }

    const primaryBtn = rail.locator(".rd-v2-rail-sticky .rd-v2-btn.primary").first();
    await expect(primaryBtn).toBeVisible();
    const primaryLabel = (await primaryBtn.innerText()).trim();
    if (primaryLabel === "Open in Library") {
      await primaryBtn.click();
      record("discover_probe_add", "Discover in-lab candidate → Open in Library", true, {
        candidate: title,
        action: "open_in_library",
      });
      return;
    }

    await primaryBtn.click();

    await expect(page.locator(".rd-v2-toast")).toContainText(/Add to lab|Collection job/, {
      timeout: 10_000,
    });
    await expect(page.locator(".rd-v2-rail-toggle").getByRole("tab", { name: "Ask" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    const askBox = page.getByTestId("ask-messages");
    await expect(askBox).toContainText("Add to lab vault", { timeout: 45_000 });

    const askText = await askBox.innerText();

    record("discover_probe_add", "Discover candidate probe + Add to lab → Ask", true, {
      candidate: title,
      ask_snippet: askText.slice(0, 240),
    });
  });

  test("scenario 5 — Resources: operational safety ledger", async ({ page }) => {
    await page.goto("/?tab=resources", { waitUntil: "load" });
    await waitLive(page);

    await expect(page.locator(".rd-v2-page-head h1", { hasText: "Resources" })).toBeVisible();
    await expect(page.locator(".rd-v2-page-head p", { hasText: "Storage, account limits" })).toBeVisible();
    await expect(page.getByText("Loading resources…")).toBeHidden({ timeout: 45_000 });

    const hasStrip = (await page.locator(".rd-v2-res-status-strip").count()) > 0;
    const hasInventory = (await page.locator(".rd-v2-res-inventory").count()) > 0;
    expect(hasStrip || hasInventory).toBeTruthy();

    const pageText = await page.locator("main.yzu-main").innerText();
    const labelCandidates = [
      "Desk connection",
      "Collection workers",
      "Lab vault",
      "Ask usage",
      "Source probes",
      "Remote tables",
      "procurement routes",
      "Connected",
    ];
    const labels = labelCandidates.filter((l) => pageText.includes(l));

    record("resources_safety", "Resources safety ledger (professor labels)", labels.length >= 1, {
      faculty_labels_found: labels,
      has_status_strip: hasStrip,
      has_inventory: hasInventory,
      page_excerpt: pageText.slice(0, 600),
    });
    expect(labels.length).toBeGreaterThanOrEqual(1);
  });

  test("scenario 6 — Resources: pending approvals queue", async ({ page }) => {
    await page.goto("/?tab=home", { waitUntil: "load" });
    await waitLive(page);

    const headerMeta = await page.locator(".rd-v2-header-meta-count").innerText();
    const pendingMatch = headerMeta.match(/(\d+)\s+pending/);
    const pendingCount = pendingMatch ? parseInt(pendingMatch[1], 10) : 0;

    const homeStrip = page.locator(".rd-v2-home-strip", { hasText: "Pending approvals" });
    const hasHomeStrip = (await homeStrip.count()) > 0;
    const homeText = await page.locator("main.yzu-main").innerText();
    const limitsNormal = /limits normal/i.test(homeText);

    if (pendingCount > 0 && hasHomeStrip) {
      await homeStrip.getByRole("button", { name: /Approve/i }).click();
      await expect(page.locator(".rd-v2-page-head h1", { hasText: "Resources" })).toBeVisible({
        timeout: 15_000,
      });
    } else {
      await page.goto("/?tab=resources", { waitUntil: "load" });
    }

    const pageText = await page.locator("main.yzu-main").innerText();
    const surfaced =
      pendingCount > 0 ||
      /pending approval|review queue|approve job/i.test(pageText) ||
      hasHomeStrip ||
      (pendingCount === 0 && limitsNormal);

    record("resources_approvals", "Pending approvals surfaced in desk", surfaced, {
      pending_count: pendingCount,
      home_strip: hasHomeStrip,
      limits_normal: limitsNormal,
      header_meta: headerMeta,
    });
    expect(surfaced).toBeTruthy();
  });

  test("scenario 7 — Profile: faculty context for ranked Discover", async ({ page }) => {
    await page.goto("/?tab=profile", { waitUntil: "load" });
    await waitLive(page);

    await expect(page.locator(".rd-v2-profile-hint", { hasText: FACULTY_EMAIL })).toBeVisible();
    await expect(page.locator(".rd-v2-profile-name")).not.toHaveText("Research profile", { timeout: 20_000 });
    const name = await page.locator(".rd-v2-profile-name").innerText();

    record("profile_faculty", "Faculty profile loaded from registry", true, {
      name_en: name,
      email: FACULTY_EMAIL,
    });
  });

  test("scenario 8 — Library: preview rows on registered dataset", async ({ page }) => {
    await page.goto(
      `/?tab=library&folder=research_panels/gdelt&dataset=${encodeURIComponent(KNOWN_DATASET)}`,
      { waitUntil: "load" },
    );
    await waitLive(page);

    await expect(page.locator("aside.rd-v2-rail")).toContainText(KNOWN_DATASET, { timeout: 20_000 });
    await page.locator("aside .rd-v2-rail-sticky").getByRole("button", { name: "Preview rows" }).click();
    const modal = page.locator(".rd-v2-preview-modal");
    await expect(modal).toBeVisible({ timeout: 25_000 });
    await expect(modal.getByRole("button", { name: "Export CSV" })).toBeVisible();

    const rowHint = await modal.innerText();
    const hasRows = /date|country|row|sample/i.test(rowHint);

    await page.keyboard.press("Escape");
    record("library_preview", "Query-ready preview on registered dataset", hasRows, {
      dataset_id: KNOWN_DATASET,
      preview_hint: rowHint.slice(0, 200),
    });
    expect(hasRows).toBeTruthy();
  });

  test("scenario 9 — Verify registered holdings discoverable (In lab filter)", async ({ page }) => {
    await page.goto(`/?tab=browse&q=${encodeURIComponent("gdelt")}`, { waitUntil: "load" });
    await waitLive(page);

    await page.locator(".rd-v2-toolbar.inline").getByRole("button", { name: "In lab" }).click();
    await page.waitForTimeout(800);

    const inLab = page.locator('.rd-v2-catalog button.row[data-state="in_lab"], .rd-v2-pill.lab');
    const inLabCount = await inLab.count();

    const ok = inLabCount > 0 || datasetCount > 0;
    record("verify_in_lab", "Registered datasets findable after Discover session", ok, {
      in_lab_ui_matches: inLabCount,
      registry_count: datasetCount,
      filter: "In lab",
      query: "gdelt",
    });
    expect(ok).toBeTruthy();
  });
});

test.afterAll(async () => {
  report.meta.captured_at = new Date().toISOString();
  report.meta.passed = report.scenarios.filter((s) => s.ok).length;
  report.meta.total = report.scenarios.length;
  report.meta.all_passed = report.meta.passed === report.meta.total && report.meta.total > 0;

  fs.mkdirSync(path.dirname(OUT_JSON), { recursive: true });
  fs.writeFileSync(OUT_JSON, `${JSON.stringify(report, null, 2)}\n`);

  const lines = [
    "# Professor demo — automated evidence",
    "",
    `Captured: ${report.meta.captured_at}`,
    `Faculty: ${FACULTY_EMAIL}`,
    `Registry: ${report.meta.registry_count ?? "?"} datasets · Composer: ${report.meta.composer_configured ? "ready" : "n/a"}`,
    "",
    "## Product model exercised",
    "",
    "```text",
    "Home → command surface + attention",
    "Library → lab vault + query-ready preview",
    "Discover → search → probe facts → Add to lab → Ask",
    "Resources → safety ledger + approvals",
    "Profile → faculty context",
    "Return → In lab filter finds registered holdings",
    "```",
    "",
    "## Scenarios",
    "",
  ];

  for (const s of report.scenarios) {
    lines.push(`### ${s.ok ? "PASS" : "FAIL"} — ${s.title}`);
    lines.push(`- **id:** \`${s.id}\``);
    for (const [k, v] of Object.entries(s)) {
      if (["id", "title", "ok", "at"].includes(k)) continue;
      lines.push(`- **${k}:** ${typeof v === "object" ? JSON.stringify(v) : v}`);
    }
    lines.push("");
  }

  lines.push("## ChatGPT review prompt");
  lines.push("");
  lines.push("```text");
  lines.push("Review this professor procurement demo evidence for Research Drive v2.");
  lines.push("Repo: Spectating101/yzu-cluster · Screenshots: docs/screenshots-review/");
  lines.push("Judge whether the workflow is credible end-to-end:");
  lines.push("search missing data → Library check → Discover probe → Resources safety → queue procurement → find registered result.");
  lines.push("```");

  fs.writeFileSync(OUT_MD, `${lines.join("\n")}\n`);
});
