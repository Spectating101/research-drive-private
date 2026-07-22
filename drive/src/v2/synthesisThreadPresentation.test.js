import test from "node:test";
import assert from "node:assert/strict";
import {
  constructionStateFromThread,
  isSynthesisThreadsUnavailableError,
  presentLocalDraftFallback,
  presentSynthesisThread,
  previewStateFromProposal,
} from "./synthesisThreadPresentation.js";

const emptyThread = {
  id: "tid-1",
  title: "Attention measure",
  objective: "Construct a durable attention signal.",
  materialisation: "not_materialised",
  session_id: "syn-sess-1",
  state: {
    title: "Attention measure",
    objective: "Construct a durable attention signal.",
    required_grain: "asset-week",
    nodes: [],
    edges: [],
    proposal: null,
    spec: { grain: "asset-week", coreEvidence: [], validation: [] },
    activity: [{ time: "Now", kind: "create", message: "Synthesis thread created." }],
    execution: {},
  },
};

const proposal = {
  id: "gdelt-validation",
  title: "Use GDELT as a validation signal",
  summary: "Add Trends + GDELT without claiming output.",
  proposal_hash: "abc123",
  operations: [
    {
      op: "add_node",
      node: {
        id: "trends",
        type: "source",
        layer: "evidence",
        label: "Google Trends",
        status: "held",
      },
    },
    {
      op: "add_node",
      node: {
        id: "gdelt",
        type: "source",
        layer: "evidence",
        label: "GDELT",
        status: "proposed",
      },
    },
    {
      op: "update_spec",
      patch: { grain: "asset-week", coreEvidence: ["Google Trends"], validation: ["GDELT"] },
    },
  ],
};

test("empty durable thread stays unformed until a proposal arrives", () => {
  assert.equal(constructionStateFromThread(emptyThread), "empty");
  const view = presentSynthesisThread(emptyThread);
  assert.equal(view.constructionState, "empty");
  assert.equal(view.proposal, null);
  assert.equal(view.nodeSummaries.inputs, "Inputs not mapped");
  assert.equal(view.nodeSummaries.method, "Method not proposed");
  assert.equal(view.outputProven, false);
  assert.equal(view.dataAvailable, false);
  assert.equal(view.sessionId, "syn-sess-1");
});

test("proposal preview maps Model/Spec as proposed without mutating durable nodes", () => {
  const thread = {
    ...emptyThread,
    state: { ...emptyThread.state, proposal },
  };
  assert.equal(constructionStateFromThread(thread), "proposed");
  const view = presentSynthesisThread(thread);
  assert.equal(view.constructionState, "proposed");
  assert.equal(view.proposal.id, "gdelt-validation");
  assert.equal(view.proposal.proposalHash, "abc123");
  assert.deepEqual(view.sources, ["Google Trends", "GDELT"]);
  assert.equal(view.grain, "asset-week");
  assert.match(view.nodeSummaries.validation, /GDELT/);
  assert.equal(thread.state.nodes.length, 0);
  assert.equal(view.outputProven, false);
});

test("previewStateFromProposal applies controlled ops only", () => {
  const preview = previewStateFromProposal(emptyThread.state, proposal);
  assert.equal(preview.nodes.length, 2);
  assert.deepEqual(preview.spec.coreEvidence, ["Google Trends"]);
});

test("accepted thread with nodes reports accepted; output stays unproven without execution", () => {
  const thread = {
    ...emptyThread,
    state: {
      ...emptyThread.state,
      proposal: null,
      nodes: [
        { id: "trends", type: "source", layer: "evidence", label: "Google Trends", status: "held" },
      ],
      execution: { status: "not_requested" },
    },
  };
  const view = presentSynthesisThread(thread);
  assert.equal(view.constructionState, "accepted");
  assert.equal(view.outputProven, false);
  assert.equal(view.outputId, "");
});

test("registered execution evidence unlocks output identity", () => {
  const thread = {
    ...emptyThread,
    materialisation: "registered",
    state: {
      ...emptyThread.state,
      proposal: null,
      nodes: [{ id: "trends", type: "source", layer: "evidence", label: "Google Trends" }],
      execution: {
        status: "registered",
        output_dataset_id: "attention_proxy_v1",
        drive_verified: true,
      },
    },
  };
  const view = presentSynthesisThread(thread);
  assert.equal(view.constructionState, "accepted");
  assert.equal(view.outputProven, true);
  assert.equal(view.outputId, "attention_proxy_v1");
});

test("local-draft fallback stays clearly local and empty without a recorded need", () => {
  const view = presentLocalDraftFallback();
  assert.equal(view.localDraft, true);
  assert.equal(view.constructionState, "empty");
  assert.equal(view.id, "local-draft");
  assert.match(view.maturityLabel, /Local current-session draft/);
});

test("threads unavailable detector covers fetch and 404 failures", () => {
  assert.equal(isSynthesisThreadsUnavailableError(new Error("404 /library/synthesis/threads")), true);
  assert.equal(isSynthesisThreadsUnavailableError(new Error("Failed to fetch")), true);
  assert.equal(isSynthesisThreadsUnavailableError(new Error("proposal_hash required")), false);
});
