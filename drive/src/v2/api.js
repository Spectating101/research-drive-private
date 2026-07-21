/** Research Drive v2 — HTTP client (dev proxies /api → :8765 via vite.config.js). */

import {
  deskFetchInit,
  deskHeaders,
  deskSessionBootstrapped,
  loadChatSessionId,
  loadUserEmail,
  markDeskSessionBootstrapped,
  saveChatSessionId,
} from "@/v2/deskSession";
import { createRequestAbort, decodeNdjson, normalizeApiError } from "./transportContract.js";

export const API = import.meta.env.DEV ? "/api" : "";

export async function fetchJson(path, init = {}) {
  const options = deskFetchInit(init || {});
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

/** Same-origin HttpOnly desk session — no DevTools token injection required. */
export async function ensureDeskSession({ force = false } = {}) {
  if (!force && deskSessionBootstrapped()) {
    return { ok: true, bootstrapped: true, reused: true };
  }
  try {
    const data = await fetchJson("/library/desk/session", {
      method: "POST",
      body: JSON.stringify({}),
    });
    const ok = Boolean(data?.ok || data?.authorized);
    markDeskSessionBootstrapped(ok);
    return { ok, bootstrapped: ok, ...data };
  } catch (error) {
    markDeskSessionBootstrapped(false);
    return { ok: false, bootstrapped: false, error: String(error?.message || error) };
  }
}

export async function clearDeskSession() {
  markDeskSessionBootstrapped(false);
  try {
    return await fetchJson("/library/desk/session", {
      method: "POST",
      body: JSON.stringify({ action: "clear" }),
    });
  } catch {
    try {
      const r = await fetch(`${API}/library/desk/session`, deskFetchInit({ method: "DELETE" }));
      return r.json().catch(() => ({ ok: r.ok }));
    } catch (error) {
      return { ok: false, error: String(error?.message || error) };
    }
  }
}

export function listDatasets() {
  return fetchJson("/datasets").then((d) => d.datasets || []);
}

export function describeDataset(datasetId) {
  return fetchJson(`/datasets/${encodeURIComponent(datasetId)}`);
}

export function queryDataset(datasetId, limit = 50) {
  return fetchJson(`/query/${encodeURIComponent(datasetId)}?limit=${limit}`);
}

export function deskHealth(live = false) {
  const q = live ? "?live=1" : "";
  return fetchJson(`/health${q}`);
}

export function deskResources(live = true) {
  const q = live ? "?live=1" : "";
  return fetchJson(`/library/desk/resources${q}`);
}

export function discoverSearch(query = "", limit = 12, email = "") {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (email) params.set("email", email);
  return fetchJson(`/library/discover?${params}`);
}

export function webDiscover(query = "", limit = 8, tavilyLive = true) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (!tavilyLive) params.set("tavily", "0");
  return fetchJson(`/library/discover/web?${params}`);
}

/** Explore source catalogue — preferred Discover search contract when backend supports it. */
export function discoverSources(query = "", { limit = 12, live = false, prefer = "" } = {}) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (live) params.set("live", "1");
  if (prefer) params.set("prefer", prefer);
  return fetchJson(`/library/discover/sources?${params}`, { timeoutMs: 10000 });
}

/** Durable Discover history (intents / subscriptions / collection runs). */
export function discoverHistory({ limit = 50, kind = "", sessionId = "" } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (kind) params.set("kind", kind);
  if (sessionId) params.set("session_id", sessionId);
  return fetchJson(`/library/discover/history?${params}`, { timeoutMs: 8000 });
}

/** Bounded Explore source preview. */
export function previewDiscoverSource({
  sourceId = "",
  connectorId = "",
  candidateKey = "",
  url = "",
  datasetId = "",
  limit = 20,
} = {}) {
  return fetchJson("/library/discover/sources/preview", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      source_id: sourceId || undefined,
      connector_id: connectorId || undefined,
      candidate_key: candidateKey || undefined,
      url: url || undefined,
      dataset_id: datasetId || undefined,
      limit,
    }),
    timeoutMs: 15000,
  });
}

