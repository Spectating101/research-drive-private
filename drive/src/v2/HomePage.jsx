import { useMemo } from "react";
import { CatalogList } from "@/v2/CatalogList";
import { DeskLanesStrip } from "@/v2/DeskLanesStrip";
import { HomeSuggestedAsks } from "@/v2/HomeSuggestedAsks";
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

function readinessLabel(ds) {
  const raw = String(ds?.analysis_readiness || "").toLowerCase();
  if (/instant|ready|query|connected/.test(raw)) return "Query-ready";
  if (/dry/.test(raw)) return "Dry-run";
  if (raw) return raw.replace(/_/g, " ");
  return "In vault";
}

function purposeLine(ds) {
  return (
    ds?.summary ||
    ds?.description ||
    ds?.purpose ||
    [ds?.source, ds?.coverage, ds?.grain].filter(Boolean).join(" · ") ||
    "Research dataset in the lab vault"
  );
}

function lastActivityLine(ds) {
  const stamp = ds?.updated_at || ds?.last_accessed || ds?.last_activity || ds?.as_of;
  if (stamp) return `Last activity · ${stamp}`;
  if (ds?.coverage) return `Coverage · ${ds.coverage}`;
  return "Available in the lab vault";
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
  const readyCount = datasets.filter((d) =>
    /instant|ready|query|connected/i.test(String(d.analysis_readiness || "")),
  ).length;
  const registryTotal = cluster?.registry_datasets || health?.datasets || datasets.length;
  const instantTotal = cluster?.instant_datasets || readyCount;
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
        detail: "Decision required before collection can continue.",
        next: "Review source, cost, destination",
        tab: "resources",
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
        detail: "Live acquisition needs a check.",
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
    return items;
  }, [firstPendingJob, firstPipeline, pending, runningJobs]);

  const openAttention = (item) => {
    if (item.tab === "resources" && item.resourceRow && onOpenAttention) {
      onOpenAttention(item);
      return;
    }
    onGoTab(item.tab);
  };

  const continueWork = () => {
    if (!continueDs) {
      onGoTab("library");
      return;
    }
    onSelectDataset?.(continueDs);
  };

  const openContinueInLibrary = () => {
    if (continueDs) onSelectDataset?.(continueDs);
    onGoTab("library");
  };

  return (
    <PageShell
      className="rd-v2-home-page"
      title="Home"
      lead="Pick up where you left off — vault, discover, or ask."
      footer={null}
    >
      <section
        className="rd-v2-home-continue-card"
        aria-label="Continue working"
        data-testid="home-continue"
      >
        <div className="rd-v2-home-continue-copy">
          <span>Continue working</span>
          {continueDs ? (
            <>
              <h2>{displayName(continueDs)}</h2>
              <p>{purposeLine(continueDs)}</p>
              <p className="rd-v2-home-continue-meta">
                <span className="rd-v2-pill">{readinessLabel(continueDs)}</span>
                <span>{lastActivityLine(continueDs)}</span>
              </p>
              <p className="rd-v2-home-continue-id mono">{continueDs.dataset_id}</p>
            </>
          ) : (
            <>
              <h2>Open the vault or find missing data</h2>
              <p>No recent dataset yet. Start from Lab holdings or Discover.</p>
            </>
          )}
        </div>
        <div className="rd-v2-home-continue-actions">
          <button type="button" className="rd-v2-btn sm primary" onClick={continueWork}>
            Continue
          </button>
          {continueDs ? (
            <button type="button" className="rd-v2-btn sm" onClick={openContinueInLibrary}>
              Open in Library
            </button>
          ) : (
            <button type="button" className="rd-v2-btn sm" onClick={() => onGoTab("browse")}>
              Discover data
            </button>
          )}
        </div>
      </section>

      <DeskLanesStrip holdings={datasets.length} onGoTab={onGoTab} onAskComposer={onAskComposer} />

      <section className="rd-v2-home-attention" aria-label="Attention queue">
        <div className="rd-v2-home-attention-head">
          <h2>Attention</h2>
          <span>
            {attentionItems.length
              ? `${attentionItems.length} needing action`
              : "Clear"}
          </span>
        </div>
        <div className="rd-v2-home-attention-body">
          {attentionItems.length ? (
            attentionItems.map((item) => (
              <HomeAttentionRow
                key={item.id}
                item={item}
                onOpen={openAttention}
                onAsk={onAskAttention}
              />
            ))
          ) : (
            <p className="rd-v2-home-attention-empty">Nothing needs a decision right now.</p>
          )}
        </div>
      </section>

      <section className="rd-v2-home-recent" aria-label="Recent research assets">
        <SectionTitle title="Recent" actionLabel="See Library →" onAction={() => onGoTab("library")} />
        <div className="rd-v2-home-list-panel">
          <CatalogList
            rows={recentRows.map(datasetListItem)}
            onSelectDataset={onSelectDataset}
            onDoubleClick={onPreviewDataset}
            compact
          />
        </div>
      </section>

      <HomeSuggestedAsks profile={profile} onAskComposer={onAskComposer} />

      <section className="rd-v2-home-footnote" aria-label="Desk context">
        <p>
          Lab vault, Discover, and Ask stay available from the sidebar — Home is for resuming work.
        </p>
        <p className="rd-v2-home-footnote-stats">
          <span className={usingSeed ? "warn" : ""}>
            {usingSeed ? "Offline catalog" : "Live registry"}
          </span>
          <span>
            {readyCount || instantTotal} query-ready · {registryTotal} registered
          </span>
          <button type="button" className="rd-v2-linkish" onClick={() => onGoTab("resources")}>
            Acquisitions →
          </button>
        </p>
      </section>

      {pipeline.length || pending > 0 ? (
        <section className="rd-v2-home-jobs" aria-label="Running jobs">
          <SectionTitle title="Running jobs" actionLabel="All jobs →" onAction={() => onGoTab("resources")} />
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
        </section>
      ) : null}
    </PageShell>
  );
}
