import assert from "node:assert/strict";
import test from "node:test";

import { createRequestAbort, decodeNdjson, normalizeApiError } from "./transportContract.js";

test("decodes a final NDJSON event without a trailing newline", () => {
  const first = decodeNdjson("", '{"type":"delta","text":"hello"}\n{"type":"complete"');
  assert.equal(first.events.length, 1);
  const final = decodeNdjson(first.buffer, "}", { final: true });
  assert.deepEqual(final.events, [{ type: "complete" }]);
  assert.equal(final.buffer, "");
});

test("normalizes FastAPI detail payloads", () => {
  assert.equal(normalizeApiError({ detail: "invalid attempt" }, 409, "/jobs/1"), "invalid attempt");
  assert.equal(
    normalizeApiError({ detail: [{ msg: "worker_id required" }, { msg: "attempt required" }] }, 422, "/jobs/1"),
    "worker_id required; attempt required",
  );
});

test("creates an abort signal for bounded requests", async () => {
  const request = createRequestAbort(5);
  await new Promise((resolve) => request.signal.addEventListener("abort", resolve, { once: true }));
  assert.equal(request.timedOut(), true);
  request.cancel();
});
