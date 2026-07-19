from __future__ import annotations

import json
from pathlib import Path


lifecycle_path = Path("drive/src/v2/executionLifecycle.js")
lifecycle = lifecycle_path.read_text(encoding="utf-8")
replacements = [
    (
        '''  ["registered", "registered"],
  ["query_ready", "registered"],
  ["materialized", "registered"],
  ["materialised", "registered"],
''',
        '''  ["registered", "registered"],
  ["query_ready", "query_ready"],
  ["queryable", "query_ready"],
  ["materialized", "completed"],
  ["materialised", "completed"],
''',
    ),
    ('  registered: "registered",\n  completed: "completed",', '  registered: "registered",\n  query_ready: "query-ready",\n  completed: "completed",'),
    ('  completed: 9,\n  registered: 9,', '  completed: 9,\n  registered: 9,\n  query_ready: 9,'),
    ('const TERMINAL_STAGES = new Set(["registered", "completed", "blocked", "failed"]);', 'const TERMINAL_STAGES = new Set(["query_ready", "registered", "completed", "blocked", "failed"]);'),
    (
        '''  const registryVerified =
    stage === "registered" ||
    truthy(
''',
        '''  const registryVerified =
    stage === "registered" ||
    stage === "query_ready" ||
    truthy(
''',
    ),
    (
        '''      registry_verified: registryVerified,
      rows: countValue''',
        '''      registry_verified: registryVerified,
      query_ready:
        stage === "query_ready" ||
        truthy(
          firstValue(
            job?.query_ready,
            job?.lifecycle?.query_ready,
            job?.execution?.query_ready,
            job?.registration?.query_ready,
          ),
        ),
      rows: countValue''',
    ),
]
for old, new in replacements:
    if lifecycle.count(old) != 1:
        raise SystemExit(f"execution lifecycle patch target count was {lifecycle.count(old)}")
    lifecycle = lifecycle.replace(old, new, 1)

start = lifecycle.index("export function normalizeSynthesisExecution(")
end = lifecycle.index("\nexport function isExecutionVisible", start)
lifecycle = lifecycle[:start] + '''export function normalizeSynthesisExecution(thread = {}) {
  const state = thread?.state || {};
  const execution = state.execution || {};
  const spec = state.execution_spec || execution.execution_spec || {};
  const materialisation = firstValue(thread?.materialisation, state?.materialisation, execution?.materialisation);
  const materialisationStage = normalizeStage(materialisation);
  const executionStage = normalizeStage(execution?.status);
  const status =
    materialisationStage === "query_ready"
      ? "query_ready"
      : materialisationStage === "registered"
        ? "registered"
        : firstValue(execution?.status, materialisation, "unknown");
  const resolvedStage = normalizeStage(status);
  const registered = resolvedStage === "registered" || resolvedStage === "query_ready";
  const outputId = firstValue(execution?.output_dataset_id, spec?.output_dataset_id);
  const inputIds = firstValue(execution?.inputs, spec?.input_dataset_ids, spec?.input_dataset_id);

  return normalizeExecutionLifecycle({
    ...execution,
    id: firstValue(execution?.job_id, execution?.run_id, thread?.id),
    job_id: firstValue(execution?.job_id, execution?.run_id),
    status: executionStage === "unknown" ? status : resolvedStage,
    inputs: inputIds,
    outputs: firstValue(execution?.outputs, outputId),
    manifest_id: firstValue(execution?.manifest_id, state?.manifest_id),
    drive_verified: firstValue(execution?.drive_verified, execution?.archive_verified),
    registry_verified: registered,
    query_ready: resolvedStage === "query_ready",
    registration_id: firstValue(execution?.registration_id, execution?.registry_id, outputId),
  });
}
''' + lifecycle[end:]
lifecycle_path.write_text(lifecycle, encoding="utf-8")

