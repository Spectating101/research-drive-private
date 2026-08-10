import test from "node:test";
import assert from "node:assert/strict";
import {
  executionPrimaryAction,
  stateFor,
  threadCreatedCardModel,
} from "./synthesisWorkspace.js";

test("fresh objective threads land in draft, not explore/blueprint", () => {
  const thread = {
    id: "thread-new",
    title: "Weekly issuer attention panel",
    objective: "Build a weekly issuer attention panel for Taiwan filings.",
    state: {
      objective: "Build a weekly issuer attention panel for Taiwan filings.",
      required_grain: "issuer × week",
      maturity: "exploring",
      maturityLabel: "Exploring",
      nodes: [],
      proposal: null,
      execution: null,
    },
  };
  assert.equal(stateFor(thread), "draft");
  const card = threadCreatedCardModel(thread);
  assert.equal(card.eyebrow, "Thread created");
  assert.match(card.objective, /issuer attention/i);
  assert.equal(card.grain, "issuer × week");
  assert.match(card.truth, /Nothing has been accepted/i);
});

test("pending execution exposes only Approve and run as the material action", () => {
  const accepted = {
    state: {
      execution_spec: {
        input_dataset_id: "stablecoin_trust_engagement_weekly",
        output_dataset_id: "stablecoin_attention_weekly",
      },
      execution: null,
    },
  };
  assert.deepEqual(executionPrimaryAction(accepted), {
    kind: "approve_and_run",
    label: "Approve and run",
  });

  const pending = {
    state: {
      execution_spec: accepted.state.execution_spec,
      execution: { status: "pending_approval", job_id: "job-1" },
    },
  };
  assert.deepEqual(executionPrimaryAction(pending), {
    kind: "approve_and_run",
    label: "Approve and run",
  });

  const queued = {
    state: {
      execution_spec: accepted.state.execution_spec,
      execution: { status: "queued", job_id: "job-1" },
    },
  };
  assert.equal(executionPrimaryAction(queued), null);
});

test("registered and query-ready stay distinct open-library outcomes", () => {
  const registered = {
    materialisation: "registered",
    state: {
      execution_spec: {
        input_dataset_id: "in",
        output_dataset_id: "out",
      },
      execution: { status: "registered", output_dataset_id: "out" },
    },
  };
  assert.deepEqual(executionPrimaryAction(registered), {
    kind: "open_library",
    label: "Open in Library",
  });

  const queryReady = {
    materialisation: "query_ready",
    state: {
      execution_spec: {
        input_dataset_id: "in",
        output_dataset_id: "out",
      },
      execution: { status: "query_ready", output_dataset_id: "out" },
    },
  };
  assert.equal(stateFor(queryReady), "query_ready");
  assert.deepEqual(executionPrimaryAction(queryReady), {
    kind: "open_library",
    label: "Open in Library",
  });
});