export function probePublicSource(url, name = "", { candidateKey = "" } = {}) {
  const body = { url, name };
  if (candidateKey) body.candidate_key = candidateKey;
  return fetchJson("/library/discover/probe", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify(body),
  });
}

export function submitDiscoverCollect(
  connectorId,
  {
    limit = 200,
    autoApprove = false,
    candidateKey = "",
    sourceIdentity = "",
    datasetId = "",
    doi = "",
    url = "",
  } = {},
) {
  const body = {
    connector_id: connectorId,
    limit,
    auto_approve: autoApprove,
  };
  if (candidateKey) body.candidate_key = candidateKey;
  if (sourceIdentity) body.source_identity = sourceIdentity;
  if (datasetId) body.dataset_id = datasetId;
  if (doi) body.doi = doi;
  if (url) body.url = url;
  return fetchJson("/library/discover/collect", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify(body),
  });
}

export function submitLibraryJob({ title, plan, autoApprove = false, request = {} }) {
  return fetchJson("/library/jobs", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      title,
      plan,
      request,
      auto_approve: autoApprove,
    }),
  });
}

export function unifiedSearch(query = "", limit = 12, email = "") {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (email) params.set("email", email);
  return fetchJson(`/library/search?${params}`);
}

export function facultyProfile(email = "") {
  const q = email ? `?email=${encodeURIComponent(email)}` : "";
  return fetchJson(`/library/faculty/profile${q}`);
}

export function libraryOps(lane = "") {
  const q = lane ? `?lane=${encodeURIComponent(lane)}` : "";
  return fetchJson(`/library/ops${q}`);
}

export function libraryOverview() {
  return fetchJson("/library/overview");
}

export function listPartitions() {
  return fetchJson("/library/partitions").then((d) => d.partitions || []);
}

export function procurementCatalogSummary() {
  return fetchJson("/library/catalog?limit=1").then((d) => d.summary || d);
}

export function yzuClusterStatus(live = true) {
  const q = live ? "?live=1" : "";
  return fetchJson(`/yzu/status${q}`);
}

export function listAcquisitions(live = true) {
  const q = live ? "?live=1" : "";
  return fetchJson(`/yzu/acquisitions${q}`);
}

export function listJobs() {
  return fetchJson("/library/jobs").then((d) => d.jobs || d.items || d || []);
}

/** RC2-A: sanitized cross-surface identity from the private factory / desk gateway. */
export function fetchLiveIdentity({ datasetId = "", jobId = "" } = {}) {
  const params = new URLSearchParams();
  if (datasetId) params.set("dataset_id", datasetId);
  if (jobId) params.set("job_id", jobId);
  if (![...params.keys()].length) {
    return Promise.reject(new Error("dataset_id or job_id is required"));
  }
  return fetchJson(`/library/live-identity?${params}`);
}

export function approveJob(jobId) {
  const body = JSON.stringify({});
  return fetch(`${API}/library/jobs/${encodeURIComponent(jobId)}/approve`, deskFetchInit({
    method: "POST",
    body,
  })).then(async (r) => {
    const data = await r.json().catch(() => ({}));
    if (!r.ok && r.status === 404) {
      const r2 = await fetch(`${API}/yzu/jobs/${encodeURIComponent(jobId)}/approve`, deskFetchInit({
        method: "POST",
        body,
      }));
      const d2 = await r2.json().catch(() => ({}));
      if (!r2.ok) throw new Error(d2.message || d2.error || "Approve failed");
      return d2;
    }
    if (!r.ok) throw new Error(data.message || data.error || "Approve failed");
    return data;
  });
}

