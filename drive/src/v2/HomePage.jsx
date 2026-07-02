import { useMemo } from "react";
import { CatalogList } from "@/v2/CatalogList";
import { deskPipelineStrips } from "@/v2/deskSeed";
import { recentDatasets } from "@/v2/recent";
import { PageShell, SectionTitle, Strip } from "@/v2/ui";
import { displayName } from "@/v2/datasetMeta";

function datasetListItem(row) {
  return {
    kind: "dataset",
    id: row.dataset_id,
    name: row.name,
    row,
  };
}

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

function HomeAttentionRow({ item, onOpen, onAsk }) {
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
        <small>{item.next}</small>
      </div>
      <span className="rd-v2-home-attention-metric">{item.metric}</span>
      <div className="rd-v2-home-attention-actions">
        <button
          type="button"
          className="rd-v2-btn sm"
          aria-label={`Open ${actionName}`}
          onClick={() => onOpen(item)}
        >
          Open
        </button>
        <button
          type="button"
          className="rd-v2-btn sm primary"
          aria-label={`Ask about ${actionName}`}
          onClick={() => onAsk(item)}
        >
          Ask
        </button>
      </div>
    </article>
  );
}

export function HomePage({
  datasets,
  health,
  acquisitions = [],
  jobs = [],
  onGoTab,
  onOpenAttention,
  onSelectDataset,
  onPreviewDataset,
  onAskAttention,
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
  const readyCount = datasets.filter((d) => /ready|query/i.test(d.analysis_readiness || "")).length;
  const runningJobs = healthJobs.running ?? pipeline.filter((a) => a.stage === "running").length;
  const firstPendingJob = pendingJobs[0];
  const firstPipeline = pipeline[0] || null;
  const heroPromise =
    "Search the lab vault. Procure missing datasets. Register everything for reuse.";
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
        detail: "Decision required before the agent can collect or archive.",
        next: "Review source, cost, destination",
        tab: "resources",
        warn: true,
        resourceRow: {
          kind: "active",
          key: jobId ? `job-${jobId}` : "jobs-pending",
          label: title,
          metric: firstPendingJob?.status ? String(firstPendingJob.status).replace(/_/g, " ") : `${pending} job(s) pending`,
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
        detail: "Live acquisition state from the desk and backend workers.",
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
      detail: `${readyCount || datasets.length} query-ready datasets available from the Lab directory.`,
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
      detail: "Search registries first, then probe public sources and propose acquisition.",
      next: "Search, probe, plan",
      tab: "browse",
      prompt: "Find missing datasets for this faculty workspace. Start from the local catalog, then suggest registry searches, public probes, vault destinations, and approval points.",
    });
    return items;
  }, [datasets.length, firstPendingJob, firstPipeline, pending, readyCount, runningJobs]);

  const openAttention = (item) => {
    if (item.tab === "resources" && item.resourceRow && onOpenAttention) {
      onOpenAttention(item);
      return;
    }
    onGoTab(item.tab);
  };

  const askAttention = (item) => {
    onAskAttention?.(item);
  };

  return (
    <PageShell
      className="rd-v2-home-page"
      title="Home"
      lead="Continue research and inspect live procurement state."
      footer={null}
    >
      <section className="rd-v2-home-command" aria-label="Research Drive command surface">
        <div className="rd-v2-home-command-copy">
          <span>Research Drive</span>
          <strong>{heroPromise}</strong>
          {continueDs ? (
            <p className="rd-v2-home-continue">
              Continue: <em>{displayName(continueDs)}</em>
              <span className="rd-v2-home-continue-id">{continueDs.dataset_id}</span>
            </p>
          ) : (
            <p>{datasets.length} indexed holdings ready to browse.</p>
          )}
        </div>
        <div className="rd-v2-home-command-actions">
          <button type="button" className="primary" onClick={() => onGoTab("library")}>
            Open lab vault
            <span>{datasets.length} registered holdings</span>
          </button>
          <button type="button" onClick={() => onGoTab("browse")}>
            Find missing data
            <span>search, probe, procure</span>
          </button>
          <button type="button" onClick={() => onGoTab("resources")}>
            Check safety
            <span>{pending > 0 ? `${pending} approvals` : "limits normal"}</span>
          </button>
        </div>
      </section>

      <section className="rd-v2-home-attention" aria-label="Attention queue">
        <div className="rd-v2-home-attention-head">
          <h2>Attention</h2>
          <span>{attentionItems.length} objects</span>
        </div>
        <div className="rd-v2-home-attention-body">
          {attentionItems.map((item) => (
            <HomeAttentionRow
              key={item.id}
              item={item}
              onOpen={openAttention}
              onAsk={askAttention}
            />
          ))}
        </div>
      </section>

      <SectionTitle title="Recent" actionLabel="See Library →" onAction={() => onGoTab("library")} />
      <div className="rd-v2-home-list-panel">
        <CatalogList
          rows={recentRows.map(datasetListItem)}
          onSelectDataset={onSelectDataset}
          onDoubleClick={onPreviewDataset}
          compact
        />
      </div>

      <SectionTitle title="Running jobs" actionLabel="All jobs →" onAction={() => onGoTab("resources")} />
      {pipeline.length === 0 && pending === 0 ? (
        <Strip>● Desk idle · {runningJobs || 0} running <span className="rd-v2-pill muted">OK</span></Strip>
      ) : null}
      {pipeline.map((a) => (
        <Strip key={a.id || a.name} warn={a.stage === "warn"}>
          ● {a.name || a.title} · {a.amount || a.subtitle || a.stage || "running"}{" "}
          <span className={`rd-v2-pill${a.stage === "warn" ? " warn" : a.stage === "running" ? "" : " muted"}`}>
            {(a.stage === "warn" ? "WARN" : a.stage === "running" ? "OK" : (a.stage || "OK")).toUpperCase()}
          </span>
        </Strip>
      ))}

      {pending > 0 ? (
        <Strip warn actionLabel="Approve →" onAction={() => onGoTab("resources")}>
          ● Pending approvals · {pending} <span className="rd-v2-pill warn">WARN</span>
        </Strip>
      ) : null}
    </PageShell>
  );
}
