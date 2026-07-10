import { useEffect, useMemo } from "react";
import {
  activeProcurementJobs,
  jobTitle,
  pendingApprovalJobs,
} from "@/v2/procurementJobs";
import { Chip } from "@/v2/ui";

const ACTIVITY_FILTERS = [
  { id: "all", label: "All" },
  { id: "awaiting", label: "Awaiting" },
  { id: "running", label: "Running" },
  { id: "queued", label: "Queued" },
  { id: "failed", label: "Recent failures" },
];

function statusLabel(status) {
  if (status === "pending_approval") return "Awaiting you";
  if (status === "running") return "Collecting";
  if (status === "queued") return "Queued";
  if (status === "failed") return "Failed";
  if (status === "done" || status === "completed") return "Registered";
  return status || "Job";
}

function statusClass(status) {
  if (status === "pending_approval") return "queue";
  if (status === "running" || status === "queued") return "conn";
  if (status === "failed") return "fail";
  if (status === "done" || status === "completed") return "lab";
  return "ext";
}

function jobRowKey(job) {
  return `job:${job.id}`;
}

/** Discover Activity — a focused review queue for source acquisition jobs. */
export function DiscoverActivityPanel({
  jobs = [],
  selectedId,
  onSelectJob,
  onApproveSafeJobs,
  activityFilter = "all",
  onActivityFilterChange,
  focusAwaiting = false,
}) {
  const pending = useMemo(() => pendingApprovalJobs(jobs), [jobs]);
  const active = useMemo(() => activeProcurementJobs(jobs), [jobs]);
  const running = useMemo(
    () => jobs.filter((j) => String(j.status || "") === "running"),
    [jobs],
  );
  const queued = useMemo(
    () => jobs.filter((j) => String(j.status || "") === "queued"),
    [jobs],
  );
  const failed = useMemo(
    () => jobs.filter((j) => String(j.status || "") === "failed"),
    [jobs],
  );

  const counts = useMemo(
    () => ({
      awaiting: pending.length,
      running: running.length,
      queued: queued.length,
      failed: failed.length,
    }),
    [failed.length, pending.length, running.length, queued.length],
  );

  const effectiveFilter = focusAwaiting && activityFilter === "all" ? "awaiting" : activityFilter;

  const visibleJobs = useMemo(() => {
    if (effectiveFilter === "awaiting") return pending;
    if (effectiveFilter === "running") return running;
    if (effectiveFilter === "queued") return queued;
    if (effectiveFilter === "failed") return failed;
    // Prefer actionable first, then other active jobs.
    const seen = new Set();
    const out = [];
    for (const job of [...pending, ...running, ...queued, ...active]) {
      if (!job?.id || seen.has(job.id)) continue;
      seen.add(job.id);
      out.push(job);
    }
    return out;
  }, [effectiveFilter, pending, running, queued, failed, active]);

  useEffect(() => {
    if (!visibleJobs.length || !onSelectJob) return;
    const hasVisibleSelection = visibleJobs.some((job) => {
      const key = jobRowKey(job);
      return selectedId === key || selectedId === job.id;
    });
    if (!hasVisibleSelection) onSelectJob(visibleJobs[0]);
  }, [onSelectJob, selectedId, visibleJobs]);

  return (
    <div className="rd-v2-discover-activity" data-testid="discover-activity">
      <div className="rd-v2-discover-activity-head">
        <div>
          <h2 className="rd-v2-discover-activity-title">Review queue</h2>
          <p className="rd-v2-discover-activity-lead">
            Acquisition jobs that need approval or monitoring.
          </p>
        </div>
        {onApproveSafeJobs && pending.length > 0 ? (
          <button
            type="button"
            className="rd-v2-btn sm"
            data-testid="discover-bulk-approve-safe"
            onClick={() => onApproveSafeJobs()}
          >
            Approve all safe jobs
          </button>
        ) : null}
      </div>

      <div className="rd-v2-discover-activity-summary" data-testid="discover-activity-summary">
        <button type="button" onClick={() => onActivityFilterChange?.("awaiting")}>
          <span>Awaiting</span>
          <strong>{counts.awaiting}</strong>
          <em>Needs a decision</em>
        </button>
        <button type="button" onClick={() => onActivityFilterChange?.("running")}>
          <span>Running</span>
          <strong>{counts.running}</strong>
          <em>Collecting now</em>
        </button>
        <button type="button" onClick={() => onActivityFilterChange?.("queued")}>
          <span>Queued</span>
          <strong>{counts.queued}</strong>
          <em>Waiting for worker</em>
        </button>
        <button type="button" onClick={() => onActivityFilterChange?.("failed")}>
          <span>Failed 7 days</span>
          <strong>{counts.failed}</strong>
          <em>Inspect and retry</em>
        </button>
      </div>

      <div className="rd-v2-toolbar inline" data-testid="discover-activity-filters">
        {ACTIVITY_FILTERS.map((f) => (
          <Chip
            key={f.id}
            active={effectiveFilter === f.id}
            warn={f.id === "awaiting" && pending.length > 0}
            onClick={() => onActivityFilterChange?.(f.id)}
          >
            {f.label}
            {f.id === "awaiting" && pending.length ? ` · ${pending.length}` : ""}
            {f.id === "running" && running.length ? ` · ${running.length}` : ""}
            {f.id === "queued" && queued.length ? ` · ${queued.length}` : ""}
            {f.id === "failed" && failed.length ? ` · ${failed.length}` : ""}
          </Chip>
        ))}
      </div>

      {visibleJobs.length === 0 ? (
        <div className="rd-v2-discover-miss" data-testid="discover-activity-empty">
          <p className="rd-v2-empty-inline">
            {effectiveFilter === "awaiting"
              ? "No jobs awaiting approval."
              : effectiveFilter === "running"
                ? "No running collection jobs."
                : effectiveFilter === "queued"
                  ? "No queued collection jobs."
                  : effectiveFilter === "failed"
                    ? "No recent collection failures."
                  : "No acquisition jobs in this queue. Search Discover, then probe and Add to lab."}
          </p>
        </div>
      ) : (
        <div className="rd-v2-discover-activity-list" data-testid="discover-activity-list">
          <ul className="rd-v2-catalog rd-v2-discover-candidates" aria-label="Acquisition jobs">
            {visibleJobs.map((job) => {
              const key = jobRowKey(job);
              const selected = selectedId === key || selectedId === job.id;
              const title = jobTitle(job);
              const st = String(job.status || "");
              return (
                <li key={job.id} className={selected ? "rd-v2-row-on" : undefined}>
                  <button
                    type="button"
                    className={`row rd-v2-discover-candidate${selected ? " selected" : ""}`}
                    data-kind="job"
                    data-state={st === "pending_approval" ? "awaiting" : st}
                    data-testid="discover-activity-row"
                    aria-pressed={selected}
                    onClick={() => onSelectJob?.(job)}
                  >
                    <span className="rd-v2-discover-candidate-main">
                      <span className="rd-v2-discover-candidate-top">
                        <strong>{title}</strong>
                      </span>
                      <span className="rd-v2-discover-badges">
                        {statusLabel(st)}
                        {job.type ? ` · ${job.type}` : ""}
                        {job.id ? ` · ${job.id}` : ""}
                      </span>
                      {job.plan?.source || job.plan?.url ? (
                        <span className="rd-v2-discover-snippet">
                          {job.plan?.source || job.plan?.url}
                        </span>
                      ) : null}
                    </span>
                    <span className={`rd-v2-pill ${statusClass(st)}`}>{statusLabel(st)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
