import { candidateKey, discoverCandidateUrl } from "@/v2/candidateKey";

export { discoverCandidateUrl } from "@/v2/candidateKey";

export function buildAddToLabPrompt(target, probeResult) {
  const label = target?.title || target?.dataset_id || target?.name || "this dataset";
  const connector = probeResult?.connector;
  const summary = probeResult?.summary;
  const payload = {
    title: label,
    candidate_key: candidateKey(target) || null,
    dataset_id: target?.dataset_id || null,
    doi: target?.doi || null,
    url: discoverCandidateUrl(target) || null,
    source_identity: target?.source || target?.collect_via || null,
    connector_id: connector?.connector_id || connector?.id || null,
    probe: summary || null,
  };
  return [
    `Add to lab vault: ${label}`,
    "",
    "Candidate (structured):",
    JSON.stringify(payload, null, 2),
    "",
    "If no job was queued, probe the source if needed, then submit yzu_submit_job with a safe collection plan.",
  ].join("\n");
}

export function buildAddToLabDisplayText(target, probeResult, jobId = "") {
  const label = target?.title || target?.dataset_id || target?.name || "this dataset";
  const firstLine = `Add to lab vault: ${label}`;
  if (jobId) return `${firstLine}\nCollection job queued. Track it in Resources.`;
  if (probeResult?.summary) {
    return `${firstLine}\nUse the probed source details to prepare a safe collection plan.`;
  }
  return `${firstLine}\nInspect the source if needed, then prepare a safe collection plan.`;
}

export function webHitsToRows(data) {
  const fromSections = (data.sections || []).flatMap((s) => s.rows || []);
  if (fromSections.length) {
    return fromSections.map((hit) => {
      const url = hit.url || "";
      return {
        ...hit,
        kind: hit.kind || "web_hit",
        candidate_key: hit.candidate_key || (url ? `url:${url}` : ""),
        url,
      };
    });
  }
  return (data.results || []).map((hit) => {
    const url = hit.url || "";
    return {
      kind: "web_hit",
      title: hit.title || hit.url || "Web source",
      url,
      source: hit.source || "web",
      description: hit.snippet || hit.content || "",
      publisher: hit.source || "web",
      candidate_key: hit.candidate_key || (url ? `url:${url}` : ""),
    };
  });
}
