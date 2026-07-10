/** Browse row state pills — frozen in WIREFRAME_V2_FROZEN.md */

import { findJobForCandidate, pendingApprovalCount } from "@/v2/procurementJobs";

function lower(value) {
  return String(value || "").toLowerCase();
}

function isInLab(row, labIds) {
  const id = row?.dataset_id || row?.id;
  return Boolean((id && labIds?.has?.(id)) || row?.local_ready || row?.in_vault || row?.local_root);
}

function isQueued(row) {
  return Boolean(row?.queued || row?.stage === "queued" || row?.procureability === "queued");
}

function isOpenAccess(row) {
  const text = lower(`${row?.license || ""} ${row?.access || ""} ${row?.access_mode || ""}`);
  return /open|public|government|cc-|creative commons|free/.test(text);
}

function hasProbeTarget(row) {
  const url = String(row?.url || "").trim();
  const doi = String(row?.doi || "").trim();
  const handle = String(row?.open_handle || "").trim();
  return Boolean(url || doi || handle.startsWith("doi:"));
}

function accessLabel(row) {
  if (isInLab(row)) return "Vaulted";
  if (isOpenAccess(row)) return "Public";
  if (row?.license) return row.license;
  if (row?.access_mode || row?.access) return row.access_mode || row.access;
  return "Needs terms check";
}

function probeLabel(row, labIds) {
  if (isInLab(row, labIds)) return "Archived";
  if (isQueued(row)) return "Plan queued";
  if (row?.probe_state) return row.probe_state;
  if (row?.probe_snapshot?.connector) return "Connector ready";
  if (hasProbeTarget(row)) return "Probe needed";
  return "Source link required";
}

function fitLabel(row) {
  if (row?.fit_label) return row.fit_label;
  if (row?.fit_score != null) return `${Math.round(Number(row.fit_score) * 100)}% fit`;
  const text = lower(`${row?.title || ""} ${row?.description || ""} ${row?.grain || ""} ${row?.source || ""}`);
  const directFinance = /filing|financial|issuer|twse|governance|misconduct|disclosure/.test(text);
  const taiwanMops = text.includes("mops") && /taiwan|twse|governance|filing|issuer|misconduct|director|pledge|disclosure/.test(text);
  if (directFinance || taiwanMops) return "Faculty finance fit";
  if (/incident|stablecoin|crypto|defi/.test(text)) return "Faculty crypto fit";
  if (/registry|doi|datacite/.test(text)) return "Source-discovery fit";
  return "Needs fit review";
}

function destinationLabel(row) {
  return row?.destination || row?.vault_target || "Lab root";
}

function jobStage(job) {
  const status = String(job?.status || "");
  if (status === "pending_approval") {
    return { key: "awaiting", label: "Awaiting you", className: "queue" };
  }
  if (status === "queued" || status === "running") {
    return { key: "queued", label: status === "running" ? "Collecting" : "Queued", className: "queue" };
  }
  if (status === "failed") {
    return { key: "failed", label: "Failed", className: "fail" };
  }
  return null;
}

export function discoverCandidateState(row, labIds, jobs = []) {
  const inLab = isInLab(row, labIds);
  const boundJob = findJobForCandidate(row, jobs);
  const jobBased = boundJob ? jobStage(boundJob) : null;
  const queued = Boolean(jobBased?.key === "queued" || jobBased?.key === "awaiting" || isQueued(row));
  const probe = probeLabel(row, labIds);
  const stage = inLab
    ? { key: "in_lab", label: "In lab", className: "lab" }
    : jobBased || (queued
      ? { key: "queued", label: "Queued", className: "queue" }
      : /connector ready|probe needed/i.test(probe)
        ? { key: "probe_ready", label: "Probe ready", className: "ext" }
        : { key: "external", label: "External", className: "ext" });

  const awaiting = stage.key === "awaiting";
  const running = stage.key === "queued" && boundJob?.status === "running";
  const canProbe = hasProbeTarget(row);

  return {
    ...stage,
    access: accessLabel(row),
    fit: fitLabel(row),
    probe,
    destination: destinationLabel(row),
    boundJob,
    canProbe,
    nextAction: inLab
      ? "Open in Library"
      : awaiting
        ? "Approve collection to continue"
        : running
          ? "Track collection in Resources"
          : queued
            ? "Review queued job"
            : canProbe
              ? "Probe and add to lab"
              : "Resolve a source link before collection",
  };
}

export function browseRowState(row, labIds, jobs = []) {
  const state = discoverCandidateState(row, labIds, jobs);
  return { label: state.label, className: state.className };
}

export function decorateDiscoverCandidate(row, labIds, jobs = []) {
  const state = discoverCandidateState(row, labIds, jobs);
  const description = [state.access, state.fit, state.probe].filter(Boolean).join(" · ");
  return {
    ...row,
    discover_state: state,
    description: row?.description ? `${row.description} · ${description}` : description,
  };
}

export function discoverStageCounts(rows, labIds, jobs = []) {
  const counts = { total: rows.length, probeReady: 0, queued: 0, awaiting: 0, inLab: 0, external: 0 };
  for (const row of rows) {
    const state = discoverCandidateState(row, labIds, jobs);
    if (state.key === "probe_ready") counts.probeReady += 1;
    else if (state.key === "awaiting") counts.awaiting += 1;
    else if (state.key === "queued") counts.queued += 1;
    else if (state.key === "in_lab") counts.inLab += 1;
    else counts.external += 1;
  }
  const pendingJobs = pendingApprovalCount(jobs);
  counts.awaiting = Math.max(counts.awaiting, pendingJobs);
  return counts;
}
