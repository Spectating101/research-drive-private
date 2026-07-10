/** Research Drive v2 — HTTP client (dev proxies /api → :8765 via vite.config.js). */

import { deskHeaders, loadChatSessionId, loadUserEmail, saveChatSessionId } from "@/v2/deskSession";

export const API = import.meta.env.DEV ? "/api" : "";

export async function fetchJson(path, init) {
  const r = await fetch(`${API}${path}`, init);
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const msg = data.message || data.error || `${r.status} ${path}`;
    throw new Error(msg);
  }
  return data;
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

export function approveJob(jobId) {
  const body = JSON.stringify({});
  return fetch(`${API}/library/jobs/${encodeURIComponent(jobId)}/approve`, {
    method: "POST",
    headers: deskHeaders(),
    body,
  }).then(async (r) => {
    const data = await r.json().catch(() => ({}));
    if (!r.ok && r.status === 404) {
      const r2 = await fetch(`${API}/yzu/jobs/${encodeURIComponent(jobId)}/approve`, {
        method: "POST",
        headers: deskHeaders(),
        body,
      });
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
