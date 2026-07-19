/** Shared Playwright API mocks for Research Drive v2. */

import { MOCK_RESOURCES_ROLLUP } from "./mockResourcesRollup.js";

export const MOCK_DATASETS = {
  datasets: [
    {
      dataset_id: "gdelt_asia_daily_country_panel",
      name: "Asia daily news-risk panel",
      grain: "country_day",
      analysis_readiness: "instant",
      local_root: "research_panels/gdelt",
      source: "GDELT GKG",
      source_system: "GDELT news graph",
      join_keys: ["date", "country_iso3"],
      coverage: "2018–2024",
    },
    {
      dataset_id: "ticker_week_country_broadcast_panel",
      name: "Ticker week panel",
      grain: "country-week",
      analysis_readiness: "instant",
      source_system: "In-house derived research panels",
      join_keys: ["ticker", "week", "country_iso3"],
    },
    {
      dataset_id: "issuer_weekly_panel",
      name: "Issuer weekly fundamentals",
      grain: "issuer_week",
      analysis_readiness: "instant",
      source_system: "MOPS",
      source: "MOPS",
      join_keys: ["issuer_id", "week"],
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
          candidate_key: "dataset:mops_financial_statements_ext",
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

export const MOCK_SYNTHESIS_PROFILES = {
  profiles: [
    {
      profile_id: "stablecoin_trust_engagement",
      title: "Stablecoin trust & engagement",
      type: "Research panel",
      objective: "Combine security, on-chain activity, and public attention into one weekly research panel.",
      inputs: [
        {
          dataset_id: "skynet_stablecoin_security",
          name: "Stablecoin security & governance",
          source: "CertiK Skynet",
          grain: "asset-week",
          coverage: "2021–2026",
          join_keys: ["asset_id", "week"],
          analysis_readiness: "instant",
        },
        {
          dataset_id: "etherscan_stablecoin_activity",
          name: "Stablecoin on-chain activity",
          source: "Etherscan",
          grain: "asset-day",
          coverage: "2021–2026",
          join_keys: ["asset_id", "date"],
          analysis_readiness: "instant",
        },
        {
          dataset_id: "stablecoin_attention_overlay",
          name: "Public attention overlay",
          source: "GDELT · Wikipedia · GitHub",
          grain: "asset-week",
          coverage: "2021–2026",
          join_keys: ["asset_id", "week"],
          analysis_readiness: "instant",
        },
      ],
      output: {
        dataset_id: "stablecoin_trust_weekly_panel",
        name: "Stablecoin trust weekly panel",
        grain: "asset-week",
        coverage: "2021–2026",
        destination: "Research panels",
      },
    },
    {
      profile_id: "skynet_etherscan_stablecoin",
      title: "Security × on-chain activity",
      type: "Two-source synthesis",
      objective: "Join governance and security signals to observed on-chain activity.",
      inputs: [
        {
          dataset_id: "skynet_stablecoin_security",
          name: "Stablecoin security & governance",
          source: "CertiK Skynet",
          grain: "asset-week",
          coverage: "2021–2026",
          join_keys: ["asset_id", "week"],
          analysis_readiness: "instant",
        },
        {
          dataset_id: "etherscan_stablecoin_activity",
          name: "Stablecoin on-chain activity",
          source: "Etherscan",
          grain: "asset-day",
          coverage: "2021–2026",
          join_keys: ["asset_id", "date"],
          analysis_readiness: "instant",
        },
      ],
      output: {
        dataset_id: "skynet_etherscan_stablecoin_panel",
        name: "Security and activity panel",
        grain: "asset-week",
        coverage: "2021–2026",
        destination: "Synthesis outputs",
      },
    },
  ],
};

export const MOCK_JOBS = {
  jobs: [
    {
      id: "job-pending-1",
      status: "pending_approval",
      type: "procure",
      candidate_key: null,
      connector_id: null,
      registered_dataset_id: null,
      output_manifest_id: null,
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
      source_url: "https://example.com/data.csv",
      discovered_files: [{ url: "https://example.com/data.csv" }],
    },
  },
  summary: "direct_file source; 1 downloadable links detected; recommendation: collect_manifest",
  resolved_url: "https://example.com/data.csv",
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
          candidate_key: "url:https://example.com/dataset",
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
    historyBody = { items: [] },
    profileBody = { found: true, profile: { name_en: "Test Prof", discipline: "YZU" } },
  } = {},
) {
  const liveJobs = {
    jobs: Array.isArray(jobsBody?.jobs) ? [...jobsBody.jobs] : [],
  };
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
    let candidateKey = "";
    try {
      candidateKey = JSON.parse(route.request().postData() || "{}").candidate_key || "";
    } catch {
      candidateKey = "";
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...MOCK_PROBE_RESULT,
        candidate_key: candidateKey || null,
        connector_id: MOCK_PROBE_RESULT.connector.connector_id,
        resolved_url: MOCK_PROBE_RESULT.resolved_url,
      }),
    });
  });
  await page.route("**/library/discover/collect", (route) => {
    if (route.request().method() !== "POST") {
      return route.continue();
    }
    let body = {};
    try {
      body = JSON.parse(route.request().postData() || "{}");
    } catch {
      body = {};
    }
    const job = {
      id: `job-discover-collect-${liveJobs.jobs.length + 1}`,
      status: "pending_approval",
      candidate_key: body.candidate_key || null,
      connector_id: body.connector_id || null,
      registered_dataset_id: null,
      output_manifest_id: null,
      plan: { title: body.title || "Discover collect" },
      request: {
        candidate_key: body.candidate_key || null,
        connector_id: body.connector_id || null,
        source_identity: body.source_identity || body.source || null,
        dataset_id: body.dataset_id || null,
        doi: body.doi || null,
        url: body.url || null,
      },
    };
    liveJobs.jobs = [job, ...liveJobs.jobs.filter((j) => j?.id !== job.id)];
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ job }),
    });
  });
  await page.route("**/library/discover/web*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_WEB_DISCOVER),
    }),
  );
  await page.route("**/library/discover/history?*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(historyBody) }),
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
  await page.route("**/library/discover/sources?*", (route) => {
    const sections = Array.isArray(discoverBody?.sections) ? discoverBody.sections : [];
    const rows = sections.length
      ? sections.flatMap((section) => section?.rows || [])
      : Array.isArray(discoverBody?.results)
        ? discoverBody.results
        : [];
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ results: rows }),
    });
  });
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
  await page.route("**/library/jobs*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(liveJobs) }),
  );
  await page.route("**/library/partitions*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ partitions: [] }) }),
  );
  await page.route("**/library/synthesis/profiles", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_SYNTHESIS_PROFILES),
    }),
  );
  await page.route("**/library/synthesis/run", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    let body = {};
    try {
      body = JSON.parse(route.request().postData() || "{}");
    } catch {
      body = {};
    }
    const profile =
      MOCK_SYNTHESIS_PROFILES.profiles.find((item) => item.profile_id === body.profile_id) ||
      MOCK_SYNTHESIS_PROFILES.profiles[0];
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "completed",
        registered: true,
        registered_dataset_id: profile.output.dataset_id,
        row_count: 18432,
        output: { ...profile.output, registered: true },
      }),
    });
  });
  await page.route("**/library/synthesis/pair", (route) => {
    if (route.request().method() !== "POST") return route.continue();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "completed",
        registered: false,
        output_dataset_id: "custom_pair_synthesis",
        row_count: 830,
        output: {
          dataset_id: "custom_pair_synthesis",
          name: "Custom pair synthesis",
          grain: "derived",
          coverage: "Computed from input overlap",
          destination: "Synthesis outputs",
        },
      }),
    });
  });
  await page.route("**/library/synthesis/*", (route) => {
    const id = decodeURIComponent(route.request().url().split("/library/synthesis/")[1]?.split("?")[0] || "");
    // This wildcard is registered last, so let the explicit profile/run/pair routes handle their contracts.
    if (["profiles", "run", "pair"].includes(id)) return route.fallback();
    const profile =
      MOCK_SYNTHESIS_PROFILES.profiles.find((item) => item.profile_id === id) ||
      MOCK_SYNTHESIS_PROFILES.profiles[0];
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ profile }),
    });
  });
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
  const fulfillChat = (route) => {
    const body = route.request().postDataJSON?.() || {};
    const entity = body?.rail_context?.entity || {};
    const reply =
      entity.kind === "discover_history"
        ? `Lifecycle context received for ${entity.title || "selected record"}.`
        : entity.kind === "external_candidate"
          ? `Source context received for ${entity.title || "selected candidate"}.`
          : entity.kind === "synthesis_thread"
            ? `Synthesis thread context received for ${entity.title || "selected thread"}.`
          : "Resources context received.";
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ session_id: "test-session", reply, action: "answer" }),
    });
  };
  await page.route("**/api/library/chat/stream", fulfillChat);
  await page.route("**/api/library/chat", fulfillChat);
  await page.route("**/yzu/acquisitions*", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ acquisitions: [] }) }),
  );
  await page.route("**/library/faculty/profile*", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(profileBody),
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
