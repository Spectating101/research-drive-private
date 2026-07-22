import {
  RailActionFooter,
  RailEntityHeader,
  RailEvidenceDetails,
  RailFactSection,
  RailFrame,
  RailJudgment,
} from "@/v2/RailFrame";
import { PAGE_DETAIL_EMPTY } from "@/v2/discoverRailPresentation";
import { EmptyRailState } from "@/v2/EmptyRailState";

function text(value, fallback = "") {
  return String(value || "").trim() || fallback;
}

function lifecycleOf(thread) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  if (thread?.localDraft || execution.status === "local_draft") return "local_draft";
  const raw = text(execution.status || thread?.materialisation).toLowerCase().replace(/-/g, "_");
  if (raw === "query_ready") return "query_ready";
  if (raw === "registered") return "registered";
  if (raw === "failed") return "failed";
  if (execution.status && execution.status !== "not_requested") return "execution";
  if (state.proposal) return "proposal";
  return "explore";
}

function pushFact(list, label, value) {
  const v = text(value, "");
  if (!v) return;
  list.push({ label, value: v });
}

function buildNodeRail(thread) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const localDraft = Boolean(thread?.localDraft);
  const mode = lifecycleOf(thread);
  const outputId = execution.output_dataset_id || state.execution_spec?.output_dataset_id || "";
  const sources = Array.isArray(state.sources)
    ? state.sources.filter(Boolean)
    : (state.nodes || [])
        .filter((node) => node?.layer === "evidence" || node?.type === "source" || node?.type === "construct")
        .map((node) => node.label || node.dataset_id)
        .filter(Boolean);
  const joinKeys = Array.isArray(state.joinKeys) ? state.joinKeys.filter(Boolean) : [];
  const selectedEvidence = text(state.selectedEvidence || "", "");
  const constructionState = text(state.constructionState || state.proposalState, "empty");
  const proposal = state.proposal;

  const confirmed = [];
  pushFact(
    confirmed,
    "Construction",
    constructionState === "accepted"
      ? "Accepted"
      : constructionState === "proposed"
        ? "Proposed"
        : selectedEvidence
          ? `Evidence · ${selectedEvidence}`
          : mode === "local_draft"
            ? "Local draft"
            : text(state.maturityLabel || state.maturity, "Exploring"),
  );
  pushFact(
    confirmed,
    "Selected",
    selectedEvidence
      ? `Evidence · ${selectedEvidence}`
      : `${state.selectedStepLabel || "Inputs"}${state.selectedStepSummary ? ` · ${state.selectedStepSummary}` : ""}`,
  );
  pushFact(confirmed, "Detail", state.selectedStepDetail);
  pushFact(confirmed, "Evidence", selectedEvidence || (sources.length ? sources.join(" · ") : ""));
  pushFact(confirmed, "Method", joinKeys.length ? joinKeys.join(" + ") : "");
  pushFact(confirmed, "Grain", state.grain || state.required_grain || state.spec?.grain);
  pushFact(confirmed, "Proposal", proposal?.title);
  pushFact(confirmed, "Execution", execution.status && execution.status !== "not_requested" ? execution.status : "");
  pushFact(confirmed, "Output", outputId);

  const unknowns = [];
  if (!sources.length && !selectedEvidence) pushFact(unknowns, "Evidence", "No inputs mapped");
  if (!joinKeys.length && !state.grain && !state.required_grain) {
    pushFact(unknowns, "Method", "Join / grain not reported");
  }
  if (!outputId) pushFact(unknowns, "Output", "Not registered");
  if (localDraft) pushFact(unknowns, "Persistence", "Local only — Composer integration is not durable yet");

  let judgment;
  if (localDraft) {
    judgment = state.recordedNeed
      ? `Local draft · ${state.recordedNeed}`
      : "Local draft — no research need recorded for this session yet.";
  } else if (mode === "failed") {
    judgment = text(execution.error, "Execution failed — inspect the recorded failure.");
  } else if (mode === "query_ready" || mode === "registered") {
    judgment = "Construction has a registered output — open the asset in Library.";
  } else if (selectedEvidence) {
    judgment = `Selected construction evidence · ${selectedEvidence}.`;
  } else if (state.selectedStepLabel) {
    judgment = `Selected construction node · ${state.selectedStepLabel}.`;
  } else {
    judgment = "Selected construction facts only — Composer remains the place to propose changes.";
  }

  return {
    title: selectedEvidence
      ? `Evidence · ${selectedEvidence}`
      : localDraft
        ? "Local current-session draft"
        : thread?.title || state.title || "Synthesis",
    judgment,
    confirmed,
    unknowns,
    outputId,
    localDraft,
    registered: mode === "registered" || mode === "query_ready",
    proposal,
    stepDetail: selectedEvidence
      ? `Evidence: ${selectedEvidence}`
      : `${state.selectedStepLabel || "Inputs"}: ${state.selectedStepDetail || "No detail reported"}`,
  };
}

