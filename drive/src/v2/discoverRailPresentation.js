/**
 * Discover Detail rail presentation — factual inspector for a selected source candidate.
 * Reuses discoverCandidateState + assessDiscoverCandidate; never fabricates coverage or readiness.
 */

import { assessDiscoverCandidate } from "@/v2/discoverCompare";
import { discoverCandidateState } from "@/v2/browseMeta";
import { discoverCandidateUrl } from "@/v2/discoverActions";
import { formatMetaValue } from "@/v2/datasetMeta";
import { PAGE_DETAIL_EMPTY } from "@/v2/railEmptyCopy";

export { PAGE_DETAIL_EMPTY };

function meta(value) {
  const text = formatMetaValue(value);
  return text && text !== "—" ? text : "";
}

function pushFact(list, label, value) {
  const text = String(value || "").trim();
  if (!text || text === "—") return;
  list.push({ label, value: text });
}

/**
 * Build Detail rail model for a Discover source candidate.
 * @returns {{
 *   title: string,
 *   statusLabel: string,
 *   statusClass: string,
 *   judgment: string,
 *   confirmed: Array<{label: string, value: string}>,
 *   unknowns: Array<{label: string, value: string}>,
 *   evidence: Array<{label: string, value: string}>,
 *   showCollectionPlan: boolean,
 * }}
 */
export function buildDiscoverCandidateRailState({
  target,
  labIds,
  jobs = [],
  catalog = [],
  profile = null,
  peers = [],
  probeSummary = "",
  connector = null,
  preflight = null,
} = {}) {
  if (!target) return null;

  const state = target.discover_state || discoverCandidateState(target, labIds, jobs);
  const compare = assessDiscoverCandidate({ target, catalog, profile, peers, labIds });
  const title = target.title || target.name || target.dataset_id || "External dataset";
  const source = meta(target.source || target.collect_via || target.publisher || target.backend || target.domain);
  const coverage = meta(target.coverage || target.subtitle);
  const grain = meta(target.grain);
  const license = meta(target.license);
  const access = meta(state.access);
  const fit = meta(state.fit || compare.profile?.label);
  const probe = meta(state.probe);
  const labCoverage =
    compare.labMatch?.overlap?.pct != null
      ? `${compare.labMatch.overlap.pct}% vs ${compare.labMatch.dataset?.name || compare.labMatch.dataset?.title || compare.labMatch.dataset?.dataset_id || "lab"} · ${compare.labMatch.reason || "overlap"}`
      : "";

  const confirmed = [];
  const fitKnown = Boolean(fit) && !/needs fit review/i.test(fit);
  if (fitKnown) pushFact(confirmed, "Fit", fit);
  if (labCoverage || state.key === "in_lab") {
    pushFact(confirmed, "Local coverage", labCoverage || "Already in lab");
  }
  pushFact(confirmed, "Source", source);
  pushFact(confirmed, "Access", access);
  pushFact(confirmed, "Coverage", coverage);
  pushFact(confirmed, "Grain", grain);
  if (license) pushFact(confirmed, "License", license);
  const probeKnown = Boolean(probe) && !/probe needed|source link required/i.test(probe);
  if (probeKnown) pushFact(confirmed, "Probe", probe);

  const unknowns = [];
  if (!fitKnown) pushFact(unknowns, "Fit", "Needs fit review against faculty stack");
  if (!labCoverage && state.key !== "in_lab") {
    pushFact(unknowns, "Local coverage", "No close lab match yet");
  }
  if (!coverage) pushFact(unknowns, "Coverage", "Not reported by source");
  if (!grain) pushFact(unknowns, "Grain", "Not reported by source");
  if (!license) pushFact(unknowns, "License", "See source terms");
  if (!probeKnown && probe) pushFact(unknowns, "Probe", probe);

  const unknownRows = unknowns;

  const evidence = [];
  if (probeSummary) pushFact(evidence, "Probe summary", probeSummary);
  const connectorId = connector?.connector_id || connector?.id;
  if (connectorId) pushFact(evidence, "Connector", connectorId);
  const spec = connector?.spec || {};
  if (spec.access_mode) pushFact(evidence, "Access mode", meta(spec.access_mode));
  if (spec.content_type) pushFact(evidence, "Format", meta(spec.content_type));
  if (Array.isArray(spec.discovered_files)) {
    pushFact(evidence, "Files", String(spec.discovered_files.length));
  }
  if (preflight?.connector) pushFact(evidence, "On collect", preflight.connector);
  if (preflight?.onAdd) pushFact(evidence, "Add to lab", preflight.onAdd);
  if (preflight?.approval && preflight.approval !== "—") {
    pushFact(evidence, "Approval", preflight.approval);
  }
  if (preflight?.destination) pushFact(evidence, "Vault path", preflight.destination);
  if (target.dataset_id) pushFact(evidence, "Candidate id", target.dataset_id);
  if (target.doi) pushFact(evidence, "DOI", target.doi);
  const url = discoverCandidateUrl(target);
  if (url) pushFact(evidence, "URL", url);

  const judgment = compare.verdict || state.nextAction || "Inspect fit and probe before collecting.";

  return {
    title,
    statusLabel: state.label,
    statusClass: state.className || "",
    stateKey: state.key,
    judgment,
    confirmed,
    unknowns: unknownRows,
    evidence,
    showCollectionPlan: state.key !== "in_lab",
    canProbe: Boolean(url) && state.key !== "in_lab",
    probeUrl: url || "",
  };
}

