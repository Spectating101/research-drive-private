/** Shared Playwright API mocks for Research Drive v2. */

import { MOCK_RESOURCES_ROLLUP } from "./mockResourcesRollup.js";

export const MOCK_DATASETS = {
  datasets: [
    {
      dataset_id: "gdelt_asia_daily_country_panel",
      name: "Asia daily news-risk panel",
      grain: "country-day",
      analysis_readiness: "instant",
      local_root: "research_panels/gdelt",
      source: "GDELT GKG",
      coverage: "2018–2026",
    },
    {
      dataset_id: "ticker_week_country_broadcast_panel",
      name: "Ticker week panel",
      grain: "country-week",
      analysis_readiness: "instant",
    },
  ],
};

export const MOCK_DISCOVER_HIT = {
  sections: [
    {
      title: "Registry",
      rows: [
        {
          dataset_id: "mops_financial_statements_ext",
          title: "MOPS financial statements (Taiwan)",
          source: "MOPS",
          collect_via: "mops_tw",
          url: "https://mops.twse.com.tw/example",
          coverage: "2015–2026",
          license: "Open Government",
          grain: "issuer-quarter",
          description: "TW listed company filings",
        },
      ],
    },
  ],
  total: 1,
};

export const MOCK_HEALTH = {
  status: "ok",
  datasets: 2,
  desk: {
    jobs: { running: 1, pending_approval: 1, gdelt_progress: "18 / 99 mo" },
    composer_configured: true,
    composer_model: "composer-2.5",
    mcp_tools: { total: 62, core: 13, acquire: 28, ops: 21 },
    storage_tiers: {
      canonical: { label: "GDrive vault", quota_tb: 5, used_tb: 2.1, pool_tb: 5 },
      hot: { label: "NVMe hot", used_pct: 68, free_gb: 56, headroom_ok: true },
      cache: { label: "USB bulk cache", mounted: true, used_gb: 1800, total_gb: 2000 },
    },
    gdrive: { ok: true },
    worker_pools: { busy: 2, total: 12 },
  },
};

export const MOCK_OVERVIEW = {
  total_datasets: 128,
  buckets: {
    instant_local: [
      { dataset_id: "gdelt_asia_daily_country_panel", name: "GDELT Asia", analysis_readiness: "instant" },
      { dataset_id: "ticker_week_country_broadcast_panel", name: "Ticker week", analysis_readiness: "instant" },
    ],
    remote_query: [{ dataset_id: "usdt_bigquery_catalogue", name: "USDT BQ", analysis_readiness: "dry_run" }],
    metadata_search: [{ dataset_id: "external_dataset_catalog", name: "External", analysis_readiness: "metadata_search" }],
    procurement_ops: [],
    other: [],
  },
};

export const MOCK_CATALOG_SUMMARY = {
  summary: {
    registry_datasets: 128,
    queue_tasks: 18,
    runnable_queue_tasks: 14,
    pipelines: 6,
    connectors: 3,
  },
};

export const MOCK_CLUSTER = {
  cluster: "yzu-cluster",
  controller: "optiplex",
  worker_pools: { windows_lab: { joined: 3, total: 4 } },
  disk: { free_gb: "56", used_pct: "68%" },
};

export const MOCK_OPS = {
  collection_queue: { pending: 2 },
  datacite_harvest: { running: 2, status: "warn" },
  query_engine: { ok: true },
};

export const MOCK_JOBS = {
  jobs: [
    {
      id: "job-pending-1",
      status: "pending_approval",
      type: "procure",
      plan: { title: "MOPS financial statements" },
    },
  ],
};

export const MOCK_PROBE_RESULT = {
  connector: {
    id: "example_com_data",
    connector_id: "example_com_data",
    status: "candidate",
    spec: {
      access_mode: "direct_file",
      content_type: "text/csv",
      discovered_files: [{ url: "https://example.com/data.csv" }],
    },
  },
  summary: "direct_file source; 1 downloadable links detected; recommendation: collect_manifest",
};

export const MOCK_WEB_DISCOVER = {
  query: "obscure dataset",
  sections: [
    {
      id: "web_discover",
      label: "Open web",
      rows: [
        {
          kind: "web_hit",
          title: "Example open dataset",
          url: "https://example.com/dataset",
          source: "web",
          description: "Public CSV mirror",
        },
      ],
    },
  ],
  total: 1,
  index_miss: true,
};

