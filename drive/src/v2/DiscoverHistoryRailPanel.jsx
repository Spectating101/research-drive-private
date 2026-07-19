import { EmptyRailState } from "@/v2/EmptyRailState";
import { RailDecisionSummary, RailEntityHeader, RailField, RailFieldGrid, RailFrame, RailStickyFooter } from "@/v2/RailFrame";

function text(value) {
  return String(value || "").replace(/_/g, " ").trim();
}

function historyState(event) {
  const status = String(event?.status || event?.meta?.status || "").toLowerCase();
  const kind = String(event?.kind || event?.action || "").toLowerCase();

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
  if (/completed|ready|registered|archived|done|succeeded/.test(status)) {
    return {
      label: /query[_ -]?ready/.test(status) ? "Query ready" : "Completed",
      explanation: "The latest durable record reports completion. Verify registry/readiness evidence before reuse.",
      risk: "Completion alone does not imply query readiness.",
      next: "Inspect the registered asset or its supporting evidence.",
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
  const source = meta.source_id || meta.candidate_key || meta.intent_id || "Durable Discover record";
  const requestId = meta.intent_id || meta.job_id || meta.subscription_id || event.id || "";
  const canReview = state.label === "Approval required" && Boolean(job?.id || meta.job_id);

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
