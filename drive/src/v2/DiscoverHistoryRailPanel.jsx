import { EmptyRailState } from "@/v2/EmptyRailState";
import { RailDecisionSummary, RailEntityHeader, RailField, RailFieldGrid, RailFrame, RailStickyFooter } from "@/v2/RailFrame";

function text(value) {
  return String(value || "").replace(/_/g, " ").trim();
}

function historyState(event) {
  const status = String(event?.status || event?.meta?.status || "").toLowerCase();
  const kind = String(event?.kind || event?.action || "").toLowerCase();
  const meta = event?.meta || {};

  if (kind === "subscription" || /scheduled|paused|subscription/.test(status)) {
    return {
      label: "Scheduled refresh",
      explanation: event?.meta?.execution_mode === "non_executing"
        ? "The refresh request is recorded. Automatic execution is not claimed."
        : "The refresh schedule is recorded for this evidence object.",
      risk: "Confirm execution mode before relying on automatic refresh.",
      next: "Review the schedule or ask about its scope.",
    };
  }
  if (/pending_approval|ready_for_review|awaiting|needs_approval/.test(status) || kind === "intent") {
    return {
      label: "Approval required",
      explanation: "This evidence request is waiting for a researcher decision before collection begins.",
      risk: "No collection has started.",
      next: "Review the source and the exact request before approval.",
    };
  }
  if (/queued|running|active|in_progress/.test(status)) {
    return {
      label: status === "queued" ? "Queued" : "Collecting",
      explanation: status === "queued"
        ? "The approved request is waiting for a worker."
        : "Collection is active. The current evidence below is the last durable update.",
      risk: "Output is not yet a registered Library asset.",
      next: "Track progress until archive and registry evidence are confirmed.",
    };
  }
  if (/failed|error|needs_recovery|blocked/.test(status)) {
    return {
      label: "Recovery required",
      explanation: "The latest execution did not complete. Existing request evidence is preserved.",
      risk: "Do not treat the output as registered or query-ready.",
      next: "Inspect the failure and create a revised request if the route changed.",
    };
  }
  if (/query[_ -]?ready/.test(status)) {
    return {
      label: "Query ready",
      explanation: "The registered asset has an explicit query-ready authority state.",
      risk: "Use the recorded query evidence rather than inferring readiness from registration alone.",
      next: "Open the asset in Library or inspect its query evidence.",
    };
  }
  if (status === "registered" || kind === "registered_asset") {
    const archive = meta.archive_verified === true || event?.archive_verified === true;
    const readback = meta.registry_readback === true || event?.registry_readback === true;
    return {
      label: "Registered",
      explanation: archive && readback
        ? "Archive verification and canonical registry read-back both succeeded for this Library asset."
        : "The durable record reports registration; inspect its proof fields before reuse.",
      risk: "Registered is not Query ready. No query capability is claimed here.",
      next: "Open the exact Library asset or ask about its provenance and readiness gap.",
    };
  }
  if (/completed|ready|archived|done|succeeded/.test(status)) {
    return {
      label: "Completed",
      explanation: "The latest durable record reports completion. Verify registry/readiness evidence before reuse.",
      risk: "Completion alone does not imply registration or query readiness.",
      next: "Inspect the output and its supporting evidence.",
    };
  }
  return {
    label: "Route investigating",
    explanation: "The evidence request exists while Research Drive determines a viable acquisition route.",
    risk: "Acquisition method is not established.",
    next: "Investigate available source and access routes.",
  };
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
