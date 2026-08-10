import test from "node:test";
import assert from "node:assert/strict";
import { classifyAskRecovery } from "./askRecovery.js";

test("provider linking failures become recoverable UI, not raw plumbing", () => {
  const recovery = classifyAskRecovery({
    errorCode: "CAPABILITY_UNAVAILABLE",
    recoverable: true,
    entityKind: "synthesis_thread",
  });
  assert.equal(recovery?.kind, "provider");
  assert.equal(recovery?.recoverable, true);
  assert.match(recovery.title, /provider/i);
  assert.match(recovery.detail, /objective is preserved/i);
});

test("backend Composer action envelopes become recoverable UI", () => {
  const recovery = classifyAskRecovery({
    action: "composer_timeout",
    entityKind: "synthesis_thread",
  });
  assert.equal(recovery?.kind, "provider");
  assert.equal(recovery?.recoverable, true);
});

test("synthesis context-received acknowledgements are not treated as answers", () => {
  const recovery = classifyAskRecovery({
    answerStatus: "context_ack",
    entityKind: "synthesis_thread",
  });
  assert.equal(recovery?.kind, "plumbing");
  assert.equal(recovery?.recoverable, true);
  assert.doesNotMatch(recovery.title, /context received/i);
});

test("grounded synthesis replies are left alone", () => {
  const recovery = classifyAskRecovery({
    answerStatus: "grounded",
    entityKind: "synthesis_thread",
  });
  assert.equal(recovery, null);
});

test("assistant wording alone never changes recovery state", () => {
  const recovery = classifyAskRecovery({
    text: "The provider boundary is part of the research limitation, not an outage.",
    entityKind: "synthesis_thread",
  });
  assert.equal(recovery, null);
});

test("non-synthesis context acknowledgements stay unchanged", () => {
  const recovery = classifyAskRecovery({
    answerStatus: "context_ack",
    entityKind: "external_candidate",
  });
  assert.equal(recovery, null);
});
