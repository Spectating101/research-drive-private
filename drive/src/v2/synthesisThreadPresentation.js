/** Map durable synthesis thread payloads into workbench / Composer view models. */

function text(value, fallback = "") {
  const out = String(value ?? "").trim();
  return out || fallback;
}

function cloneOps(proposal) {
  return Array.isArray(proposal?.operations) ? proposal.operations : [];
}

/** Preview construction after applying proposal ops in-memory (never mutates thread). */
export function previewStateFromProposal(threadState, proposal) {
  const base = {
    nodes: Array.isArray(threadState?.nodes) ? threadState.nodes.map((n) => ({ ...n })) : [],
    edges: Array.isArray(threadState?.edges) ? threadState.edges.map((e) => ({ ...e })) : [],
    spec: { ...(threadState?.spec || {}) },
  };
  for (const operation of cloneOps(proposal)) {
    const op = String(operation?.op || "");
    if (op === "add_node" && operation.node?.id) {
      if (!base.nodes.some((n) => n.id === operation.node.id)) {
        base.nodes.push({ ...operation.node });
      }
    } else if (op === "update_node" && operation.id) {
      const idx = base.nodes.findIndex((n) => n.id === operation.id);
      if (idx >= 0) base.nodes[idx] = { ...base.nodes[idx], ...(operation.patch || {}) };
    } else if (op === "remove_node" && operation.id) {
      base.nodes = base.nodes.filter((n) => n.id !== operation.id);
      base.edges = base.edges.filter((e) => e.source !== operation.id && e.target !== operation.id);
    } else if (op === "add_edge" && operation.edge?.id) {
      if (!base.edges.some((e) => e.id === operation.edge.id)) {
        base.edges.push({ ...operation.edge });
      }
    } else if (op === "update_edge" && operation.id) {
      const idx = base.edges.findIndex((e) => e.id === operation.id);
      if (idx >= 0) base.edges[idx] = { ...base.edges[idx], ...(operation.patch || {}) };
    } else if (op === "update_spec") {
      base.spec = { ...base.spec, ...(operation.patch || {}) };
    }
  }
  return base;
}

export function evidenceLabelsFromNodes(nodes) {
  return (nodes || [])
    .filter((n) => n && (n.layer === "evidence" || n.type === "source" || n.type === "construct"))
    .map((n) => text(n.label || n.dataset_id || n.id))
    .filter(Boolean);
}

export function constructionStateFromThread(thread) {
  if (!thread || thread.localDraft) {
    return thread?.state?.recordedNeed ? "proposed" : "empty";
  }
  const state = thread.state || {};
  const execution = state.execution || {};
  if (execution.status === "registered" || thread.materialisation === "registered") {
    return "accepted";
  }
  if (state.proposal && typeof state.proposal === "object") {
    return "proposed";
  }
  if (Array.isArray(state.nodes) && state.nodes.length) {
    return "accepted";
  }
  return "empty";
}

/**
 * Truthful workbench projection from a durable thread (or local-draft sentinel).
 * Does not invent construction from free text or profile metadata.
 */
export function presentSynthesisThread(thread, { selectedStep = "inputs", selectedEvidence = "" } = {}) {
  const localDraft = Boolean(thread?.localDraft);
  const state = thread?.state || {};
  const proposal = state.proposal && typeof state.proposal === "object" ? state.proposal : null;
  const constructionState = constructionStateFromThread(thread);
  const preview =
    constructionState === "proposed" && proposal
      ? previewStateFromProposal(state, proposal)
      : {
          nodes: Array.isArray(state.nodes) ? state.nodes : [],
          edges: Array.isArray(state.edges) ? state.edges : [],
          spec: state.spec || {},
        };

  const sources = evidenceLabelsFromNodes(preview.nodes);
  const grain = text(preview.spec?.grain || state.required_grain || state.spec?.grain);
  const execution = state.execution || {};
  const outputId = text(execution.output_dataset_id || "");
  const outputProven = Boolean(
    outputId &&
      (execution.status === "registered" ||
        execution.drive_verified ||
        thread?.materialisation === "registered"),
  );

  const nodeSummaries = {
    inputs:
      constructionState === "empty"
        ? "Inputs not mapped"
        : sources.length
          ? sources.join(" · ")
          : "Inputs not mapped",
    method:
      constructionState === "empty"
        ? "Method not proposed"
        : grain
          ? `Grain · ${grain}`
          : text(preview.spec?.construction?.[0], "Method pending"),
    validation:
      constructionState === "empty"
        ? "Validation pending"
        : Array.isArray(preview.spec?.validation) && preview.spec.validation.length
          ? preview.spec.validation.join(" · ")
          : "Validation pending",
    output: outputProven
      ? `Registered · ${outputId}`
      : constructionState === "empty"
        ? "Output not materialised"
        : "Not materialised",
  };

  return {
    id: thread?.id || (localDraft ? "local-draft" : ""),
    title: text(thread?.title || state.title, localDraft ? "New synthesis" : "Synthesis thread"),
    objective: text(thread?.objective || state.objective),
    localDraft,
    materialisation: text(thread?.materialisation || state.materialisation, "not_materialised"),
    sessionId: text(thread?.session_id),
    conversationId: text(thread?.conversation_id),
    constructionState,
    proposal: proposal
      ? {
          id: text(proposal.id),
          title: text(proposal.title, "Proposal"),
          summary: text(proposal.summary),
          proposalHash: text(proposal.proposal_hash),
          nodeId: text(proposal.nodeId || proposal.node_id),
          operations: cloneOps(proposal),
        }
      : null,
    sources,
    grain,
    spec: preview.spec || {},
    nodes: preview.nodes,
    edges: preview.edges,
    activity: Array.isArray(state.activity) ? state.activity : [],
    execution,
    outputProven,
    outputId: outputProven ? outputId : "",
    nodeSummaries,
    selectedStep,
    selectedEvidence,
    maturityLabel:
      localDraft
        ? "Local current-session draft · local only"
        : constructionState === "proposed"
          ? "Proposal awaiting review"
          : constructionState === "accepted"
            ? text(state.maturityLabel, "Accepted construction")
            : text(state.maturityLabel, "Exploring"),
    dataAvailable: false,
    review: text(
      state.lastActivity,
      constructionState === "proposed"
        ? "Proposal awaiting accept or reject."
        : constructionState === "empty"
          ? "No controlled proposal yet — Model stays unformed."
          : "Construction accepted; output not claimed without execution evidence.",
    ),
  };
}

export function presentLocalDraftFallback({ sessionNeed = "", selectedStep = "inputs" } = {}) {
  return presentSynthesisThread(
    {
      id: "local-draft",
      localDraft: true,
      title: "New synthesis",
      materialisation: "local_draft",
      state: {
        recordedNeed: sessionNeed,
        title: "New synthesis",
        objective: sessionNeed,
        maturityLabel: "Local current-session draft · local only",
        execution: { status: "local_draft" },
        proposal: null,
        nodes: [],
        edges: [],
        activity: [],
      },
    },
    { selectedStep },
  );
}

/** Detect whether list/create thread routes look available from an error message. */
export function isSynthesisThreadsUnavailableError(err) {
  const msg = String(err?.message || err || "").toLowerCase();
  return (
    /404/.test(msg) ||
    /not found/.test(msg) ||
    /unavailable/.test(msg) ||
    /failed to fetch/.test(msg) ||
    /network/.test(msg)
  );
}