test_path = Path("drive/src/v2/executionLifecycle.test.js")
test_text = test_path.read_text(encoding="utf-8")
old_test = '''test("distinguishes completed execution from registered research asset", () => {
  const completed = normalizeExecutionLifecycle({ status: "succeeded", outputs: ["panel-v1"] });
  const registered = normalizeExecutionLifecycle({
    status: "registered",
    outputs: ["panel-v1"],
    manifest_id: "manifest-7",
    drive_verified: true,
    registration_id: "registry:panel-v1",
  });

  assert.equal(completed.stage, "completed");
  assert.equal(completed.proof.registry_verified, false);
  assert.equal(registered.stage, "registered");
  assert.equal(registered.terminal, true);
  assert.equal(registered.visible, false);
  assert.equal(registered.proof.manifest_id, "manifest-7");
  assert.equal(registered.proof.archive_verified, true);
  assert.equal(registered.proof.registry_verified, true);
});
'''
new_test = '''test("distinguishes completed, registered, and query-ready research assets", () => {
  const completed = normalizeExecutionLifecycle({ status: "materialized", outputs: ["panel-v1"] });
  const registered = normalizeExecutionLifecycle({
    status: "registered",
    outputs: ["panel-v1"],
    manifest_id: "manifest-7",
    drive_verified: true,
    registration_id: "registry:panel-v1",
  });
  const queryReady = normalizeExecutionLifecycle({
    status: "query_ready",
    outputs: ["panel-v1"],
    manifest_id: "manifest-7",
    drive_verified: true,
    registration_id: "registry:panel-v1",
  });

  assert.equal(completed.stage, "completed");
  assert.equal(completed.proof.registry_verified, false);
  assert.equal(completed.proof.query_ready, false);
  assert.equal(registered.stage, "registered");
  assert.equal(registered.terminal, true);
  assert.equal(registered.visible, false);
  assert.equal(registered.proof.manifest_id, "manifest-7");
  assert.equal(registered.proof.archive_verified, true);
  assert.equal(registered.proof.registry_verified, true);
  assert.equal(registered.proof.query_ready, false);
  assert.equal(queryReady.stage, "query_ready");
  assert.equal(queryReady.label, "query-ready");
  assert.equal(queryReady.proof.registry_verified, true);
  assert.equal(queryReady.proof.query_ready, true);
});
'''
if test_text.count(old_test) != 1:
    raise SystemExit("execution lifecycle test patch target missing")
test_text = test_text.replace(old_test, new_test, 1)
test_text += '''

test("Synthesis preserves query-ready beyond registration", () => {
  const result = normalizeSynthesisExecution({
    id: "syn-ready",
    materialisation: "query_ready",
    state: {
      execution_spec: { output_dataset_id: "ready-panel" },
      execution: { job_id: "job-ready", status: "completed", registry_id: "registry:ready-panel" },
    },
  });

  assert.equal(result.stage, "query_ready");
  assert.equal(result.proof.registration_id, "registry:ready-panel");
  assert.equal(result.proof.query_ready, true);
});
'''
test_path.write_text(test_text, encoding="utf-8")

Path("drive/src/v2/transportContract.js").write_text(
    '''function detailMessage(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "string" ? item : item?.msg || item?.message || ""))
      .filter(Boolean)
      .join("; ");
  }
  if (detail && typeof detail === "object") return detail.message || detail.msg || JSON.stringify(detail);
  return "";
}

export function normalizeApiError(data, status, path) {
  return data?.message || data?.error || detailMessage(data?.detail) || `${status || "Request failed"} ${path || ""}`.trim();
}

export function decodeNdjson(buffer = "", chunk = "", { final = false } = {}) {
  const combined = `${buffer || ""}${chunk || ""}`;
  const lines = combined.split("\\n");
  const remainder = final ? "" : lines.pop() || "";
  const events = lines
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line));
  return { events, buffer: remainder };
}

export function createRequestAbort(timeoutMs = 0, externalSignal = null) {
  const duration = Number(timeoutMs);
  if (!Number.isFinite(duration) || duration <= 0) {
    return { signal: externalSignal || undefined, cancel() {}, timedOut: () => false };
  }

  const controller = new AbortController();
  let timeoutTriggered = false;
  const forwardAbort = () => controller.abort(externalSignal?.reason);
  if (externalSignal?.aborted) forwardAbort();
  else externalSignal?.addEventListener("abort", forwardAbort, { once: true });
  const timer = setTimeout(() => {
    timeoutTriggered = true;
    controller.abort();
  }, duration);

  return {
    signal: controller.signal,
    timedOut: () => timeoutTriggered,
    cancel() {
      clearTimeout(timer);
      externalSignal?.removeEventListener("abort", forwardAbort);
    },
  };
}
''',
    encoding="utf-8",
)

Path("drive/src/v2/transportContract.test.js").write_text(
    '''import assert from "node:assert/strict";
import test from "node:test";

import { createRequestAbort, decodeNdjson, normalizeApiError } from "./transportContract.js";

test("decodes a final NDJSON event without a trailing newline", () => {
  const first = decodeNdjson("", '{"type":"delta","text":"hello"}\\n{"type":"complete"');
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
''',
    encoding="utf-8",
)

