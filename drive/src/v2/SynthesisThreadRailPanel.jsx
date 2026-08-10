import {
  RailDecisionSummary,
  RailEntityHeader,
  RailField,
  RailFieldGrid,
  RailFrame,
  RailStickyFooter,
} from "@/v2/RailFrame";

function text(value, fallback = "Not reported") {
  return String(value || "").trim() || fallback;
}

function stateSummary(thread) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const registered = execution.status === "registered" || thread?.materialisation === "registered";
  if (registered) {
    return {
      status: "Registered output",
      primary: "Open the reusable asset",
      risk: execution.drive_verified ? "Drive verification reported" : "Verification detail not reported",
      next: "Inspect the registered asset in Library",
    };
  }
  if (execution.status === "failed") {
    return {
      status: "Execution failed",
      primary: "Inspect the recorded failure",
      risk: text(execution.error, "Failure detail not reported"),
      next: "Revise or retry the accepted specification",
    };
  }
  if (execution.status) {
    return {
      status: execution.status.replace(/_/g, " "),
      primary: "Follow the execution record",
      risk: "No registered output is claimed yet",
      next: "Wait for durable execution evidence",
    };
  }
  if (state.proposal) {
    return {
      status: "Proposal needs review",
      primary: "Inspect the proposed change",
      risk: "No method change is accepted yet",
      next: "Accept or reject the exact proposal",
    };
  }
  return {
    status: text(state.maturityLabel || state.maturity, "Exploring"),
    primary: "Continue the research construction",
    risk: "No output is registered",
    next: "Use Ask to constrain or propose the next method change",
  };
}

export function SynthesisThreadRailPanel({ thread, onAskAbout, onOpenInLibrary }) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const outputId = execution.output_dataset_id || state.execution_spec?.output_dataset_id || "";
  const summary = stateSummary(thread);
  const sources = (state.nodes || [])
    .filter((node) => node?.layer === "evidence" || node?.type === "source" || node?.type === "construct")
    .map((node) => node.label || node.dataset_id)
    .filter(Boolean);
  // A method can be proposed or accepted before its input ever becomes a
  // mapped evidence node (state.nodes stays empty through that whole path).
  // "No inputs mapped" would then sit next to a proposal/execution record
  // that names a specific input dataset — a real, verified contradiction,
  // not just a missing-data default. Distinguish declared-but-unmapped from
  // genuinely nothing yet, and keep "accepted" vs "proposed" honest rather
  // than folding either into the verified "mapped inputs" count.
  const specInput = state.execution_spec?.input_dataset_id || state.proposal?.execution_spec?.input_dataset_id || "";
  const evidenceValue = sources.length
    ? `${sources.length} mapped inputs`
    : specInput
      ? `Declared input · ${state.execution_spec ? "accepted" : "proposed"}: ${specInput}`
      : "No inputs mapped";

  return (
    <RailFrame>
      <RailEntityHeader
        title={thread?.title || state.title || "Synthesis thread"}
        description={thread?.objective || state.objective || "A durable research-construction thread."}
      />
      <RailDecisionSummary {...summary} />
      <RailFieldGrid>
        <RailField label="Grain" value={state.required_grain || state.spec?.grain} />
        <RailField label="Evidence" value={evidenceValue} />
        <RailField label="Proposal" value={state.proposal?.title || "No proposal awaiting review"} />
        <RailField label="Execution" value={execution.status || "Not requested"} />
        <RailField label="Output" value={outputId || "Not registered"} mono={Boolean(outputId)} />
        <RailField label="Manifest" value={execution.manifest_id || "Not reported"} mono={Boolean(execution.manifest_id)} />
      </RailFieldGrid>
      <RailStickyFooter>
        {outputId && (execution.status === "registered" || thread?.materialisation === "registered") ? (
          <button
            type="button"
            className="rd-v2-btn primary"
            onClick={() => onOpenInLibrary?.({ dataset_id: outputId, name: outputId, analysis_readiness: "instant" })}
          >
            Open in Library
          </button>
        ) : null}
        <button type="button" className="rd-v2-btn" onClick={onAskAbout}>
          Ask about this thread
        </button>
      </RailStickyFooter>
    </RailFrame>
  );
}
