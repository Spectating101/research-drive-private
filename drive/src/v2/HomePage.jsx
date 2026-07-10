import { useMemo } from "react";
import { deskPipelineStrips } from "@/v2/deskSeed";
import { recentDatasets } from "@/v2/recent";
import { PageShell } from "@/v2/ui";
import { displayName, statusPillKind } from "@/v2/datasetMeta";

function jobTitle(job) {
  return (
    job?.plan?.title ||
    job?.title ||
    job?.name ||
    job?.dataset_id ||
    job?.type ||
    "Procurement job"
  );
}

function HomeAttentionRow({ item, onOpen, onApproveSafeJobs }) {
  const actionName = `${item.label}: ${item.title}`;
  return (
    <article
      className={`rd-v2-home-attention-row${item.warn ? " warn" : ""}`}
      data-kind={item.kind}
      aria-label={`${item.label}: ${item.title}`}
    >
      <span className="rd-v2-home-attention-label">{item.label}</span>
      <div className="rd-v2-home-attention-main">
        <strong>{item.title}</strong>
        <span>{item.detail}</span>
      </div>
      <span className="rd-v2-home-attention-metric">{item.metric}</span>
      <div className="rd-v2-home-attention-actions">
        {item.kind === "approval" && onApproveSafeJobs ? (
          <button
            type="button"
            className="rd-v2-btn sm primary"
            aria-label="Approve safe pending jobs"
            onClick={() => onApproveSafeJobs()}
          >
            Approve safe
          </button>
        ) : null}
        <button
          type="button"
          className="rd-v2-btn sm"
          aria-label={`Open ${actionName}`}
          onClick={() => onOpen(item)}
        >
          Open
        </button>
      </div>
    </article>
  );
}

