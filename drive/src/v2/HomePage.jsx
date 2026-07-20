import { useMemo } from "react";
import { CatalogList } from "@/v2/CatalogList";
import { DeskLanesStrip } from "@/v2/DeskLanesStrip";
import { GuidedState, Skeleton } from "@/v2/InteractionFeedback";
import { recentDatasets } from "@/v2/recent";
import { PageShell, SectionTitle } from "@/v2/ui";
import { displayName, statusPill } from "@/v2/datasetMeta";

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

function HomeAttentionRow({ item, onOpen }) {
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
          aria-label={`Review ${actionName}`}
          onClick={() => onOpen(item)}
        >
          Review
        </button>
      </div>
    </article>
  );
}

function HomeContinueSkeleton() {
  return (
    <div className="rd-v2-home-loading-copy" data-testid="home-loading-state">
      <span>Restoring research context</span>
      <Skeleton lines={3} label="Loading the most recent research asset" />
      <div className="rd-v2-home-loading-meta">
        <Skeleton lines={1} label="Loading readiness" />
        <Skeleton lines={1} label="Loading activity" />
      </div>
    </div>
  );
}

export function HomePage({
  datasets,
  health,
  jobs = [],
  onAskComposer,
  onGoTab,
  onOpenAttention,
  onSelectDataset,
  onPreviewDataset,
}) {
  const recent = useMemo(() => recentDatasets(datasets, 3), [datasets]);
  const continueDs = recent[0] || datasets[0] || null;
  const loading = health == null && datasets.length === 0;
  const healthJobs = health?.desk?.jobs || {};
  const pendingJobs = useMemo(
    () => jobs.filter((job) => /pending|approval|hold/i.test(String(job.status || job.state || ""))),
    [jobs],
  );
  const pending = healthJobs.pending_approval ?? pendingJobs.length;
  const recentRows = recent.length ? recent : datasets.slice(0, 3);
  const firstPendingJob = pendingJobs[0];

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
    return items;
  }, [firstPendingJob, pending]);

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
    onPreviewDataset?.(continueDs);
  };

  const openContinueInLibrary = () => {
    if (continueDs) onSelectDataset?.(continueDs);
    onGoTab("library");
  };

  return (
    <PageShell
      className="rd-v2-home-page"
      title="Home"
      lead="Resume a research context or address the one decision that needs you."
      footer={null}
    >
      <section
        className="rd-v2-home-continue-card"
        aria-label="Continue working"
        aria-busy={loading}
        data-testid="home-continue"
      >
        <div className="rd-v2-home-continue-copy">
          {loading ? (
            <HomeContinueSkeleton />
          ) : (
            <>
              <span>Continue working</span>
              {continueDs ? (
                <>
                  <h2>{displayName(continueDs)}</h2>
                  <p className="rd-v2-home-continue-purpose">{purposeLine(continueDs)}</p>
                  <p className="rd-v2-home-continue-meta">
                    <span className="rd-v2-pill">{statusPill(continueDs)}</span>
                    <span>{lastActivityLine(continueDs)}</span>
                  </p>
                  <p className="rd-v2-home-continue-id mono">{continueDs.dataset_id}</p>
                </>
              ) : (
                <GuidedState
                  eyebrow="No recent asset"
                  title="Open the vault or find missing data"
                  detail="Research Drive has no recent dataset to resume in this browser yet."
                  checks={["Library holds registered assets", "Discover searches beyond current holdings"]}
                />
              )}
            </>
          )}
        </div>
        <div className="rd-v2-home-continue-actions">
          {loading ? (
            <Skeleton className="rd-v2-home-action-skeleton" lines={2} label="Loading actions" />
          ) : (
            <>
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
            </>
          )}
        </div>
      </section>

      {loading ? (
        <div className="rd-v2-home-lanes-loading" aria-label="Loading research entrances">
          <Skeleton lines={2} />
          <Skeleton lines={2} />
          <Skeleton lines={2} />
        </div>
      ) : (
        <DeskLanesStrip holdings={datasets.length} onGoTab={onGoTab} onAskComposer={onAskComposer} />
      )}

      <section className="rd-v2-home-attention" aria-label="Attention queue" aria-busy={loading}>
        <div className="rd-v2-home-attention-head">
          <h2>Attention</h2>
          <span>{loading ? "Checking" : attentionItems.length ? `${attentionItems.length} needing action` : "Clear"}</span>
        </div>
        <div className="rd-v2-home-attention-body">
          {loading ? (
            <Skeleton className="rd-v2-home-attention-skeleton" lines={2} label="Checking the attention queue" />
          ) : attentionItems.length ? (
            attentionItems.map((item) => (
              <HomeAttentionRow
                key={item.id}
                item={item}
                onOpen={openAttention}
              />
            ))
          ) : (
            <p className="rd-v2-home-attention-empty">Nothing needs a decision right now.</p>
          )}
        </div>
      </section>

      <section className="rd-v2-home-recent" aria-label="Recent research assets" aria-busy={loading}>
        <SectionTitle title="Recent research assets" actionLabel="Open Library →" onAction={() => onGoTab("library")} />
        <div className="rd-v2-home-list-panel">
          {loading ? (
            <div className="rd-v2-home-list-skeletons">
              <Skeleton lines={2} label="Loading recent research assets" />
              <Skeleton lines={2} />
              <Skeleton lines={2} />
            </div>
          ) : (
            <CatalogList
              rows={recentRows.map(datasetListItem)}
              onSelectDataset={onSelectDataset}
              onDoubleClick={onPreviewDataset}
              compact
            />
          )}
        </div>
      </section>
    </PageShell>
  );
}
