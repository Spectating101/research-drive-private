export function discoverCandidateUrl(row) {
  if (!row) return "";
  const raw = String(row.url || "").trim();
  if (raw) return raw;
  const doi = String(row.doi || "").trim();
  if (doi) {
    const bare = doi.replace(/^https?:\/\/(dx\.)?doi\.org\//i, "");
    return `https://doi.org/${bare}`;
  }
  const handle = String(row.open_handle || "").trim();
  if (handle.startsWith("doi:")) return `https://doi.org/${handle.slice(4)}`;
  return "";
}

export function browseTargetKey(target) {
  if (!target) return "";
  return target.dataset_id || target.url || target.doi || target.title || target.name || "";
}

export function buildAddToLabPrompt(target, probeResult) {
  const label = target?.title || target?.dataset_id || target?.name || "this dataset";
  const connector = probeResult?.connector;
  const summary = probeResult?.summary;
  const facts = [
    target?.dataset_id ? `dataset ${target.dataset_id}` : "",
    target?.doi ? `DOI ${target.doi}` : "",
    discoverCandidateUrl(target) ? `URL ${discoverCandidateUrl(target)}` : "",
    target?.source || target?.collect_via ? `source ${target.source || target.collect_via}` : "",
    connector?.connector_id || connector?.id ? `connector ${connector.connector_id || connector.id}` : "",
    summary ? `probe ${summary}` : "",
  ].filter(Boolean);
  return [
    `Add "${label}" to the lab vault.`,
    facts.length ? `Candidate details: ${facts.join("; ")}.` : "",
    "",
    "If no collection job was queued yet, probe the source if needed, then submit a safe yzu_submit_job plan with vault archival and registry verification.",
  ].filter(Boolean).join("\n");
}

export function webHitsToRows(data) {
  const fromSections = (data.sections || []).flatMap((s) => s.rows || []);
  if (fromSections.length) return fromSections;
  return (data.results || []).map((hit) => ({
    kind: "web_hit",
    title: hit.title || hit.url || "Web source",
    url: hit.url,
    source: hit.source || "web",
    description: hit.snippet || hit.content || "",
    publisher: hit.source || "web",
  }));
}
