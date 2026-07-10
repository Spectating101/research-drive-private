import { jobStatusLabel } from "@/v2/askArtifacts";
import { jobTitle } from "@/v2/procurementJobs";

export function ProcurementDecisionCard({
  job,
  error,
  busy = false,
  onApprove,
  title,
  showApproveButton = true,
}) {
  if (!job && !error) return null;

  const label = title || (job ? jobTitle(job) : "");
  const needsApproval = job?.status === "pending_approval";

  return (
    <section
      className="rd-v2-procure-decision"
      data-testid="procurement-decision-card"
      aria-label="Procurement decision"
    >
      {error ? <p className="rd-v2-procure-decision-error">{error}</p> : null}

      {job ? (
        <>
          <div className="rd-v2-procure-decision-head">
            <span className="rd-v2-procure-decision-label">Collection job</span>
            <span className={`rd-v2-chip sm${needsApproval ? " warn" : ""}`}>
              {jobStatusLabel(job.status)}
            </span>
          </div>
          {label ? <p className="rd-v2-procure-decision-title">{label}</p> : null}
          <code className="rd-v2-procure-decision-id">{job.id}</code>

          {needsApproval ? (
            <p className="rd-v2-procure-decision-hint">
              Review connector fit, access terms, and vault destination — then approve to start collection.
            </p>
          ) : job.status === "running" ? (
            <p className="rd-v2-procure-decision-hint">
              Collection is running. Open Resources → Activity for progress.
            </p>
          ) : job.status === "queued" ? (
            <p className="rd-v2-procure-decision-hint">Approved — waiting for a worker slot.</p>
          ) : null}

          {needsApproval && onApprove && showApproveButton ? (
            <div className="rd-v2-procure-decision-actions">
              <button
                type="button"
                className="rd-v2-btn primary sm"
                disabled={busy}
                onClick={() => onApprove(job.id)}
              >
                Approve collection
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
