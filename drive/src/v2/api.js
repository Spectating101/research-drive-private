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

export const API = import.meta.env.DEV ? "/api" : "";
const healthInflight = new Map();

export async function fetchJson(path, init) {
  const { timeoutMs, ...fetchInit } = init || {};
  let timeoutId = null;
  if (timeoutMs && !fetchInit.signal) {
    const controller = new AbortController();
    fetchInit.signal = controller.signal;
    timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  }
  let r;
  try {
    r = await fetch(`${API}${path}`, deskFetchInit(fetchInit));
  } catch (err) {
    if (err?.name === "AbortError") throw new Error(`Request timed out: ${path}`);
    throw err;
  } finally {
    if (timeoutId) window.clearTimeout(timeoutId);
  }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = data.message || data.error || `${r.status} ${path}`;
    throw new Error(msg);
  }
  return data;
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
  const key = live ? "live" : "fast";
  if (healthInflight.has(key)) return healthInflight.get(key);
  const request = fetchJson(`/health${q}`, live ? { timeoutMs: 5000 } : undefined).finally(() => {
    healthInflight.delete(key);
  });
  healthInflight.set(key, request);
  return request;
}

export function deskResources(live = true) {
  const q = live ? "?live=1" : "";
  return fetchJson(`/library/desk/resources${q}`);
}

export function discoverSearch(query = "", limit = 12, email = "") {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (email) params.set("email", email);
  return fetchJson(`/library/discover?${params}`, { timeoutMs: 8000 });
}

export function semanticDiscover(goal = "", limit = 12) {
  return fetchJson("/library/discover/semantic", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({ goal, limit }),
    timeoutMs: 30000,
  });
}

export function webDiscover(query = "", limit = 8, tavilyLive = true) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (!tavilyLive) params.set("tavily", "0");
  return fetchJson(`/library/discover/web?${params}`, { timeoutMs: 10000 });
}

/** Explore source catalogue — preferred Discover search contract. */
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

export function probePublicSource(url, name = "", extra = {}) {
  return fetchJson("/library/discover/probe", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      url,
      name,
      candidate_key: extra.candidateKey || extra.candidate_key || undefined,
      source_id: extra.sourceId || extra.source_id || undefined,
      connector_id: extra.connectorId || extra.connector_id || undefined,
      provider: extra.provider || undefined,
      kind: extra.kind || undefined,
      external_id: extra.externalId || extra.external_id || undefined,
    }),
  });
}

export function submitDiscoverCollect(connectorId, {
  limit = 200,
  autoApprove = false,
  destination = "",
  candidateKey = "",
  sourceId = "",
  url = "",
  provider = "",
  kind = "",
} = {}) {
  return fetchJson("/library/discover/collect", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      connector_id: connectorId,
      limit,
      auto_approve: autoApprove,
      destination: destination || undefined,
      candidate_key: candidateKey || undefined,
      source_id: sourceId || undefined,
      url: url || undefined,
      provider: provider || undefined,
      kind: kind || undefined,
    }),
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

export function unifiedSearch(query = "", limit = 12, email = "", { skipDiscover = false } = {}) {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (email) params.set("email", email);
  if (skipDiscover) params.set("skip_discover", "1");
  return fetchJson(`/library/search?${params}`, { timeoutMs: 8000 });
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
  return fetchJson("/library/catalog?limit=500").then((d) => d.summary || d);
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

export function getJob(jobId) {
  return fetchJson(`/library/jobs/${encodeURIComponent(jobId)}`);
}

export function fetchChatSession(sessionId) {
  if (!sessionId) return Promise.resolve(null);
  return fetchJson(`/library/chat/${encodeURIComponent(sessionId)}`);
}

export function approveSafeJobs(limit = 200) {
  return fetchJson("/library/jobs/approve-safe", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({ limit }),
  });
}

export function approveDatasetLicense({ doi = "", url = "", license = "", note = "" } = {}) {
  return fetchJson("/library/licenses/approve", {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({
      doi,
      url,
      license,
      license_text: license,
      note,
    }),
  });
}

export function approveJob(jobId) {
  return fetchJson(`/library/jobs/${encodeURIComponent(jobId)}/approve`, {
    method: "POST",
    headers: deskHeaders(),
    body: JSON.stringify({}),
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
  /** MCP/Composer equipment — not a faculty UI surface. */
  return fetchJson("/library/synthesis/profiles");
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

  const streamRes = await fetch(`${API}/library/chat/stream`, {
    method: "POST",
    headers: deskHeaders(),
    body,
  });

  if (streamRes.ok && (streamRes.headers.get("content-type") || "").includes("ndjson")) {
    const reader = streamRes.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let result = null;
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) {
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.type === "delta" && event.text) onDelta?.(event.text);
        if ((event.type === "activity" || event.type === "progress") && event.text) {
          onActivity?.(event.text);
        }
        if (event.type === "error") {
          throw new Error(event.message || event.error || "Chat stream error");
        }
        if (event.type === "complete") result = event.result || null;
      }
    }
    if (!result) throw new Error("Chat ended without a response");
    if (result.session_id) saveChatSessionId(result.session_id);
    return result;
  }

  const fallback = await fetch(`${API}/library/chat`, {
    method: "POST",
    headers: deskHeaders(),
    body,
  });
  const payload = await fallback.json().catch(() => ({}));
  if (!fallback.ok) throw new Error(payload.message || payload.error || "Chat error");
  if (payload.session_id) saveChatSessionId(payload.session_id);
  return payload;
}

export function openQueryInNewTab(datasetId, limit = 50) {
  const url = `${API}/query/${encodeURIComponent(datasetId)}?limit=${limit}`;
  window.open(url, "_blank", "noopener");
}
