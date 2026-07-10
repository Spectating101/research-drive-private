import { extractAskArtifacts, jobStatusLabel, rowKind, rowTitle } from "@/v2/askArtifacts";

export function AskMessageArtifacts({
  message,
  onApproveJob,
  onApproveLicense,
  busy,
}) {
  const { searchRows, probe, queryPreview, candidates } = extractAskArtifacts(message);
  const showSearch = searchRows.length > 0 && message.action === "search";
  const showCandidates = candidates.length > 0 && !showSearch;
  const probeSpec = probe?.connector?.spec || probe?.spec || {};
  const access = probeSpec.access_mode || probe?.access_mode;
  const contentType = probeSpec.content_type || probe?.content_type;

  return (
    <>
      {message.composerPending || message.action === "composer_pending" ? (
        <div className="rd-v2-ask-composer-pending" data-testid="ask-composer-pending">
          <span className="rd-v2-chip sm warn">Composer working</span>
          <span className="muted small">Discover and probe stay instant — this reply updates automatically.</span>
        </div>
      ) : null}

      {message.pendingJobId ? (
        <div className="rd-v2-ask-job" data-testid="ask-job-tracker">
          <span className="rd-v2-ask-job-label">Cluster job</span>
          <code className="rd-v2-ask-job-id">{String(message.pendingJobId).slice(0, 14)}…</code>
          <span className={`rd-v2-chip sm${message.jobStatus === "pending_approval" ? " warn" : ""}`}>
            {jobStatusLabel(message.jobStatus || "queued")}
          </span>
          {message.pendingJobId && message.jobStatus === "pending_approval" ? (
            <button
              type="button"
              className="rd-v2-btn sm primary"
              disabled={busy}
              onClick={() => onApproveJob?.(message.pendingJobId)}
            >
              Approve
            </button>
          ) : null}
        </div>
      ) : null}

      {message.licenseBlocked && message.licenseDoi ? (
        <div className="rd-v2-ask-license" data-testid="ask-license-gate">
          <span className="rd-v2-chip sm warn">License gate</span>
          <span className="muted small">Approve terms for {message.licenseDoi} before cluster collect.</span>
          <button
            type="button"
            className="rd-v2-btn sm"
            disabled={busy}
            onClick={() => onApproveLicense?.(message.licenseDoi)}
          >
            Approve license
          </button>
        </div>
      ) : null}

      {showSearch ? (
        <ul className="rd-v2-ask-artifacts" data-testid="ask-search-results">
          {searchRows.slice(0, 6).map((row, idx) => (
            <li key={`${rowTitle(row)}-${idx}`} className="rd-v2-ask-artifact-row">
              <strong>{rowTitle(row)}</strong>
              <span className="muted small">{rowKind(row)}</span>
            </li>
          ))}
          {searchRows.length > 6 ? (
            <li className="muted small">…and {searchRows.length - 6} more</li>
          ) : null}
        </ul>
      ) : null}

      {showCandidates ? (
        <ul className="rd-v2-ask-artifacts" data-testid="ask-candidates">
          {candidates.slice(0, 5).map((row, idx) => (
            <li key={`${rowTitle(row)}-${idx}`} className="rd-v2-ask-artifact-row">
              <strong>{rowTitle(row)}</strong>
              <span className="muted small">{rowKind(row)}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {probe && (access || contentType || probe.summary) ? (
        <div className="rd-v2-ask-probe" data-testid="ask-probe-summary">
          {probe.summary ? <p className="small">{probe.summary}</p> : null}
          {access ? (
            <p className="muted small">
              Access: <strong>{access}</strong>
              {contentType ? ` · ${contentType}` : ""}
            </p>
          ) : null}
        </div>
      ) : null}

      {queryPreview?.rows?.length ? (
        <div className="rd-v2-ask-query-preview" data-testid="ask-query-preview">
          <p className="muted small">
            Sample rows ({queryPreview.rows.length}
            {queryPreview.columns?.length ? ` · cols: ${queryPreview.columns.slice(0, 6).join(", ")}` : ""})
          </p>
          <ul className="rd-v2-ask-artifacts compact">
            {queryPreview.rows.slice(0, 4).map((row, idx) => (
              <li key={idx} className="rd-v2-ask-artifact-row mono small">
                {typeof row === "object"
                  ? Object.entries(row)
                      .slice(0, 4)
                      .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
                      .join(" · ")
                  : String(row)}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}
