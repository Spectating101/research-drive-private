/**
 * Discover selected-candidate evaluation helpers (Evaluation Surface E2).
 */

import { classifyDiscoverResult } from "./discoverTaxonomy.js";
import { humanizeDiscoverDescription } from "./browseMeta.js";
import {
  boundProbeResult,
  classifyProbeEvidence,
  deriveUnknowns,
  primaryVerifiedFacts,
} from "./discoverProbeEvidence.js";
import { discoverCandidateUrl } from "./candidateKey.js";

const DECISION = {
  "local-query-ready": {
    headline: "In lab · Query ready",
    body: "You can query this dataset now.",
  },
  "local-connected": {
    headline: "In lab · Connected",
    body: "The asset is connected to the lab, but no instant query path is confirmed.",
  },
  "local-metadata": {
    headline: "In lab · Metadata only",
    body: "The lab has a registry record, but no usable local data path is confirmed.",
  },
  "external-discoverable": {
    headline: "External · Available to inspect",
    body: "This source can be inspected. Acquisition has not been confirmed.",
  },
  "external-probed": {
    headline: "External · Probed",
    body: "The source has been probed. Review verified evidence and remaining unknowns.",
  },
  "external-acquirable": {
    headline: "External · Acquisition available",
    body: "A known collection route is available.",
  },
  "external-unavailable": {
    headline: "External · Acquisition unavailable",
    body: "No supported acquisition route is currently available.",
  },
  "licensed-manual": {
    headline: "Licensed / manual access",
    body: "This source requires entitlement, credentials, or manual intake.",
  },
};

/**
 * Neutral “Useful for” line from deterministic metadata — never fit heuristics.
 */
export function usefulForLine(row) {
  const parts = [
    row?.description,
    row?.recommended_use,
    row?.subject,
    row?.topic,
    row?.subtitle,
  ]
    .map((p) => String(p || "").replace(/\s+/g, " ").trim())
    .filter(Boolean);

  if (parts.length) {
    let text = parts[0];
    const grain = String(row?.grain || "").trim();
    const geo = String(row?.geographic_coverage || "").trim();
    if (grain && !text.toLowerCase().includes(grain.toLowerCase())) {
      text = `${text.replace(/\.$/, "")} at ${grain} grain`;
    } else if (geo && !text.toLowerCase().includes(geo.toLowerCase().slice(0, 12))) {
      text = `${text.replace(/\.$/, "")} · ${geo}`;
    }
    if (text.length > 180) return `${text.slice(0, 179).trim()}…`;
    return text;
  }

  const grain = String(row?.grain || "").trim();
  const coverage = String(row?.coverage || row?.date_range || "").trim();
  const source = String(row?.source || row?.publisher || "").trim();
  if (grain || coverage || source) {
    return [source, coverage, grain ? `${grain} grain` : ""]
      .filter(Boolean)
      .join(" · ");
  }
  return "Research use is not yet described.";
}

export function coverageParts(row) {
  const parts = [
    row?.coverage,
    row?.date_range,
    row?.temporal_coverage,
    row?.geographic_coverage,
    row?.grain,
  ]
    .map((p) => String(p || "").trim())
    .filter(Boolean);
  const seen = new Set();
  const out = [];
  for (const p of parts) {
    const k = p.toLowerCase();
    if (seen.has(k)) continue;
    seen.add(k);
    out.push(p);
  }
  return out;
}

/**
 * Primary + secondary actions for the evaluation footer.
 * @returns {{ primary: { id: string, label: string }, secondary: { id: string, label: string }[] }}
 */