api_path = Path("drive/src/v2/api.js")
api = api_path.read_text(encoding="utf-8")
import_line = 'import { deskHeaders, loadChatSessionId, loadUserEmail, saveChatSessionId } from "@/v2/deskSession";\n'
if api.count(import_line) != 1:
    raise SystemExit("api import target missing")
api = api.replace(import_line, import_line + 'import { createRequestAbort, decodeNdjson, normalizeApiError } from "./transportContract.js";\n', 1)
fetch_start = api.index("export async function fetchJson(")
fetch_end = api.index("\nexport function listDatasets", fetch_start)
api = api[:fetch_start] + '''export async function fetchJson(path, init = {}) {
  const options = { ...(init || {}) };
  const timeoutMs = Number(options.timeoutMs || 0);
  delete options.timeoutMs;
  const requestAbort = createRequestAbort(timeoutMs, options.signal);
  if (requestAbort.signal) options.signal = requestAbort.signal;

  try {
    const r = await fetch(`${API}${path}`, options);
    const raw = await r.text();
    let data = {};
    if (raw) {
      try {
        data = JSON.parse(raw);
      } catch {
        data = { message: raw };
      }
    }
    if (!r.ok) throw new Error(normalizeApiError(data, r.status, path));
    return data;
  } catch (error) {
    if (requestAbort.timedOut()) throw new Error(`Request timed out after ${timeoutMs}ms: ${path}`);
    throw error;
  } finally {
    requestAbort.cancel();
  }
}
''' + api[fetch_end:]

chat_start = api.index("export async function sendChatMessage(")
chat_end = api.index("\nexport function openQueryInNewTab", chat_start)
api = api[:chat_start] + '''export async function sendChatMessage(
  message,
  { sessionId, userEmail, railContext, onDelta, onActivity } = {},
) {
  const body = JSON.stringify({
    message,
    session_id: sessionId || undefined,
    user_email: userEmail || loadUserEmail() || undefined,
    rail_context: railContext && typeof railContext === "object" ? railContext : undefined,
  });

  const consumeEvent = (event, state) => {
    if (event.type === "delta" && event.text) onDelta?.(event.text);
    if ((event.type === "activity" || event.type === "progress") && event.text) {
      onActivity?.({ text: event.text, action: event.action || null, elapsed_seconds: event.elapsed_seconds });
    }
    if (event.type === "error") throw new Error(event.message || event.error || "Chat stream error");
    if (event.type === "complete") state.result = event.result || null;
  };

  const streamRes = await fetch(`${API}/library/chat/stream`, {
    method: "POST",
    headers: deskHeaders(),
    body,
  });
  const contentType = streamRes.headers.get("content-type") || "";

  if (streamRes.ok && contentType.includes("ndjson") && streamRes.body) {
    const reader = streamRes.body.getReader();
    const decoder = new TextDecoder();
    const state = { result: null };
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const decoded = decodeNdjson(buffer, decoder.decode(value, { stream: true }));
      buffer = decoded.buffer;
      decoded.events.forEach((event) => consumeEvent(event, state));
    }
    const tail = decodeNdjson(buffer, decoder.decode(), { final: true });
    tail.events.forEach((event) => consumeEvent(event, state));
    if (!state.result) throw new Error("Chat ended without a response");
    if (state.result.session_id) saveChatSessionId(state.result.session_id);
    return state.result;
  }

  if (streamRes.ok) {
    const payload = await streamRes.json().catch(() => ({}));
    if (payload.session_id) saveChatSessionId(payload.session_id);
    return payload;
  }

  if (![404, 405, 406, 415].includes(streamRes.status)) {
    const streamError = await streamRes.json().catch(() => ({}));
    throw new Error(normalizeApiError(streamError, streamRes.status, "/library/chat/stream"));
  }

  const fallback = await fetch(`${API}/library/chat`, {
    method: "POST",
    headers: deskHeaders(),
    body,
  });
  const payload = await fallback.json().catch(() => ({}));
  if (!fallback.ok) throw new Error(normalizeApiError(payload, fallback.status, "/library/chat"));
  if (payload.session_id) saveChatSessionId(payload.session_id);
  return payload;
}
''' + api[chat_end:]
api_path.write_text(api, encoding="utf-8")

package_path = Path("package.json")
package = json.loads(package_path.read_text(encoding="utf-8"))
script = package["scripts"]["test:runtime-contract"]
if "transportContract.test.js" not in script:
    package["scripts"]["test:runtime-contract"] = script + " drive/src/v2/transportContract.test.js"
package_path.write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