export function deskWarm({ sessionId, userEmail, background = true } = {}) {
  return fetchJson("/library/desk/warm", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      session_id: sessionId || loadChatSessionId() || undefined,
      user_email: userEmail || loadUserEmail() || undefined,
      background,
    }),
  });
}

export function libraryConsolidated(live = false) {
  const q = live ? "?live=1" : "";
  return fetchJson(`/library/consolidated${q}`);
}

export function listSynthesisProfiles() {
  return fetchJson("/library/synthesis/profiles");
}

/** Durable Synthesis workspaces. The thread, not a browser-local stage, is authoritative. */
export function listSynthesisThreads({ limit = 30, sessionId = "" } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (sessionId) params.set("session_id", sessionId);
  return fetchJson(`/library/synthesis/threads?${params}`);
}

export function getSynthesisThread(threadId) {
  return fetchJson(`/library/synthesis/threads/${encodeURIComponent(threadId)}`);
}

export function createSynthesisThread({ objective, title = "", requiredGrain = "", sessionId = "" } = {}) {
  return fetchJson("/library/synthesis/threads", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      objective,
      title: title || undefined,
      required_grain: requiredGrain || undefined,
      session_id: sessionId || loadChatSessionId() || undefined,
    }),
  });
}

export function decideSynthesisProposal(threadId, { decision, proposalId, proposalHash } = {}) {
  return fetchJson(`/library/synthesis/threads/${encodeURIComponent(threadId)}/patches`, {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      decision,
      proposal_id: proposalId,
      proposal_hash: proposalHash,
    }),
  });
}

export function requestSynthesisExecution(threadId) {
  return fetchJson(`/library/synthesis/threads/${encodeURIComponent(threadId)}/execute`, {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({}),
  });
}

export function synthesisMaterialisation(threadId) {
  return fetchJson(`/library/synthesis/threads/${encodeURIComponent(threadId)}/materialisation`);
}

export function getSynthesisProfile(profileId, { refresh = false } = {}) {
  const q = refresh ? "?refresh=1" : "";
  return fetchJson(`/library/synthesis/${encodeURIComponent(profileId)}${q}`);
}

export function runSynthesis(profileId, { previewLimit = 50, gapLimit = 100 } = {}) {
  return fetchJson("/library/synthesis/run", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      profile_id: profileId,
      preview_limit: previewLimit,
      gap_limit: gapLimit,
    }),
  });
}

export function runSynthesisPair(leftDatasetId, rightDatasetId) {
  return fetchJson("/library/synthesis/pair", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      left_dataset_id: leftDatasetId,
      right_dataset_id: rightDatasetId,
    }),
  });
}

export function adviseDatasets(goal, { datasetId = "", limit = 5 } = {}) {
  return fetchJson("/library/advise", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      goal,
      current_dataset_id: datasetId || undefined,
      limit,
    }),
  });
}

export function rowsToCsv(rows) {
  if (!rows?.length) return "";
  const cols = Object.keys(rows[0]);
  const esc = (v) => {
    const s = String(v ?? "");
    return s.includes(",") || s.includes('"') || s.includes("\n") ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [cols.join(","), ...rows.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
}

export function downloadText(filename, text, mime = "text/plain") {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function sendChatMessage(
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

  const streamRes = await fetch(`${API}/library/chat/stream`, deskFetchInit({
    method: "POST",
    body,
  }));
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

  const fallback = await fetch(`${API}/library/chat`, deskFetchInit({
    method: "POST",
    body,
  }));
  const payload = await fallback.json().catch(() => ({}));
  if (!fallback.ok) throw new Error(normalizeApiError(payload, fallback.status, "/library/chat"));
  if (payload.session_id) saveChatSessionId(payload.session_id);
  return payload;
}

export function openQueryInNewTab(datasetId, limit = 50) {
  const url = `${API}/query/${encodeURIComponent(datasetId)}?limit=${limit}`;
  window.open(url, "_blank", "noopener");
}