export function evaluationActions(row, taxonomy, { queued = false, hasProbeUrl = false, probed = false } = {}) {
  const key = taxonomy?.key || "external-discoverable";

  if (queued) {
    return {
      primary: { id: "track_resources", label: "Track in Resources" },
      secondary: [
        hasProbeUrl ? { id: "probe", label: "Probe source" } : null,
        { id: "ask", label: "Ask about this source" },
      ].filter(Boolean),
    };
  }

  if (key === "local-query-ready" || key === "local-connected") {
    return {
      primary: { id: "open_library", label: "Open in Library" },
      secondary: [{ id: "ask", label: "Ask about this source" }],
    };
  }
  if (key === "local-metadata") {
    return {
      primary: { id: "inspect_record", label: "Inspect record" },
      secondary: [
        { id: "open_library", label: "Open in Library" },
        { id: "ask", label: "Ask about this source" },
      ],
    };
  }
  if (key === "licensed-manual") {
    return {
      primary: { id: "review_access", label: "Review access requirements" },
      secondary: [
        hasProbeUrl ? { id: "probe", label: "Probe source" } : null,
        { id: "ask", label: "Ask about this source" },
        { id: "preview", label: "Preview source" },
      ].filter(Boolean),
    };
  }
  if (key === "external-unavailable") {
    return {
      primary: { id: "ask", label: "Ask about this source" },
      secondary: [
        hasProbeUrl ? { id: "probe", label: "Probe source" } : null,
        { id: "preview", label: "Preview source" },
      ].filter(Boolean),
    };
  }
  if (key === "external-acquirable") {
    return {
      primary: { id: "add_lab", label: "Request this evidence" },
      secondary: [
        hasProbeUrl && !probed ? { id: "probe", label: "Probe source" } : null,
        { id: "preview", label: "Preview source" },
        { id: "ask", label: "Ask about this source" },
      ].filter(Boolean),
    };
  }
  if (key === "external-probed") {
    return {
      primary: { id: "preview", label: "Preview source" },
      secondary: [
        { id: "add_lab", label: "Request this evidence" },
        hasProbeUrl ? { id: "probe", label: "Probe again" } : null,
        { id: "ask", label: "Ask about this source" },
      ].filter(Boolean),
    };
  }
  // external-discoverable default
  return {
    primary: hasProbeUrl
      ? { id: "probe", label: "Probe source" }
      : { id: "preview", label: "Preview source" },
    secondary: [
      { id: "add_lab", label: "Request this evidence" },
      { id: "ask", label: "Ask about this source" },
      hasProbeUrl ? { id: "preview", label: "Preview source" } : null,
    ].filter(Boolean),
  };
}

export function decisionCopy(taxonomy) {
  return DECISION[taxonomy?.key] || DECISION["external-discoverable"];
}

/**
 * Full evaluation model for the Discover Detail surface.
 */
export function buildDiscoverEvaluation(row, labIds, probeState) {
  const probe = boundProbeResult(row, probeState);
  const hasProbe = Boolean(probe);
  // Reclassify with bound probe so rail taxonomy matches list after probe (D1.1).
  const rowForTaxonomy = hasProbe
    ? {
        ...row,
        discover_taxonomy: undefined,
        discover_state: undefined,
        probe_snapshot: probe,
      }
    : row;
  const taxonomy = classifyDiscoverResult(rowForTaxonomy, labIds);
  const classified = hasProbe
    ? classifyProbeEvidence(row, probe)
    : { verified: [], inferred: [], model: [], technical: [] };
  const decision = decisionCopy(taxonomy);
  const usefulFor = humanizeDiscoverDescription(usefulForLine(row));
  const coverage = coverageParts(row);
  const verified = primaryVerifiedFacts(classified);
  const unknowns = deriveUnknowns(row, taxonomy, classified, hasProbe);
  const hasProbeUrl = Boolean(discoverCandidateUrl(row));
  const actions = evaluationActions(row, taxonomy, {
    queued: Boolean(row?.queued),
    hasProbeUrl,
    probed: hasProbe,
  });

  const sourceLine = [row?.source || row?.publisher || row?.collect_via, row?.geographic_coverage]
    .map((p) => String(p || "").trim())
    .filter(Boolean)
    .join(" · ");

  return {
    title: row?.title || row?.name || row?.dataset_id || "External dataset",
    sourceLine: sourceLine || "Source not described",
    taxonomyLabel: taxonomy.label,
    taxonomyKey: taxonomy.key,
    decision,
    usefulFor,
    coverage,
    verified,
    unknowns,
    inferred: (classified.inferred || []).map((f) => f.label),
    modelNotes: (classified.model || []).map((f) => ({ label: f.label, detail: f.detail })),
    technical: classified.technical || [],
    actions,
    hasProbe,
    probeError: probeState?.error || "",
    probeLoading: Boolean(probeState?.loading),
  };
}
