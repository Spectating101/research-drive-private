function words(value) {
  return String(value || "").toLowerCase();
}

export function researchNeedFromQuery(query) {
  const text = String(query || "").trim();
  const lower = words(text);
  const fields = [];
  if (/\brevenue\b/.test(lower)) fields.push("revenue");
  if (/\breturn(s)?\b/.test(lower)) fields.push("returns");
  if (/\bprice(s)?\b|\bclose\b/.test(lower)) fields.push("close");
  if (/\bvolume\b/.test(lower)) fields.push("volume");
  if (/\bfiling/.test(lower)) fields.push("filing_date");

  return {
    title: text || "Untitled financial research need",
    universe: /\bissuer|company|listed/.test(lower) ? "listed issuers" : "",
    market: /\btaiwan|\btwse|\btaipex/.test(lower) ? "TW" : "",
    frequency: /\bquarterly|quarter\b/.test(lower)
      ? "quarterly"
      : /\bmonthly|month\b/.test(lower)
        ? "monthly"
        : "",
    point_in_time_required: /\bpoint.?in.?time|\bvintage|\bhistorical constituent/.test(lower),
    fields,
  };
}

function evidenceStatus(value) {
  const status = String(value || "").toLowerCase();
  if (status === "verified" || status === "observed") return "verified";
  if (status === "inferred") return "inferred";
  return "unknown";
}

/** Merge catalog candidate + optional probe snapshot into a durable SourceOffering. */
export function offeringFromCandidate(candidate = {}, probe = null) {
  const key = String(
    candidate.candidate_key || candidate.dataset_id || candidate.url || candidate.title || "",
  ).trim();
  const connectorId = String(
    probe?.connector?.connector_id ||
      probe?.connector?.id ||
      candidate.connector_id ||
      "",
  ).trim();
  const url = String(
    probe?.url || candidate.url || candidate.source_url || candidate.landing_url || "",
  ).trim();
  const probeOk = Boolean(probe && (probe.ok || probe.connector || probe.sample));
  const accessStatus = probeOk && connectorId ? "verified" : connectorId ? "inferred" : "unknown";
  const pitStatus = evidenceStatus(
    probe?.point_in_time?.status || candidate.point_in_time_status || "unknown",
  );

  const evidence = [
    {
      kind: "catalog",
      status: "inferred",
      source: candidate.source || candidate.publisher || "",
    },
  ];
  if (probe) {
    evidence.push({
      kind: "probe",
      status: probeOk ? "verified" : "unknown",
      observed_at: probe.observed_at || probe.checked_at || "",
      connector_id: connectorId || undefined,
    });
  }

  return {
    candidate_key: key,
    title: candidate.title || candidate.name || candidate.dataset_id || "Untitled source",
    url,
    source_id: candidate.source_id || "",
    connector_id: connectorId,
    coverage: {
      market: candidate.market || candidate.geography || "",
      start: candidate.coverage_start || "",
      frequency: candidate.frequency || candidate.grain || "",
      summary: candidate.coverage || "",
    },
    fields: Array.isArray(candidate.fields) ? candidate.fields : [],
    point_in_time: { status: pitStatus },
    access: {
      route: connectorId ? "public_connector" : url ? "craft" : "researcher_review",
      status: accessStatus,
      connector_id: connectorId || undefined,
      url: url || undefined,
    },
    evidence,
  };
}

export function preferredRouteForOffering(offering = {}) {
  const access = offering.access || {};
  const connectorId = offering.connector_id || access.connector_id || "";
  const url = offering.url || access.url || "";
  if (connectorId) {
    return {
      kind: "public_connector",
      connector_id: connectorId,
      source_id: offering.source_id || "",
      url,
    };
  }
  if (url) {
    return { kind: "craft", url };
  }
  return { kind: "researcher_review" };
}
