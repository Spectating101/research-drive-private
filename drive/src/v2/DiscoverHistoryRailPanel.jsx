import { EmptyRailState } from "@/v2/EmptyRailState";
import { RailDecisionSummary, RailEntityHeader, RailField, RailFieldGrid, RailFrame, RailStickyFooter } from "@/v2/RailFrame";
import { historyLifecycleExplanation } from "@/v2/historyLifecycleLabel";

function text(value) {
  return String(value || "").replace(/_/g, " ").trim();
}

function historyState(event) {
  return historyLifecycleExplanation(event);
}

function updatedAt(event) {
  const value = event?.ts || event?.updated_at || event?.created_at || "";
  if (!value) return "Time unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? String(value)
    : date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function proofLabel(value) {
  if (value === true) return "Verified";
  if (value === false) return "Not verified";
  return null;
}

export function DiscoverHistoryRailPanel({ event, job, onAskAbout, onReviewRequest }) {
  if (!event) {
    return (
      <RailFrame>
        <div className="rd-v2-rail-scroll">
          <EmptyRailState
            title="No lifecycle item selected"
            hint="Select a request, schedule, failure, or registered result to inspect its durable state."
          />
        </div>
      </RailFrame>
    );
  }

  const state = historyState(event);
  const meta = event.meta || {};
  const title = event.target || event.title || event.id || "Discover request";
  const datasetId = meta.dataset_id || event.dataset_id || "";
  const source = datasetId || meta.source_id || meta.candidate_key || meta.intent_id || "Durable Discover record";
  const requestId = datasetId || meta.intent_id || meta.job_id || meta.subscription_id || event.id || "";
  const canReview = state.label === "Approval required" && Boolean(job?.id || meta.job_id);
  const registered = state.label === "Registered" || state.label === "Query ready";
  const libraryHref = datasetId ? `?tab=library&dataset=${encodeURIComponent(datasetId)}` : "";

  return (
    <RailFrame>
      <RailEntityHeader
        id={requestId}
        title={title}
        pills={<span className={`rd-v2-pill${state.label === "Recovery required" ? " fail" : state.label === "Approval required" ? " warn" : ""}`}>{state.label}</span>}
        description={source}
      />
      <RailDecisionSummary status={state.label} primary={state.explanation} risk={state.risk} next={state.next} />
      <div className="rd-v2-rail-scroll">
        <RailFieldGrid>
          <RailField label="Latest durable update" value={updatedAt(event)} />
          <RailField label="Recorded event" value={text(event.kind || event.action || "discover")} />
          {meta.summary || event.summary ? <RailField label="Evidence" value={meta.summary || event.summary} /> : null}
          {datasetId ? <RailField label="Dataset" value={datasetId} mono /> : null}
          {meta.registry_id || event.registry_id ? <RailField label="Registry" value={meta.registry_id || event.registry_id} mono /> : null}
          {meta.manifest_id || event.manifest_id ? <RailField label="Manifest" value={meta.manifest_id || event.manifest_id} mono /> : null}
          {meta.job_id || event.job_id ? <RailField label="Job" value={meta.job_id || event.job_id} mono /> : null}
          {meta.archive_verified != null || event.archive_verified != null ? (
            <RailField label="Archive" value={proofLabel(meta.archive_verified ?? event.archive_verified)} />
          ) : null}
          {meta.registry_readback != null || event.registry_readback != null ? (
            <RailField label="Registry read-back" value={proofLabel(meta.registry_readback ?? event.registry_readback)} />
          ) : null}
          {meta.catalog_reconciliation?.state || event.catalog_reconciliation?.state ? (
            <RailField
              label="Catalog state"
              value={text(meta.catalog_reconciliation?.state || event.catalog_reconciliation?.state)}
            />
          ) : null}
          {meta.cadence || event.cadence ? <RailField label="Schedule" value={meta.cadence || event.cadence} /> : null}
          {meta.requested_schedule || event.requested_schedule ? (
            <RailField label="Requested cadence" value={meta.requested_schedule || event.requested_schedule} />
          ) : null}
          {meta.execution_mode ? <RailField label="Execution mode" value={text(meta.execution_mode)} /> : null}
        </RailFieldGrid>
      </div>
      <RailStickyFooter>
        {canReview ? (
          <button type="button" className="rd-v2-btn sm primary" onClick={() => onReviewRequest?.(job || event)}>
            Review request
          </button>
        ) : null}
        {registered && libraryHref ? (
          <a className="rd-v2-btn sm primary" href={libraryHref}>
            Open in Library
          </a>
        ) : null}
        <button
          type="button"
          className="rd-v2-btn sm"
          onClick={() => onAskAbout?.({ ...event, title, kind: "discover_history" })}
        >
          Ask about this
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}