export function HomePage({
  datasets,
  health,
  cluster,
  profile = null,
  acquisitions = [],
  partitions = [],
  jobs = [],
  usingSeed = false,
  onAskComposer,
  onGoTab,
  onOpenAttention,
  onSelectDataset,
  onPreviewDataset,
  onSuggestSearch,
  onApproveSafeJobs,
}) {
  const recent = useMemo(() => recentDatasets(datasets, 5), [datasets]);
  const continueDs = recent[0] || datasets[0] || null;
  const healthJobs = health?.desk?.jobs || {};
  const pendingJobs = useMemo(
    () => jobs.filter((job) => /pending|approval|hold/i.test(String(job.status || job.state || ""))),
    [jobs],
  );
  const pending = healthJobs.pending_approval ?? pendingJobs.length;
  const pipeline = useMemo(() => deskPipelineStrips(health, acquisitions), [health, acquisitions]);
  const recentRows = recent.length ? recent : datasets.slice(0, 5);
  const readyCount = datasets.filter((d) => statusPillKind(d).kind === "query-ready").length;
  const runningJobs = healthJobs.running ?? pipeline.filter((a) => a.stage === "running").length;
  const firstPendingJob = pendingJobs[0];
  const firstPipeline = pipeline[0] || null;

  const attentionItems = useMemo(() => {
    const items = [];
    if (pending > 0) {
      const title = firstPendingJob ? jobTitle(firstPendingJob) : "Procurement approval waiting";
      const jobId = firstPendingJob?.id;
      items.push({
        id: "approval",
        kind: "approval",
        label: "Approval",
        title,
        metric: `${pending} pending`,
        detail: "Review source, cost, and vault destination before collection starts.",
        next: "Review source, cost, destination",
        tab: "browse",
        discoverFilter: "awaiting",
        warn: true,
        resourceRow: {
          kind: "active",
          key: jobId ? `job-${jobId}` : "jobs-pending",
          label: title,
          metric: firstPendingJob?.status
            ? String(firstPendingJob.status).replace(/_/g, " ")
            : `${pending} job(s) pending`,
          section: "active",
          warn: true,
          ok: false,
          job: firstPendingJob,
        },
        prompt: `Review the pending procurement approval for ${title}${jobId ? ` (job ${jobId})` : ""}. Check source fit, access terms, expected cost, vault destination, and whether this should be approved now.`,
      });
    }
    if (runningJobs > 0 || firstPipeline) {
      const title = firstPipeline?.name || firstPipeline?.title || "Procurement in progress";
      const amount = firstPipeline?.amount || firstPipeline?.subtitle || `${runningJobs || 1} running`;
      items.push({
        id: "procurement",
        kind: "procurement",
        label: "Procurement",
        title,
        metric: amount,
        detail: "Live acquisition from desk workers.",
        next: "Inspect run health",
        tab: "resources",
        warn: firstPipeline?.stage === "warn",
        resourceRow: {
          kind: "active",
          key: firstPipeline?.id || "jobs-running",
          label: title,
          metric: amount,
          section: "active",
          warn: firstPipeline?.stage === "warn",
          ok: firstPipeline?.stage !== "warn",
          meta: firstPipeline,
        },
        prompt: `Explain the current procurement run: ${title} (${amount}). Summarize progress, blockers, resource usage, and the next safe action.`,
      });
    }
    items.push({
      id: "library",
      kind: "library",
      label: "Library",
      title: "Faculty vault",
      metric: `${datasets.length} holdings`,
      detail: `${readyCount || datasets.length} query-ready in Lab.`,
      next: "Open folders or upload",
      tab: "library",
      prompt: `Summarize Library readiness across ${datasets.length} holdings. Identify query-ready datasets, likely gaps, and what should be uploaded, linked, or procured next.`,
    });
    items.push({
      id: "discover",
      kind: "discover",
      label: "Discover",
      title: "Find missing data",
      metric: "Probe path",
      detail: "Search registries, then probe and collect.",
      next: "Search, probe, plan",
      tab: "browse",
      prompt:
        "Find missing datasets for this faculty workspace. Start from the local catalog, then suggest registry searches, public probes, vault destinations, and approval points.",
    });
    return items;
  }, [datasets.length, firstPendingJob, firstPipeline, pending, readyCount, runningJobs]);

  const openAttention = (item) => {
    if (item?.kind === "approval" || item?.discoverFilter || (item.tab === "browse" && item.resourceRow?.job)) {
      onOpenAttention?.(item);
      return;
    }
    if (item.tab === "resources" && item.resourceRow && onOpenAttention) {
      onOpenAttention(item);
      return;
    }
    onGoTab(item.tab);
  };

  const visibleAttention = attentionItems.slice(0, 3);
  const gapChips = useMemo(() => {
    const fromProfile = (profile?.procurement_recommendations || [])
      .map((r) => r.search_query || r.title || r.prompt)
      .filter(Boolean)
      .slice(0, 3);
    if (fromProfile.length) return fromProfile;
    return ["TWSE governance", "MOPS filings", "stablecoin incidents"];
  }, [profile]);

  return (
    <PageShell
      className="rd-v2-home-page"
      title="Home"
      lead="Continue · running · recent — not the full catalog"
      footer={null}
    >
      <section className="rd-v2-home-brief" aria-label="Research Drive brief">
        <div className="rd-v2-home-brief-copy">
          <span className="rd-v2-eyebrow">Institutional research data OS</span>
          <h2>Turn a research question into trusted, reusable evidence.</h2>
          <p>
            Search the lab first, verify source and coverage, acquire what is missing, and preserve every useful result for the next project.
          </p>
        </div>
        <div className="rd-v2-home-capabilities" aria-label="Research Drive capabilities">
          <button type="button" onClick={() => onGoTab("browse")}>
            <strong>Find</strong>
            <span>{datasets.length} holdings plus external indexes</span>
          </button>
          <button type="button" onClick={() => onGoTab("library")}>
            <strong>Verify</strong>
            <span>Coverage, provenance and readiness</span>
          </button>
          <button type="button" onClick={() => onGoTab("browse")}>
            <strong>Acquire</strong>
            <span>Probe → approve → worker → vault</span>
          </button>
          <button type="button" onClick={() => onGoTab("synthesis")}>
            <strong>Synthesize</strong>
            <span>Join registered evidence into panels</span>
          </button>
        </div>
      </section>

      {continueDs ? (
        <section className="rd-v2-home-continue" aria-label="Continue">
          <div className="rd-v2-home-continue-copy">
            <span>{usingSeed ? "Offline sample" : "Continue"}</span>
            <h2>{displayName(continueDs)}</h2>
            <p className="rd-v2-home-continue-id mono">{continueDs.dataset_id}</p>
            <p>
              {readyCount} query-ready · {datasets.length} holdings
              {pending > 0 ? ` · ${pending} awaiting approval` : ""}
            </p>
          </div>
          <div className="rd-v2-home-continue-actions">
            <button
              type="button"
              className="rd-v2-btn sm"
              onClick={() => {
                onSelectDataset?.(continueDs);
                onGoTab("library");
              }}
            >
              Open in Library
            </button>
            <button
              type="button"
              className="rd-v2-btn sm primary"
              onClick={() => onPreviewDataset?.(continueDs)}
            >
              Preview rows
            </button>
          </div>
        </section>
      ) : (
        <section className="rd-v2-home-continue" aria-label="Continue">
          <div className="rd-v2-home-continue-copy">
            <span>Start</span>
            <h2>Open the vault or search for missing data</h2>
            <p>No recent dataset yet.</p>
          </div>
          <div className="rd-v2-home-continue-actions">
            <button type="button" className="rd-v2-btn sm primary" onClick={() => onGoTab("library")}>
              Open vault
            </button>
            <button type="button" className="rd-v2-btn sm" onClick={() => onGoTab("browse")}>
              Search sources
            </button>
          </div>
        </section>
      )}

      <section className="rd-v2-home-attention" aria-label="Attention queue">
        <div className="rd-v2-home-attention-head">
          <h2>Needs attention</h2>
          <span>
            {visibleAttention.length} of {attentionItems.length}
          </span>
        </div>
        <div className="rd-v2-home-attention-body">
          {visibleAttention.map((item) => (
            <HomeAttentionRow
              key={item.id}
              item={item}
              onOpen={openAttention}
              onApproveSafeJobs={onApproveSafeJobs}
            />
          ))}
        </div>
      </section>

      {recentRows.length ? (
        <section className="rd-v2-home-recent" aria-label="Recent datasets">
          <div className="rd-v2-home-attention-head">
            <h2>Recent</h2>
            <button type="button" className="rd-v2-linkish" onClick={() => onGoTab("library")}>
              See Library →
            </button>
          </div>
          <ul className="rd-v2-home-recent-list">
            {recentRows.slice(0, 4).map((row) => (
              <li key={row.dataset_id}>
                <button
                  type="button"
                  className="rd-v2-home-recent-row"
                  onClick={() => {
                    onSelectDataset?.(row);
                    onGoTab("library");
                  }}
                >
                  <span className="rd-v2-home-recent-main">
                    <strong>{displayName(row)}</strong>
                    <em className="mono">{row.dataset_id}</em>
                  </span>
                  <span className="rd-v2-pill">
                    {statusPillKind(row).kind === "query-ready"
                      ? "Query-ready"
                      : "In vault"}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section className="rd-v2-home-gaps" aria-label="Suggested searches">
        <div className="rd-v2-home-attention-head">
          <h2>Suggested gaps</h2>
        </div>
        <div className="rd-v2-home-gap-chips">
          {gapChips.map((chip) => (
            <button
              key={chip}
              type="button"
              className="rd-v2-chip"
              onClick={() => {
                if (onSuggestSearch) onSuggestSearch(chip);
                else onGoTab("browse");
              }}
            >
              {chip}
            </button>
          ))}
        </div>
      </section>
    </PageShell>
  );
}