export async function mockV2Api(
  page,
  {
    discoverBody = { sections: [], total: 0 },
    jobsBody = MOCK_JOBS,
    chatComplete = null,
    synthesisProfiles = { profiles: [], latest: {}, count: 0 },
    synthesisDetail = { found: false },
  } = {},
) {
  await page.route("**/datasets", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_DATASETS) }),
  );
  await page.route("**/datasets/*", (route) => {
    const id = decodeURIComponent(route.request().url().split("/datasets/")[1]?.split("?")[0] || "");
    const row = MOCK_DATASETS.datasets.find((d) => d.dataset_id === id) || MOCK_DATASETS.datasets[0];
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(row) });
  });
  await page.route("**/library/desk/resources*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_RESOURCES_ROLLUP),
    }),
  );
  await page.route("**/health*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_HEALTH) }),
  );
  await page.route("**/library/discover/probe", (route) => {
    if (route.request().method() !== "POST") {
      return route.continue();
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_PROBE_RESULT),
    });
  });
  await page.route("**/library/discover/collect", (route) => {
    if (route.request().method() !== "POST") {
      return route.continue();
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        job: {
          id: "job-discover-collect-1",
          status: "pending_approval",
          plan: { title: "MOPS financial statements" },
        },
      }),
    });
  });
  await page.route("**/library/discover/web*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_WEB_DISCOVER),
    }),
  );
  await page.route("**/library/discover?*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(discoverBody),
    }),
  );
  await page.route("**/library/discover", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(discoverBody),
    }),
  );
  await page.route("**/library/search*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ sections: [], total: 0 }),
    }),
  );
  await page.route("**/library/ops*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_OPS) }),
  );
  await page.route("**/library/overview*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_OVERVIEW) }),
  );
  await page.route("**/library/catalog*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_CATALOG_SUMMARY) }),
  );
  await page.route("**/yzu/status*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(MOCK_CLUSTER) }),
  );
  await page.route("**/library/jobs*", (route) => {
    if (route.request().method() === "POST" && route.request().url().includes("approve-safe")) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ approved: ["job-pending-1"], approved_count: 1 }),
      });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(jobsBody) });
  });
  await page.route("**/library/partitions*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ partitions: [] }) }),
  );
  await page.route("**/library/desk/warm", (route) => {
    if (route.request().method() !== "POST") {
      return route.continue();
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ primed: true, session_id: "warm-test" }),
    });
  });
  const chatReply = chatComplete || {
    session_id: "test-session",
    reply: "Resources context received.",
    action: "answer",
  };
  const streamBody = `${JSON.stringify({ type: "complete", result: chatReply })}\n`;
  await page.route("**/library/chat/stream", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({
      status: 200,
      contentType: "application/x-ndjson",
      body: streamBody,
    });
  });
  await page.route("**/api/library/chat/stream", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({
      status: 200,
      contentType: "application/x-ndjson",
      body: streamBody,
    });
  });
  await page.route("**/library/chat", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(chatReply),
    });
  });
  await page.route("**/api/library/chat", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(chatReply),
    });
  });
  await page.route(/\/library\/synthesis\/(?!profiles|run|pair)[^/?#]+$/, (route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(synthesisDetail),
    });
  });
  await page.route("**/library/synthesis/profiles", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(synthesisProfiles),
    }),
  );
  await page.route("**/yzu/acquisitions*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ acquisitions: [] }) }),
  );
  await page.route("**/library/faculty/profile*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        found: true,
        profile: {
          name_en: "Test Prof",
          email: "test@saturn.yzu.edu.tw",
          discipline: "YZU FinTech",
          title: "Assistant Professor",
          specialties: ["FinTech", "Asset Pricing"],
          method_tags: ["empirical_secondary"],
          research_tracks: [
            { id: "t1", phase: "active_grant", title: "Token taxonomy pilot", weight: 1 },
          ],
          publication_highlights: [
            "Test, A. (2023). Sample paper on FinTech panels. SSRN 1.",
          ],
          paper_count_parsed: 3,
          lab_fintech_stack: [
            { id: "cg", label: "CoinGecko daily archive", route: "vault" },
          ],
          procurement_recommendations: [
            { dataset: "MOPS filings", search_query: "MOPS financial statements", source_route: "twse_openapi" },
            { dataset: "TWSE governance", search_query: "TWSE OpenAPI", source_route: "twse_openapi" },
          ],
          default_search_query: "MOPS financial statements",
          preferred_destination: "collection/",
          domain_tags: ["stablecoin"],
        },
      }),
    }),
  );
  await page.route("**/query/*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ rows: [{ date: "2026-04-30", country: "TW", score: 0.82 }] }),
    }),
  );
}

export async function v2Nav(page, label) {
  await page.locator("aside.yzu-sidebar").getByRole("button", { name: label, exact: true }).click();
}

export async function waitForShell(page) {
  await page.locator(".rd-v2-shell").waitFor({ timeout: 30_000 });
}