function WorkbenchRailPanel({ thread, onAskAbout, onOpenInLibrary }) {
  const rail = buildNodeRail(thread);
  return (
    <div data-testid="synthesis-rail-panel">
      <RailFrame>
        <RailEntityHeader compact title={rail.title} />
        {rail.localDraft ? (
          <p className="muted small" data-testid="synthesis-rail-local-draft">
            Local current-session draft · local only
            {thread?.state?.recordedNeed ? ` · ${thread.state.recordedNeed}` : " · no need recorded yet"}.
          </p>
        ) : null}
        <RailJudgment>{rail.judgment}</RailJudgment>
        <div className="rd-v2-rail-scroll">
          <RailFactSection title="Confirmed" items={rail.confirmed} testId="rail-confirmed" />
          <RailFactSection title="Unknown" items={rail.unknowns} testId="rail-unknown" />
          <div data-testid="synthesis-rail-step-detail" className="muted small">
            {rail.stepDetail}
          </div>
          {rail.proposal?.title ? (
            <RailEvidenceDetails label="Proposal evidence" defaultOpen>
              <p className="rd-v2-rail-judgment-text">{rail.proposal.summary || rail.proposal.title}</p>
            </RailEvidenceDetails>
          ) : null}
        </div>
        <RailActionFooter
          primary={
            rail.outputId && !rail.localDraft
              ? {
                  key: "open",
                  label: "Open in Library",
                  onClick: () => onOpenInLibrary?.({ dataset_id: rail.outputId, name: rail.outputId }),
                }
              : {
                  key: "composer",
                  label: "Discuss in Composer",
                  onClick: onAskAbout,
                }
          }
          secondary={
            rail.outputId && !rail.localDraft
              ? [{ key: "composer", label: "Discuss in Composer", onClick: onAskAbout }]
              : []
          }
        />
      </RailFrame>
    </div>
  );
}

export function SynthesisThreadRailPanel({ thread, onAskAbout, onOpenInLibrary }) {
  if (!thread) {
    return (
      <RailFrame>
        <div className="rd-v2-rail-scroll">
          <EmptyRailState title={PAGE_DETAIL_EMPTY.synthesis} minimal />
        </div>
      </RailFrame>
    );
  }

  const state = thread?.state || {};
  if (state.workbench || thread?.localDraft != null) {
    return (
      <WorkbenchRailPanel thread={thread} onAskAbout={onAskAbout} onOpenInLibrary={onOpenInLibrary} />
    );
  }

  const rail = buildNodeRail(thread);
  const mode = lifecycleOf(thread);

  return (
    <RailFrame>
      <RailEntityHeader compact title={rail.title} />
      <RailJudgment>{rail.judgment}</RailJudgment>
      <div className="rd-v2-rail-scroll">
        <RailFactSection title="Confirmed" items={rail.confirmed} testId="rail-confirmed" />
        <RailFactSection title="Unknown" items={rail.unknowns} testId="rail-unknown" />
        {rail.proposal?.title ? (
          <div data-testid="synthesis-rail-proposal" className="muted small">
            {rail.proposal.summary || rail.proposal.title}
          </div>
        ) : null}
      </div>
      <RailActionFooter
        primary={
          rail.outputId && rail.registered
            ? {
                key: "open",
                label: "Open in Library",
                onClick: () =>
                  onOpenInLibrary?.({
                    dataset_id: rail.outputId,
                    name: rail.outputId,
                    analysis_readiness: mode === "query_ready" ? "instant" : undefined,
                  }),
              }
            : {
                key: "composer",
                label: "Discuss in Composer",
                onClick: onAskAbout,
              }
        }
        secondary={
          rail.outputId && rail.registered
            ? [{ key: "composer", label: "Discuss in Composer", onClick: onAskAbout }]
            : []
        }
      />
    </RailFrame>
  );
}
