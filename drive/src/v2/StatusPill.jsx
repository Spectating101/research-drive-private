import { RichContextHelp } from "@/v2/InteractionGuidance";
import { statusPillKind } from "@/v2/datasetMeta";

const STYLES = {
  "query-ready": "rd-v2-status-pill rd-v2-status-ready",
  registered: "rd-v2-status-pill rd-v2-status-connected",
  connected: "rd-v2-status-pill rd-v2-status-connected",
  review: "rd-v2-status-pill rd-v2-status-review",
  failed: "rd-v2-status-pill rd-v2-status-failed",
  external: "rd-v2-status-pill rd-v2-status-external",
  remote: "rd-v2-status-pill rd-v2-status-external",
  unknown: "rd-v2-status-pill rd-v2-status-unknown",
  queued: "rd-v2-status-pill rd-v2-status-review",
  warn: "rd-v2-status-pill rd-v2-status-review",
};

const GUIDANCE = {
  "query-ready": {
    title: "Query ready",
    summary: "This asset has passed the checks needed for analysis inside Research Drive.",
    checks: [
      "A durable registry identity is available",
      "Local or connected query authority is reconciled",
      "The current desk is permitted to analyse it",
    ],
    next: "Preview rows, ask a grounded question, or use it in Synthesis.",
  },
  registered: {
    title: "Registered",
    summary: "The asset is durably archived and registered, but Research Drive has not promoted it to Query ready.",
    checks: [
      "Archive and registry identity are available",
      "Provenance can be inspected in Detail",
      "Query readiness remains a separate evidence claim",
    ],
    next: "Inspect files or preview support without relabelling the asset Query ready.",
  },
  connected: {
    title: "Connected source",
    summary: "Research Drive can reach this source through a connector or remote service, but may not own the bytes locally.",
    checks: [
      "A route to the source is known",
      "Availability may depend on credentials or an upstream service",
      "Local archival and licensing still require confirmation",
    ],
    next: "Open Detail to inspect access, authority, and collection options.",
  },
  review: {
    title: "Review required",
    summary: "A researcher decision is required before the item can advance.",
    checks: [
      "The system has stopped before a material action",
      "Source, cost, destination, or access may need confirmation",
      "No approval is implied by this status",
    ],
    next: "Review the evidence and approve only when the proposed action is acceptable.",
  },
  failed: {
    title: "Operation failed",
    summary: "The latest attempt did not complete successfully.",
    checks: [
      "The failure is retained rather than hidden",
      "Identifiers and evidence remain available in Detail",
      "A retry should not upgrade the current readiness claim",
    ],
    next: "Inspect the recorded error and retry only after correcting the cause.",
  },
  external: {
    title: "Beyond your Library",
    summary: "This source is known outside your current Library.",
    checks: [
      "The source has not been claimed as locally owned",
      "Access and licensing may still need verification",
      "Collection requires an explicit route or proposal",
    ],
    next: "Probe the source or ask Research Drive for the safest acquisition path.",
  },
  remote: {
    title: "Remote query",
    summary: "The data is queried upstream rather than stored in the lab archive.",
    checks: [
      "Results depend on upstream availability",
      "The lab may retain metadata without retaining the source bytes",
      "Remote access does not imply durable archival",
    ],
    next: "Confirm limits and decide whether a durable local copy is required.",
  },
  queued: {
    title: "Queued",
    summary: "The request has been accepted into the work queue but is not currently executing.",
    checks: [
      "A durable work item exists",
      "No running worker is implied",
      "Queue position and approval requirements may still change",
    ],
    next: "Track the item in Resources or Discover History.",
  },
  warn: {
    title: "Condition needs attention",
    summary: "The item is available with a condition that still needs review.",
    checks: [
      "The current state is usable only within its stated limitation",
      "The warning is not a failure",
      "The condition should remain visible in downstream work",
    ],
    next: "Open Detail and resolve or document the condition before relying on it.",
  },
  unknown: {
    title: "Readiness unknown",
    summary: "Research Drive cannot yet prove this asset's readiness state.",
    checks: [
      "No positive readiness claim is being fabricated",
      "Metadata may still be incomplete or stale",
      "The asset should not silently enter analysis",
    ],
    next: "Refresh or inspect the source, registry, and query evidence.",
  },
};

export function StatusPill({ dataset, label }) {
  const state = statusPillKind(dataset);
  const text = label || state.label;
  const kind = state.kind;
  const cls = STYLES[kind] || STYLES.unknown;
  const guidance = GUIDANCE[kind] || GUIDANCE.unknown;
  return (
    <span className={cls}>
      <span className="rd-v2-status-dot" aria-hidden />
      <span>{text}</span>
      <RichContextHelp {...guidance} label={`Explain ${text}`} />
    </span>
  );
}
